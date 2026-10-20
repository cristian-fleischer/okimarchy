"""Store redaction and file safety."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from support import HELPERS

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


if __name__ == '__main__':
  unittest.main()
