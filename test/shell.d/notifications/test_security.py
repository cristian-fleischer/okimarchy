"""Store redaction and file safety, KDE Connect replies, icon paths."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

from support import HELPERS, have_magick, load_helper, png
import notification_files as files

STATE = '.local/state/omarchy/notifications'


class Storage(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.home = Path(self.tmp.name)
    self.live = self.home / STATE / 'live'
    self.env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE='1')

  def run_store(self, *args, payload=None):
    return subprocess.run([sys.executable, str(HELPERS / 'store'), *args],
                          input=json.dumps(payload) if payload is not None else '',
                          text=True, capture_output=True, env=self.env)

  def rows(self, verb):
    result = self.run_store(verb)
    self.assertEqual(result.returncode, 0, result.stderr)
    return json.loads(result.stdout)

  def test_exec_argv_and_glyph_persist_through_restore_and_history(self):
    # A toast restored after a shell restart must click through like the live one.
    argv = json.dumps(['omarchy-update'])
    entry = {'key': 'update', 'app': 'Omarchy', 'summary': 'Update available',
             'body': 'Click to update', 'glyph': '', 'execArgv': argv}
    self.assertEqual(self.run_store('put', payload=entry).returncode, 0)
    self.assertEqual(self.rows('restore'), [entry])
    self.assertEqual(self.run_store('close', 'update', 'dismissed').returncode, 0)
    [closed] = self.rows('history')
    self.assertEqual((closed['execArgv'], closed['glyph']), (argv, ''))

  def test_exec_argv_is_validated_on_write_and_read(self):
    cases = {
        'not-json': '{"omarchy-update"',
        'not-a-list': json.dumps('omarchy-update'),
        'empty': json.dumps([]),
        'too-many': json.dumps(['echo'] + ['x'] * 32),
        'non-string': json.dumps(['echo', 1]),
        'blank-program': json.dumps(['', 'x']),
        'option-program': json.dumps(['--help']),
        'long-argument': json.dumps(['echo', 'x' * 4097]),
        'long-total': json.dumps(['run'] + ['x' * 4000] * 9),
        'nul': json.dumps(['echo', 'a\x00b']),
    }
    self.rows('restore')
    for key, value in cases.items():
      with self.subTest(case=key):
        if len(json.dumps({'key': key, 'execArgv': value})) < 65536:
          self.assertEqual(self.run_store('put', payload={'key': key, 'execArgv': value}).returncode, 0)
          self.assertEqual(json.loads((self.live / f'{key}.json').read_text())['execArgv'], '')
        (self.live / f'{key}.json').write_text(json.dumps({'key': key, 'execArgv': value}))
    rows = {row['key']: row for row in self.rows('restore')}
    self.assertEqual({key: rows[key]['execArgv'] for key in cases}, dict.fromkeys(cases, ''))
    valid = json.dumps(['notify-send', '-a', 'x', 'y' * 4096])
    self.assertEqual(self.run_store('put', payload={'key': 'valid', 'execArgv': valid}).returncode, 0)
    self.assertEqual(self.rows('restore')[-1]['execArgv'], valid)

  def test_glyph_is_bounded(self):
    for key, glyph, kept in (('short', '\U000f0001', True), ('word', 'abcdefghijklmnop', True),
                             ('long', 'a' * 17, False), ('control', '\n', False),
                             ('escape', '\x1b[31m', False), ('empty', '', False)):
      with self.subTest(case=key):
        self.assertEqual(self.run_store('put', payload={'key': key, 'glyph': glyph}).returncode, 0)
        row = json.loads((self.live / f'{key}.json').read_text())
        self.assertEqual(row.get('glyph'), glyph if kept else None)

  def test_ordinary_restore_and_off(self):
    self.assertEqual(self.run_store('put', payload={'key': 'n1', 'body': 'ordinary message'}).returncode, 0)
    self.assertEqual(self.rows('restore')[0]['body'], 'ordinary message')
    self.assertEqual(self.run_store('policy', payload={'historyHours': 0}).returncode, 0)
    self.run_store('close', 'n1', 'done')
    self.assertEqual(self.rows('history'), [])

  def test_symlinks_traversal_and_oversize_are_refused(self):
    linked = self.home / STATE
    linked.parent.mkdir(parents=True)
    target = self.home / 'victim-directory'
    target.mkdir()
    linked.symlink_to(target, target_is_directory=True)
    self.assertNotEqual(self.run_store('put', payload={'key': 'n1'}).returncode, 0)
    self.assertEqual(list(target.iterdir()), [])
    linked.unlink()

    self.rows('restore')
    victim = self.home / 'victim'
    victim.write_text('untouched')
    (self.live / 'n1.json').symlink_to(victim)
    for entry in ({'key': 'n1', 'body': 'x'}, {'key': '../../escape', 'body': 'x'},
                  {'key': 'n2', 'body': 'x' * 70000}):
      self.assertNotEqual(self.run_store('put', payload=entry).returncode, 0, entry['key'])
    self.assertEqual(victim.read_text(), 'untouched')

  def test_numbered_ordinary_notifications_survive_put_and_legacy_reads(self):
    cases = [
        ('Visual Studio Code', 'Build finished', 'Build 4123 completed successfully'),
        ('Assistant', 'Task finished', 'Claude Code finished build 4123'),
        ('Chat', 'New message', 'Please review the code from 2025'),
        ('VS Code', 'Build finished', 'VS Code finished build 4123'),
        ('Xcode', 'Build finished', 'Xcode build 4123 completed'),
        ('Chat', 'Review requested', 'Please review code abc123'),
        ('OTP Monitor', 'Build finished', 'Build 4123 completed successfully'),
        ('Auth', 'Verification completed successfully', 'Account ready'),
        ('Settings', 'PIN configuration updated', 'Settings saved'),
    ]
    self.rows('restore')
    stamp = int(time.time() * 1000)
    for i, (app, summary, body) in enumerate(cases):
      # Production rows carry numbered keys and lowercase product group keys;
      # neither belongs in the content detector.
      entry = {'key': f'notification-{4123 + i}', 'app': app, 'summary': summary,
               'body': body, 'rawBody': body, 'bodyLine': body,
               'groupKey': app.lower(), 'source': app, 'urgency': 1}
      with self.subTest(app=app, body=body):
        self.assertEqual(self.run_store('put', payload=entry).returncode, 0)
        live = self.live / f'{entry["key"]}.json'
        self.assertEqual(json.loads(live.read_text()), entry)
        history = self.home / STATE / 'history' / f'{stamp}-{entry["key"]}.json'
        for path in (live, history):
          path.write_text(json.dumps(entry))
          path.chmod(0o644)
        for verb in ('restore', 'history'):
          self.assertIn(entry, self.rows(verb))
        for path in (live, history):
          self.assertEqual(json.loads(path.read_text()), entry)
          self.assertEqual(path.stat().st_mode & 0o777, 0o600)

  def test_codes_redact_the_whole_row_on_put_and_legacy_reads(self):
    cases = [
        {'code': '938271', 'body': '938271'},
        {'codes': '938271', 'rawBody': '&#57;38271'},
        {'body': 'Your code is 938271'},
        {'body': 'Your code is G-938271'},
        {'body': 'Your OTP is 938 271'},
        {'body': 'Your OTP is 938\t271'},
        {'body': 'Your OTP is 938\n271'},
        {'body': 'Your OTP is 938 271'},
        {'body': 'Your code is 72-9182'},
        {'body': 'Your code is A9F3K2'},
        {'body': 'Your code is &#57;38271'},
        {'body': 'Your code is &amp;#57;38271'},
        {'body': 'Your OTP is 938<br/>271'},
        {'body': 'Your code to finish signing in to your account in this browser is 938271'},
        {'body': '938271 is your verification code'},
        {'body': 'Please confirm 938271'},
        {'body': 'Your security key is 938271'},
        {'body': 'Your Verification Code is 938271'},
        {'summary': 'Your code is', 'body': '938271'},
        {'summary': 'Your OTP is 938271'},
        {'rawBody': 'Your OTP is 938\n271', 'body': 'Open the app'},
    ]
    self.rows('restore')
    state = self.home / STATE
    stamp = int(time.time() * 1000)
    for mode in ('put', 'legacy-live', 'legacy-history'):
      directory = 'history' if mode == 'legacy-history' else 'live'
      expected = {}
      for i, text in enumerate(cases):
        key = f'{mode}-{i}'
        # Every string but the key goes, glyph and stored command line included.
        entry = {'key': key, 'urgency': 1, 'app': 'alternate-secret',
                 'groupKey': 'alternate-secret', 'bodyLine': 'alternate-secret',
                 'source': 'alternate-secret', 'appIcon': 'alternate-secret',
                 'replyTo': 'alternate-secret', 'image': '/etc/passwd', 'glyph': '',
                 'execArgv': json.dumps(['xdg-open', 'https://example.com/938271']), **text}
        expected[key] = {'key': key, 'urgency': 1,
                         'summary': 'Verification notification', 'body': '[redacted]',
                         'rawBody': '[redacted]', 'bodyLine': '[redacted]'}
        path = state / directory / (f'{stamp}-{key}.json' if directory == 'history' else f'{key}.json')
        with self.subTest(mode=mode, text=text):
          if mode == 'put':
            result = self.run_store('put', payload=entry)
            self.assertEqual(result.returncode, 0, result.stderr)
            # Checked before restore: a migration must not mask a put leak.
            self.assertEqual(json.loads(path.read_text()), expected[key])
          else:
            path.write_text(json.dumps(entry))
            path.chmod(0o644)
      rows = {row['key']: row for row in self.rows('history' if directory == 'history' else 'restore')}
      for key, clean in expected.items():
        with self.subTest(mode=mode, key=key):
          self.assertEqual(rows[key], clean)
          path = state / directory / (f'{stamp}-{key}.json' if directory == 'history' else f'{key}.json')
          self.assertEqual(json.loads(path.read_text()), clean)
          self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class Replies(unittest.TestCase):
  PATH = '/modules/kdeconnect/devices/device/notifications/1'

  def setUp(self):
    self.k = load_helper('kdeconnect')

  def test_ambiguous_and_empty(self):
    a = dict(appName='Chat', text='hello', ticker='', replyId='1', path=self.PATH)
    with patch.object(self.k, 'listing', return_value=[a, a]):
      self.assertIsNone(self.k.find('Chat', 'hello'))
    with patch.object(self.k, 'listing', return_value=[a]):
      self.assertEqual(self.k.find('Chat', 'hello'), a)
      for app, body in (('Other', 'hello'), ('Chat', 'something else'), ('Chat', '')):
        self.assertIsNone(self.k.find(app, body))

  def test_path(self):
    self.assertTrue(self.k.valid_path('/modules/kdeconnect/devices/device_1/notifications/12'))
    for p in ('fake:1', '/org/other', '--help', '; rm -rf ~', '$(touch /tmp/pwned)', '`touch /tmp/pwned`',
              self.PATH + '\n'):
      self.assertFalse(self.k.valid_path(p), p)

  def test_command_text_is_data(self):
    for text in ('; rm -rf ~', '$(touch /tmp/pwned)', '`touch /tmp/pwned`', '--help', 'quotes"\n\\'):
      with patch.object(sys, 'argv', ['helper', 'reply', self.PATH, text, 'Chat', 'body']), \
              patch.object(self.k, 'find', return_value={'path': self.PATH}), \
              patch.object(self.k.subprocess, 'run', return_value=MagicMock(returncode=0)) as run, \
              contextlib.redirect_stdout(io.StringIO()):
        self.assertEqual(self.k.main(), 0)
      call = run.call_args_list[0]
      self.assertEqual((call.args[0][2], call.args[0][-1]), ('--', text))
      self.assertNotIn('shell', call.kwargs)

  def demo(self, temp, **row):
    fixture = Path(temp) / 'notification.json'
    files.write_json(fixture, dict({'token': 'a' * 32, 'created': time.time(),
                                    'title': 'Demo sender', 'text': 'hello'}, **row))
    return fixture

  def test_demo_cannot_impersonate_a_real_phone_app(self):
    with tempfile.TemporaryDirectory() as temp, \
            patch.object(self.k, 'FIXTURE', self.demo(temp, appName='WhatsApp')), \
            patch.object(self.k, 'listing', return_value=[]):
      self.assertIsNone(self.k.find('WhatsApp', 'Demo sender: hello'))
      self.assertEqual(self.k.find('Omarchy reply demo', 'Demo sender: hello')['appName'], 'Omarchy reply demo')

  def test_demo_rejects_replaced_and_expired_sessions(self):
    with tempfile.TemporaryDirectory() as temp:
      reply = Path(temp) / 'reply.json'
      with patch.object(self.k, 'FIXTURE', self.demo(temp)), patch.object(self.k, 'REPLY_LOG', reply), \
              patch.object(self.k, 'listing', return_value=[]):
        original = self.k.find('Omarchy reply demo', 'Demo sender: hello')
        self.assertIsNotNone(original)
        self.demo(temp, token='b' * 32)
        with patch.object(sys, 'argv', ['helper', 'reply', original['path'], 'must not be sent',
                                        'Omarchy reply demo', 'Demo sender: hello']):
          self.assertEqual(self.k.main(), 1)
        self.assertFalse(reply.exists())
        self.demo(temp, created=time.time() - self.k.FIXTURE_MAX_AGE - 1)
        self.assertIsNone(self.k.find('Omarchy reply demo', 'Demo sender: hello'))


class Icons(unittest.TestCase):
  def setUp(self):
    self.icon = load_helper('icon')

  def test_icon_hint_traversal(self):
    with patch.object(self.icon.glob, 'glob', return_value=[]) as glob:
      self.icon.from_icon_theme(['../../../../etc/passwd', '/etc/passwd', '*', '--help'])
    for call in glob.call_args_list:
      self.assertNotIn('../', call.args[0])

  def test_local_theme_svgs_are_found(self):
    with tempfile.TemporaryDirectory() as temp:
      theme = Path(temp) / 'hicolor/scalable/apps'
      theme.mkdir(parents=True)
      (theme / 'kitty.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
      with patch.object(self.icon, 'ICON_DIRS', [temp]):
        self.assertEqual(self.icon.from_icon_theme(['kitty']), str(theme / 'kitty.svg'))


@unittest.skipUnless(have_magick(), "imagemagick is not installed")
class Raster(unittest.TestCase):
  def setUp(self):
    self.icon = load_helper('icon')

  def test_sender_raster_and_dimension_limit(self):
    for size, accepted in (((256, 256), True), ((2049, 1), False)):
      with self.subTest(size=size):
        try:
          width, height, rgba = self.icon.sender_pixels(png(size, (0, 0, 0, 255)))
        except ValueError:
          self.assertFalse(accepted)
        else:
          self.assertTrue(accepted)
          self.assertLessEqual(max(width, height), 128)
          self.assertEqual(len(rgba), width * height * 4)

  def test_local_icons_normalise_to_one_canvas(self):
    import notification_images
    # A small opaque square and a padded transparent plus come out the same
    # canvas size; the opaque one is inset less and has its corners cleared.
    opaque = png((16, 16), (200, 40, 40, 255))
    glyph = notification_images.encode_png(64, 64, b''.join(
        bytes((0, 0, 0, 255) if 16 <= x < 48 and 16 <= y < 48 and (28 <= x < 36 or 28 <= y < 36) else (0, 0, 0, 0))
        for y in range(64) for x in range(64)))
    with tempfile.TemporaryDirectory() as temp:
      for name, data, mono in (('opaque.png', opaque, False), ('glyph.png', glyph, True)):
        source = Path(temp) / name
        source.write_bytes(data)
        rgba, found_mono = self.icon.normalise(str(source))
        self.assertEqual(found_mono, mono, name)
        self.assertEqual(len(rgba), 128 * 128 * 4)
        self.assertEqual(rgba[(64 * 128 + 64) * 4 + 3], 255)
      corner = self.icon.normalise(str(Path(temp) / 'opaque.png'))[0]
      self.assertEqual(corner[(4 * 128 + 4) * 4 + 3], 0)
      # Normalising writes nothing: only the launcher publishes icons.
      self.assertEqual(sorted(p.name for p in Path(temp).iterdir()), ['glyph.png', 'opaque.png'])
      self.assertIsNone(self.icon.normalise(str(Path(temp) / 'missing.png')))


if __name__ == '__main__':
  unittest.main()
