"""Store redaction and file safety, pinned HTTPS, KDE Connect replies, icon paths."""
import argparse
import io
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

from support import HELPERS, have_magick, load_helper, png
import notification_http as net
import notification_files as files

STATE = '.local/state/omarchy/notifications'

def module(name):
  return load_helper(name)

class Storage(unittest.TestCase):
  def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)
    self.env=dict(os.environ,HOME=str(self.home),PYTHONDONTWRITEBYTECODE='1')
  def tearDown(self): self.tmp.cleanup()
  def run_store(self,*args,payload=None):
    return subprocess.run([sys.executable,str(HELPERS/'store'),*args],input=json.dumps(payload) if payload is not None else '',text=True,capture_output=True,env=self.env)
  def test_explicit_code_flags_redact_whole_row(self):
    for flag in ('code', 'codes'):
      entry = {'key': flag, flag: '938271', 'app': '938271',
               'summary': '938271', 'body': '938271', 'rawBody': '&#57;38271',
               'bodyLine': '938 271', 'groupKey': '938271',
               'image': '/etc/passwd', 'replyTo': '938271'}
      self.assertEqual(self.run_store('put', payload=entry).returncode, 0)
      self.assertEqual(self.run_store('close', flag, 'done').returncode, 0)
    result = self.run_store('history')
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual({row['key']: row['body'] for row in json.loads(result.stdout)},
                     {'code': '[redacted]', 'codes': '[redacted]'})
    history = self.home/STATE/'history'
    for path in history.glob('*.json'):
      row = json.loads(path.read_text())
      self.assertEqual(row['summary'], 'Verification notification')
      self.assertEqual(row['body'], '[redacted]')
      for secret in ('938271', '&#57;38271', '938 271', '/etc/passwd'):
        self.assertNotIn(secret, path.read_text())
      self.assertEqual(path.stat().st_mode & 0o777, 0o600)
    self.assertEqual((self.home/STATE).stat().st_mode & 0o777, 0o700)
  def test_exec_argv_and_glyph_persist_through_restore_and_history(self):
    # A toast restored after a shell restart (an update restarts the shell
    # under its own installer toasts) must click through like the live one.
    argv = json.dumps(['omarchy-update'])
    entry = {
        'key': 'update',
        'app': 'Omarchy',
        'summary': 'Update available',
        'body': 'Click to update',
        'glyph': '\uf0f3',
        'execArgv': argv,
    }
    self.assertEqual(self.run_store('put', payload=entry).returncode, 0)
    restored = json.loads(self.run_store('restore').stdout)[0]
    self.assertEqual(restored['execArgv'], argv)
    self.assertEqual(restored['glyph'], '\uf0f3')
    self.assertEqual(self.run_store('close', 'update', 'dismissed').returncode, 0)
    history = json.loads(self.run_store('history').stdout)
    self.assertEqual(len(history), 1)
    self.assertEqual(history[0]['execArgv'], argv)
    self.assertEqual(history[0]['glyph'], '\uf0f3')
  def test_exec_argv_is_validated_on_write_and_read(self):
    long_total = json.dumps(['run'] + ['x' * 4000] * 9)
    cases = {
        'not-json': '{"omarchy-update"',
        'not-a-list': json.dumps('omarchy-update'),
        'empty': json.dumps([]),
        'too-many': json.dumps(['echo'] + ['x'] * 32),
        'non-string': json.dumps(['echo', 1]),
        'blank-program': json.dumps(['', 'x']),
        'option-program': json.dumps(['--help']),
        'long-argument': json.dumps(['echo', 'x' * 4097]),
        'long-total': long_total,
        'nul': json.dumps(['echo', 'a\x00b']),
    }
    self.assertEqual(self.run_store('restore').returncode, 0)
    live = self.home/STATE/'live'
    for key, value in cases.items():
      with self.subTest(case=key):
        if len(json.dumps({'key': key, 'execArgv': value})) < 65536:
          self.assertEqual(self.run_store('put', payload={'key': key, 'execArgv': value}).returncode, 0)
          self.assertEqual(json.loads((live/f'{key}.json').read_text())['execArgv'], '')
        (live/f'{key}.json').write_text(json.dumps({'key': key, 'execArgv': value}))
    rows = {row['key']: row for row in json.loads(self.run_store('restore').stdout)}
    for key in cases:
      with self.subTest(case=key):
        self.assertEqual(rows[key]['execArgv'], '')
    valid = json.dumps(['notify-send', '-a', 'x', 'y' * 4096])
    self.assertEqual(self.run_store('put', payload={'key': 'valid', 'execArgv': valid}).returncode, 0)
    self.assertEqual(json.loads(self.run_store('restore').stdout)[-1]['execArgv'], valid)
  def test_glyph_is_bounded(self):
    for key, glyph, kept in (('short', '\U000f0001', True), ('word', 'abcdefghijklmnop', True),
                             ('long', 'a' * 17, False), ('control', '\uf0f3\n', False),
                             ('escape', '\x1b[31m', False), ('empty', '', False)):
      with self.subTest(case=key):
        self.assertEqual(self.run_store('put', payload={'key': key, 'glyph': glyph}).returncode, 0)
        row = json.loads((self.home/STATE/'live'/f'{key}.json').read_text())
        self.assertEqual(row.get('glyph'), glyph if kept else None)
  def test_redaction_clears_exec_argv_and_glyph(self):
    entry = {'key': 'otp', 'body': 'Your code is 938271', 'glyph': '\uf023',
             'execArgv': json.dumps(['xdg-open', 'https://example.com/938271'])}
    self.assertEqual(self.run_store('put', payload=entry).returncode, 0)
    row = json.loads(self.run_store('restore').stdout)[0]
    self.assertNotIn('execArgv', row)
    self.assertNotIn('glyph', row)
    self.assertEqual(row['body'], '[redacted]')
  def test_ordinary_restore_and_off(self):
    self.assertEqual(self.run_store('put',payload={'key':'n1','body':'ordinary message'}).returncode,0)
    self.assertEqual(json.loads(self.run_store('restore').stdout)[0]['body'],'ordinary message')
    self.assertEqual(self.run_store('policy',payload={'historyHours':0}).returncode,0)
    self.run_store('close','n1','done')
    self.assertEqual(json.loads(self.run_store('history').stdout),[])
  def test_symlink_and_oversize(self):
    self.run_store('restore')
    victim=self.home/'victim';victim.write_text('untouched')
    live=self.home/STATE/'live'
    (live/'n1.json').symlink_to(victim)
    self.assertNotEqual(self.run_store('put',payload={'key':'n1','body':'x'}).returncode,0)
    self.assertEqual(victim.read_text(),'untouched')
    self.assertNotEqual(self.run_store('put',payload={'key':'../../escape','body':'x'}).returncode,0)
    self.assertNotEqual(self.run_store('put',payload={'key':'n2','body':'x'*70000}).returncode,0)
  def test_directory_symlink(self):
    root=self.home/'.local/state/omarchy';root.mkdir(parents=True)
    target=self.home/'victim';target.mkdir()
    (root/'notifications').symlink_to(target,target_is_directory=True)
    self.assertNotEqual(self.run_store('put',payload={'key':'n1'}).returncode,0)
    self.assertEqual(list(target.iterdir()),[])
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
    self.assertEqual(self.run_store('restore').returncode, 0)
    state = self.home/STATE
    stamp = int(time.time() * 1000)
    for i, (app, summary, body) in enumerate(cases):
      # Real production rows carry numbered keys and derived lowercase
      # product group keys; neither belongs in the content detector.
      entry = {'key': f'notification-{4123+i}', 'app': app, 'summary': summary,
               'body': body, 'rawBody': body, 'bodyLine': body,
               'groupKey': app.lower(), 'source': app, 'urgency': 1}
      with self.subTest(app=app, body=body):
        self.assertEqual(self.run_store('put', payload=entry).returncode, 0)
        live = state/'live'/f'{entry["key"]}.json'
        self.assertEqual(json.loads(live.read_text()), entry)
        history = state/'history'/f'{stamp}-{entry["key"]}.json'
        for path in (live, history):
          path.write_text(json.dumps(entry))
          path.chmod(0o644)
        for verb in ('restore', 'history'):
          result = self.run_store(verb)
          self.assertEqual(result.returncode, 0, result.stderr)
          row = next(row for row in json.loads(result.stdout) if row['key'] == entry['key'])
          self.assertEqual(row, entry)
        for path in (live, history):
          self.assertEqual(json.loads(path.read_text()), entry)
          self.assertEqual(path.stat().st_mode & 0o777, 0o600)

  def test_raw_and_legacy_recognised_codes_redact_whole_row(self):
    cases = [
        {'body': 'Your code is 938271'},
        {'body': 'Your code is G-938271'},
        {'body': 'Your OTP is 938 271'},
        {'body': 'Your OTP is 938\t271'},
        {'body': 'Your OTP is 938\n271'},
        {'body': 'Your OTP is 938\u00a0271'},
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
    self.assertEqual(self.run_store('restore').returncode, 0)
    state = self.home/STATE
    stamp = int(time.time() * 1000)
    for mode in ('put', 'legacy-live', 'legacy-history'):
      expected = {}
      for i, text in enumerate(cases):
        key = f'{mode}-{i}'
        entry = {'key': key, 'urgency': 1, 'app': 'alternate-secret',
                 'groupKey': 'alternate-secret', 'bodyLine': 'alternate-secret',
                 'source': 'alternate-secret', 'appIcon': 'alternate-secret',
                 'replyTo': 'alternate-secret', 'image': '/etc/passwd', **text}
        expected[key] = {'key': key, 'urgency': 1,
                         'summary': 'Verification notification', 'body': '[redacted]',
                         'rawBody': '[redacted]', 'bodyLine': '[redacted]'}
        directory = 'history' if mode == 'legacy-history' else 'live'
        name = f'{stamp}-{key}.json' if directory == 'history' else f'{key}.json'
        path = state/directory/name
        with self.subTest(mode=mode, text=text):
          if mode == 'put':
            result = self.run_store('put', payload=entry)
            self.assertEqual(result.returncode, 0, result.stderr)
            # Check before restore: a migration must not mask a put leak.
            self.assertEqual(json.loads(path.read_text()), expected[key])
          else:
            path.write_text(json.dumps(entry))
            path.chmod(0o644)
      verb = 'history' if mode == 'legacy-history' else 'restore'
      result = self.run_store(verb)
      self.assertEqual(result.returncode, 0, result.stderr)
      rows = {row['key']: row for row in json.loads(result.stdout)}
      for key, clean in expected.items():
        with self.subTest(mode=mode, key=key):
          self.assertEqual(rows[key], clean)
          name = f'{stamp}-{key}.json' if mode == 'legacy-history' else f'{key}.json'
          path = state/('history' if mode == 'legacy-history' else 'live')/name
          self.assertEqual(json.loads(path.read_text()), clean)
          self.assertEqual(path.stat().st_mode & 0o777, 0o600)

class Network(unittest.TestCase):
  def test_destinations(self):
    for u in ['file:///etc/passwd','https://u:p@example.com','https://example.com:22','https://127.1','http://169.254.169.254','https://[::1]','https://host.local','https://example.com/%250a']:
      with self.assertRaises(ValueError):net.parse_url(u)
  def test_dns(self):
    for ip in ['127.0.0.1','10.0.0.1','172.16.0.1','192.168.1.1','169.254.169.254','0.0.0.0','224.0.0.1','::1','fe80::1','fc00::1','::','::ffff:192.168.1.1']:
      family=socket.AF_INET6 if ':' in ip else socket.AF_INET
      answers=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443)),(family,socket.SOCK_STREAM,6,'',(ip,443))]
      with patch.object(socket,'getaddrinfo',return_value=answers):
        with self.assertRaises(ValueError,msg=ip):net.resolve_public_host('example.com',443)
  def test_no_reresolve_and_tls_hostname(self):
    answer=(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))
    sock=MagicMock();ctx=MagicMock()
    with patch.object(socket,'socket',return_value=sock),patch.object(socket,'getaddrinfo',side_effect=AssertionError('second DNS lookup')),patch.object(net.ssl,'create_default_context',return_value=ctx):
      c=net.PinnedHTTPConnection('example.com',443,answer,time.monotonic()+net.REQUEST_DEADLINE);c.connect()
    sock.connect.assert_called_once_with(('93.184.216.34',443))
    ctx.wrap_socket.assert_called_once_with(sock,server_hostname='example.com')
  def test_redirects(self):
    for target in ['http://127.0.0.1','http://10.0.0.1','file:///etc/passwd','https://user@example.com','https://example.com:22','\nhttps://example.com']:
      with patch.object(net,'fetch_once',return_value=(None,target)):
        with self.assertRaises(ValueError,msg=target):net.fetch('https://example.com')
    with patch.object(net,'fetch_once',return_value=(None,'/again')) as f:
      with self.assertRaises(ValueError):net.fetch('https://example.com')
      self.assertEqual(f.call_count,4)
  def test_stream_limit(self):
    response=MagicMock(status=200)
    response.getheader.side_effect=lambda k,d=None: d
    response.read1.return_value=b'x'*11
    conn=MagicMock();conn.getresponse.return_value=response
    with patch.object(net,'resolve_public_answers',return_value=()),patch.object(net,'PinnedHTTPConnection',return_value=conn):
      with self.assertRaises(ValueError):net.fetch_once('https://example.com',10)
    conn.close.assert_called_once()

class Replies(unittest.TestCase):
  def setUp(self):self.k=module('kdeconnect')
  def test_ambiguous_and_empty(self):
    a=dict(appName='Chat',text='hello',ticker='',replyId='1',path='/modules/kdeconnect/devices/device/notifications/1')
    with patch.object(self.k,'listing',return_value=[a,a]):self.assertIsNone(self.k.find('Chat','hello'))
    with patch.object(self.k,'listing',return_value=[a]):
      self.assertEqual(self.k.find('Chat','hello'),a)
      self.assertIsNone(self.k.find('Other','hello'))
      self.assertIsNone(self.k.find('Chat','something else'))
      self.assertIsNone(self.k.find('Chat',''))
  def test_path(self):
    self.assertTrue(self.k.valid_path('/modules/kdeconnect/devices/device_1/notifications/12'))
    for p in ['fake:1','/org/other','--help','; rm -rf ~','$(touch /tmp/pwned)','`touch /tmp/pwned`','/modules/kdeconnect/devices/x/notifications/1\n']:
      self.assertFalse(self.k.valid_path(p))
  def test_command_text_is_data(self):
    payloads=['; rm -rf ~','$(touch /tmp/pwned)','`touch /tmp/pwned`','--help','quotes"\n\\']
    target='/modules/kdeconnect/devices/device/notifications/1'
    for text in payloads:
      with patch.object(sys,'argv',['helper','reply',target,text,'Chat','body']),patch.object(self.k,'find',return_value={'path':target}),patch.object(self.k.subprocess,'run',return_value=MagicMock(returncode=0)) as run:
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(self.k.main(),0)
        self.assertEqual(run.call_args_list[0].args[0][-1],text)
        self.assertEqual(run.call_args_list[0].args[0][2],"--")
        self.assertNotIn('shell',run.call_args_list[0].kwargs)
  def test_demo_cannot_impersonate_a_real_phone_app(self):
    with tempfile.TemporaryDirectory() as temp:
      fixture = Path(temp) / 'notification.json'
      files.write_json(fixture, {'token': 'a' * 32, 'created': time.time(),
                                'appName': 'WhatsApp', 'title': 'Demo sender', 'text': 'hello'})
      with patch.object(self.k, 'FIXTURE', fixture), patch.object(self.k, 'listing', return_value=[]):
        self.assertIsNone(self.k.find('WhatsApp', 'Demo sender: hello'))
        note = self.k.find('Omarchy reply demo', 'Demo sender: hello')
        self.assertIsNotNone(note)
        self.assertEqual(note['appName'], 'Omarchy reply demo')

  def test_demo_rejects_replaced_and_expired_sessions(self):
    with tempfile.TemporaryDirectory() as temp:
      fixture = Path(temp) / 'notification.json'
      reply = Path(temp) / 'reply.json'
      current = {'token': 'a' * 32, 'created': time.time(), 'title': 'Demo sender', 'text': 'hello'}
      files.write_json(fixture, current)
      with patch.object(self.k, 'FIXTURE', fixture), patch.object(self.k, 'REPLY_LOG', reply), \
              patch.object(self.k, 'listing', return_value=[]):
        original = self.k.find('Omarchy reply demo', 'Demo sender: hello')
        self.assertIsNotNone(original)
        current['token'] = 'b' * 32
        files.write_json(fixture, current)
        with patch.object(sys, 'argv', ['helper', 'reply', original['path'], 'must not be sent',
                                       'Omarchy reply demo', 'Demo sender: hello']):
          self.assertEqual(self.k.main(), 1)
        self.assertFalse(reply.exists())
        current['created'] = time.time() - self.k.FIXTURE_MAX_AGE - 1
        files.write_json(fixture, current)
        self.assertIsNone(self.k.find('Omarchy reply demo', 'Demo sender: hello'))

class Icons(unittest.TestCase):
  def test_icon_hint_traversal(self):
    icon=module('icon')
    with patch.object(icon.glob,'glob',return_value=[]) as glob:
      icon.from_icon_theme(['../../../../etc/passwd','/etc/passwd','*','--help'])
      for call in glob.call_args_list:
        self.assertNotIn('../',call.args[0])
  def test_svg_rejected(self):
    icon=module('icon')
    with tempfile.TemporaryDirectory() as temp,patch.object(icon,'CACHE',temp),patch.object(icon,'get',return_value=(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>','https://example.com')):
      self.assertIsNone(icon.fetch_site('example.com','dark'))
      self.assertEqual(list(Path(temp).iterdir()),[])
  # PR 4 review finding 2 (P2): a remote cache hit used to be trusted purely
  # because the path was inside CACHE and existed, so a cache entry written
  # by a pre-hardening build - most dangerously a raw remote SVG - would be
  # handed straight to the unsandboxed UI on every later run, bypassing the
  # raster validation a fresh fetch goes through. safe_cached_remote_icon()
  # now requires a cache hit to be exactly the validated raster this code
  # itself would have produced.
  def test_review_p2_legacy_remote_svg_cache_rejected(self):
    icon=module('icon')
    with tempfile.TemporaryDirectory() as temp:
      legacy=os.path.join(temp,'web-example-com-dark.svg')
      with open(legacy,'w') as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg"><script>evil()</script></svg>')
      index={'example.com':{'dark':legacy}}
      with patch.object(icon,'CACHE',temp), \
           patch.object(icon,'INDEX',os.path.join(temp,'index.json')), \
           patch.object(icon,'load_index',return_value=index), \
           patch.object(icon,'save_index') as save_index, \
           patch.object(icon,'fetch_site',return_value=None) as fetch_site:
        args=argparse.Namespace(source='example.com',app_icon='',app='',key='',
                                scheme='dark',fetch=True)
        with patch.object(icon,'from_config',return_value=None), \
             patch.object(icon,'from_icon_theme',return_value=None), \
             patch.object(icon,'from_desktop_entries',return_value=None):
          hit,how=icon.resolve(args)
      self.assertNotEqual(hit,legacy)
      self.assertFalse(os.path.exists(legacy),'poisoned cache entry must be deleted, not reused')
      fetch_site.assert_called_once_with('example.com','dark')
      self.assertTrue(save_index.called)
  def test_review_p2_local_theme_svg_preserved(self):
    # A trusted local theme SVG is a completely separate path
    # (from_icon_theme) and must be unaffected by remote-cache hardening.
    icon=module('icon')
    with tempfile.TemporaryDirectory() as temp:
      theme_dir=os.path.join(temp,'hicolor','scalable','apps')
      os.makedirs(theme_dir)
      svg_path=os.path.join(theme_dir,'kitty.svg')
      with open(svg_path,'w') as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
      with patch.object(icon,'ICON_DIRS',[temp]):
        self.assertEqual(icon.from_icon_theme(['kitty']),svg_path)

class Raster(unittest.TestCase):
  def test_valid_raster_and_dimension_limit(self):
    if not have_magick():
      self.skipTest("imagemagick is not installed")
    import notification_images
    icon=module('icon')
    for size,accepted in [((256,256),True),((2049,1),False)]:
      with tempfile.TemporaryDirectory() as temp,patch.object(icon,'CACHE',temp),patch.object(icon,'get',return_value=(png(size,(0,0,0,255)),'https://example.com')):
        path=icon.fetch_site('example.com','dark')
        self.assertEqual(bool(path),accepted)
        if path:
          data=Path(path).read_bytes()
          self.assertEqual(notification_images.sniff(data),'PNG')
          self.assertLessEqual(max(notification_images.frames(data,'PNG')[0]),128)
          self.assertEqual(Path(path).stat().st_mode&0o777,0o600)

  def test_only_sniffed_rasters_reach_a_coder(self):
    if not have_magick():
      self.skipTest("imagemagick is not installed")
    import subprocess
    import notification_images
    svg=b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64"/></svg>'
    msl=b'<?xml version="1.0"?><image><read filename="/etc/passwd"/></image>'
    anim=subprocess.run(['magick','-size','8x8','xc:red','xc:blue','-loop','0','webp:-'],stdout=subprocess.PIPE,check=True).stdout
    for data in (svg,msl,b'not an image',b'\x89PNG\r\n\x1a\ntruncated',anim):
      with self.assertRaises(ValueError):
        notification_images.decode(data,('PNG','JPEG','WEBP','ICO'),2048,2048*2048,128)
    ico=subprocess.run(['magick','-size','64x64','xc:red','-define','icon:auto-resize=16,32,64','ico:-'],stdout=subprocess.PIPE,check=True).stdout
    self.assertEqual(notification_images.decode(ico,('ICO',),2048,2048*2048,128)[:2],(64,64))

  def test_local_icons_normalise_to_one_canvas(self):
    if not have_magick():
      self.skipTest("imagemagick is not installed")
    import notification_images
    icon=module('icon')
    # A small opaque square and a padded transparent plus come out the same
    # canvas size; the opaque one is inset less and has its corners cleared.
    opaque=png((16,16),(200,40,40,255))
    glyph=notification_images.encode_png(64,64,b''.join(
      bytes((0,0,0,255) if 16<=x<48 and 16<=y<48 and (28<=x<36 or 28<=y<36) else (0,0,0,0)) for y in range(64) for x in range(64)))
    with tempfile.TemporaryDirectory() as temp,patch.object(icon,'CACHE',temp):
      for name,data,mono in (('opaque.png',opaque,False),('glyph.png',glyph,True)):
        source=Path(temp)/name;source.write_bytes(data)
        out=icon.normalise(str(source))
        self.assertTrue(out.endswith('-mono.png')==mono,out)
        w,h,rgba=notification_images.decode(Path(out).read_bytes(),('PNG',),128,128*128,128)
        self.assertEqual((w,h),(128,128))
        self.assertEqual(rgba[(64*128+64)*4+3],255)
      corner=notification_images.decode(Path(icon.normalise(str(Path(temp)/'opaque.png'))).read_bytes(),('PNG',),128,128*128,128)[2]
      self.assertEqual(corner[(4*128+4)*4+3],0)
      self.assertIsNone(icon.normalise(str(Path(temp)/'missing.png')))

if __name__=='__main__':unittest.main()
