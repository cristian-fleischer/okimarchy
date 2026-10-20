"""Real Bubblewrap namespaces: what each helper kind can see, reach and write.

Skipped when Bubblewrap is missing or cannot create namespaces here (a
container without user namespaces); the helper-mode tests cover the policy
around it with the sandbox mocked.
"""
import json
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

  def test_the_store_writes_only_its_state_and_has_no_network(self):
    command = self.r.sandbox_command("store", [], self.bwrap, os.environ)
    check = self.r.STATE / "check-store"
    outside = self.r.HOME_DIR / "check-outside"
    self.run_inside(command, f"""import os,socket
assert not os.path.exists({str(self.secret)!r})
assert not os.path.exists({str(HELPERS.resolve().parents[3])!r})
assert os.path.isfile('/opt/omarchy-notifications/store')
s=socket.socket();s.settimeout(.2)
assert s.connect_ex(('1.1.1.1',443)) != 0
open({str(check)!r}, 'w').write('ok')
try:
  open({str(outside)!r}, 'w').write('ok')
except OSError:
  pass
""")
    self.assertTrue(check.exists())
    self.assertFalse(outside.exists())

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


class SandboxEscapes(unittest.TestCase):
  """Run a probe inside each real sandbox, as if its helper were compromised."""

  PROBE = r"""
import ctypes, json, os, socket
out = {}
def attempt(name, call):
  try:
    call(); out[name] = "ALLOWED"
  except (OSError, ValueError):
    out[name] = "blocked"
attempt("write-usr", lambda: open("/usr/omarchy-escape", "w"))
attempt("host-root", lambda: open("/proc/1/root" + SECRET).read())
attempt("secret", lambda: open(SECRET).read())
attempt("inherited-fd", lambda: os.read(FD, 10))
attempt("abstract-socket", lambda: socket.socket(socket.AF_UNIX).connect(ABSTRACT))
attempt("unix-socket", lambda: socket.socket(socket.AF_UNIX))
attempt("signal-host", lambda: os.kill(HOSTPID, 0))
attempt("tty", lambda: os.open("/dev/tty", os.O_RDWR))
s = socket.socket(); s.settimeout(0.3)
attempt("loopback", lambda: s.connect(ADDRESS))
print(json.dumps(out))
"""

  @classmethod
  def setUpClass(cls):
    cls.runner = load_helper("run")
    cls.bwrap = cls.runner.bubblewrap_path()
    if not cls.bwrap or not cls.runner.probe_sandbox(cls.bwrap):
      raise unittest.SkipTest("bubblewrap sandbox is not operational")

  def probe(self, args):
    with tempfile.TemporaryDirectory() as temp:
      home = Path(temp)
      secret = home / "secret"
      secret.write_text("secret")
      abstract = socket.socket(socket.AF_UNIX)
      abstract.bind("\0omarchy-escape-%d" % os.getpid())
      abstract.listen()
      listener = socket.socket()
      listener.bind(("127.0.0.1", 0))
      listener.listen()
      # An inheritable descriptor the launcher holds; Popen closes it on the
      # way into every helper, as run_supervised does.
      fd = os.open(secret, os.O_RDONLY)
      os.set_inheritable(fd, True)
      try:
        with patch.object(self.runner, "HOME_DIR", home), patch.object(self.runner, "STATE", home / "state"):
          cmd = self.runner.sandbox_command("store", args, self.bwrap, {})
        cmd = cmd[:cmd.index("/usr/bin/python3")]
        code = (self.PROBE.replace("SECRET", repr(str(secret))).replace("FD", str(fd))
                .replace("ABSTRACT", repr("\0omarchy-escape-%d" % os.getpid()))
                .replace("HOSTPID", str(os.getpid())).replace("ADDRESS", repr(listener.getsockname())))
        result = subprocess.run(cmd + ["/usr/bin/python3", "-c", code], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return json.loads(result.stdout)
      finally:
        os.close(fd)
        abstract.close()
        listener.close()

  def test_the_store_sandbox_reaches_nothing(self):
    found = self.probe(["restore"])
    self.assertEqual({k for k, v in found.items() if v == "ALLOWED"}, {"unix-socket"}, found)


if __name__ == "__main__":
  unittest.main()
