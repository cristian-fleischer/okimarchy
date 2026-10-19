"""Real Bubblewrap namespaces: what each helper kind can see, reach and write.

Skipped when Bubblewrap is missing or cannot create namespaces here (a
container without user namespaces); the helper-mode tests cover the policy
around it with the sandbox mocked.
"""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from urllib.parse import quote
from unittest.mock import patch

from support import HELPERS, load_helper

DEMO_APP = "Omarchy reply demo"


class Sandbox(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    runner = load_helper("run", "sandbox_probe_runner")
    bwrap = runner.bubblewrap_path()
    if not bwrap:
      raise unittest.SkipTest("bubblewrap is not installed")
    if not runner.probe_sandbox(bwrap):
      raise unittest.SkipTest("bubblewrap cannot create a sandbox here")

  def setUp(self):
    self.temp = tempfile.TemporaryDirectory(prefix="omarchy-notification-sandbox-")
    self.r = load_helper("run", "sandbox_runner")
    self.r.HOME_DIR = Path(self.temp.name) / "home"
    self.r.HOME_DIR.mkdir()
    self.r.STATE = self.r.HOME_DIR / ".local/state/omarchy/notifications"
    self.bwrap = self.r.bubblewrap_path()
    self.secret = self.r.HOME_DIR / ".ssh/id_test"
    self.secret.parent.mkdir()
    self.secret.write_text("synthetic secret")

  def tearDown(self):
    self.temp.cleanup()

  def run_inside(self, command, code):
    cut = command.index("/usr/bin/python3")
    subprocess.run(command[:cut] + ["/usr/bin/python3", "-c", code], check=True, timeout=10)

  def test_only_the_store_writes_state_and_neither_has_a_network(self):
    for kind in ("store", "icon"):
      with self.subTest(kind=kind):
        command = self.r.sandbox_command(kind, [], self.bwrap, os.environ)
        check = self.r.STATE / ("check-" + kind)
        writes = kind == "store"
        self.run_inside(command, f"""import os,socket
assert not os.path.exists({str(self.secret)!r})
assert not os.path.exists({str(HELPERS.resolve().parents[3])!r})
assert os.path.isfile('/opt/omarchy-notifications/{kind}')
s=socket.socket();s.settimeout(.2)
assert s.connect_ex(('1.1.1.1',443)) != 0
try:
  open({str(check)!r}, 'w').write('ok')
except OSError:
  assert not {writes!r}
else:
  assert {writes!r}
""")
        self.assertEqual(check.exists(), writes)

  def test_kdeconnect_gets_the_bus_and_only_the_demo_directory_it_asked_for(self):
    self.r.STATE.mkdir(parents=True)
    (self.r.STATE / "live").mkdir()
    (self.r.STATE / "live/n1.json").write_text("{}")
    runtime = self.r.HOME_DIR / "private-runtime"
    runtime.mkdir(mode=0o700)
    bus = runtime / "session bus"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as fixture:
      fixture.bind(str(bus))
      address = "unix:path=" + quote(str(bus), safe="/") + ",guid=" + "a" * 32
      bus_environment = {"DBUS_SESSION_BUS_ADDRESS": address, "XDG_RUNTIME_DIR": str(runtime)}
      demo = self.r.STATE / "reply-demo"
      demo.mkdir(mode=0o700)
      demo_note = demo / "notification.json"
      demo_note.write_text('{"synthetic":true}')
      with patch.dict(os.environ, bus_environment):
        command = self.r.sandbox_command("kdeconnect", [], self.bwrap, os.environ)
      self.run_inside(command, f"""import os
from pathlib import Path
assert os.environ['DBUS_SESSION_BUS_ADDRESS'] == {address!r}
assert os.environ['XDG_RUNTIME_DIR'] == {str(runtime)!r}
assert Path({str(bus)!r}).is_socket()
assert not Path('/run/user/{os.getuid()}/bus').exists()
""")
      for args, readable, writable in [
          (["find", "Chat", "hello"], False, False),
          (["find", DEMO_APP, "hello"], True, False),
          (["reply", "demo:" + "a" * 32, "reply", DEMO_APP, "hello"], True, True),
      ]:
        with self.subTest(args=args):
          with patch.dict(os.environ, bus_environment):
            command = self.r.sandbox_command("kdeconnect", args, self.bwrap, os.environ)
          self.run_inside(command, f"""from pathlib import Path
assert not Path({str(self.secret)!r}).exists()
assert not Path({str(self.r.STATE / 'live/n1.json')!r}).exists()
assert Path({str(demo_note)!r}).exists() == {readable!r}
try:
    Path({str(demo / 'reply.json')!r}).write_text('synthetic reply')
except OSError:
    assert not {writable!r}
else:
    assert {writable!r}
""")
      for invalid in ("", "tcp:host=localhost,port=1", "unix:abstract=fixture",
                      "unix:path=relative", address + ";unix:path=/other",
                      "unix:path=" + str(bus) + ",path=/other"):
        with self.subTest(address=invalid), \
                patch.dict(os.environ, {"DBUS_SESSION_BUS_ADDRESS": invalid,
                                        "XDG_RUNTIME_DIR": str(runtime)}), \
                self.assertRaises((RuntimeError, ValueError)):
          self.r.sandbox_command("kdeconnect", [], self.bwrap, os.environ)


if __name__ == "__main__":
  unittest.main()
