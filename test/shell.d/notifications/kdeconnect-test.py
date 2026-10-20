"""The KDE Connect reply bridge (shell/plugins/notifications/helpers/kdeconnect).

Run by notifications-test.sh with a scratch HOME. The helper is an
extensionless executable, so it is loaded through a source loader to patch
its module globals without running main().
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

HELPER = Path(__file__).resolve().parents[3] / "shell/plugins/notifications/helpers/kdeconnect"


def load_helper():
  loader = importlib.machinery.SourceFileLoader("notification_kdeconnect", str(HELPER))
  spec = importlib.util.spec_from_loader(loader.name, loader)
  module = importlib.util.module_from_spec(spec)
  loader.exec_module(module)
  return module


class Replies(unittest.TestCase):
  PATH = '/modules/kdeconnect/devices/device/notifications/1'

  def setUp(self):
    self.k = load_helper()

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
    self.k.write_json(str(fixture), dict({'token': 'a' * 32, 'created': time.time(),
                                          'title': 'Demo sender', 'text': 'hello'}, **row))
    return str(fixture)

  def test_demo_cannot_impersonate_a_real_phone_app(self):
    with tempfile.TemporaryDirectory() as temp, \
            patch.object(self.k, 'FIXTURE', self.demo(temp, appName='WhatsApp')), \
            patch.object(self.k, 'listing', return_value=[]):
      self.assertIsNone(self.k.find('WhatsApp', 'Demo sender: hello'))
      self.assertEqual(self.k.find('Omarchy reply demo', 'Demo sender: hello')['appName'], 'Omarchy reply demo')

  def test_demo_rejects_replaced_and_expired_sessions(self):
    with tempfile.TemporaryDirectory() as temp:
      reply = Path(temp) / 'reply.json'
      with patch.object(self.k, 'FIXTURE', self.demo(temp)), patch.object(self.k, 'REPLY_LOG', str(reply)), \
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

  def test_a_demo_reply_is_saved_privately(self):
    with tempfile.TemporaryDirectory() as temp:
      reply = Path(temp) / 'state' / 'reply.json'
      with patch.object(self.k, 'FIXTURE', self.demo(temp)), patch.object(self.k, 'REPLY_LOG', str(reply)), \
              patch.object(self.k, 'listing', return_value=[]), contextlib.redirect_stdout(io.StringIO()):
        path = self.k.find('Omarchy reply demo', 'Demo sender: hello')['path']
        with patch.object(sys, 'argv', ['helper', 'reply', path, 'hi', 'Omarchy reply demo', 'Demo sender: hello']):
          self.assertEqual(self.k.main(), 0)
      self.assertEqual(self.k.read_json(str(reply))['text'], 'hi')
      self.assertEqual(reply.stat().st_mode & 0o777, 0o600)
      self.assertEqual(reply.parent.stat().st_mode & 0o777, 0o700)

  def test_fixture_reads_refuse_symlinks_and_oversize(self):
    with tempfile.TemporaryDirectory() as temp:
      real = Path(temp) / 'real.json'
      real.write_text('{"token": "x"}')
      link = Path(temp) / 'link.json'
      link.symlink_to(real)
      self.assertIsNone(self.k.read_json(str(link)))
      self.assertEqual(self.k.read_json(str(real)), {'token': 'x'})
      real.write_text('[' + '0,' * self.k.MAX_BYTES + '0]')
      self.assertIsNone(self.k.read_json(str(real)))
      with self.assertRaises(ValueError):
        self.k.write_json(str(link), {})
      self.assertEqual(real.read_text()[:2], '[0')


if __name__ == '__main__':
  unittest.main()
