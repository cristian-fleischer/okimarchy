"""The sandbox launcher: status, policy, direct fallback and cancellation."""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import tempfile
import unittest
from unittest.mock import patch

from support import HELPERS, RUN, load_helper


@contextlib.contextmanager
def stdin_bytes(payload):
  saved = os.dup(0)
  read_fd, write_fd = os.pipe()
  try:
    os.write(write_fd, payload)
    os.close(write_fd)
    write_fd = -1
    os.dup2(read_fd, 0)
    os.close(read_fd)
    read_fd = -1
    yield
  finally:
    if read_fd >= 0:
      os.close(read_fd)
    if write_fd >= 0:
      os.close(write_fd)
    os.dup2(saved, 0)
    os.close(saved)


class HelperModes(unittest.TestCase):
  def setUp(self):
    self.runner = load_helper("run", "helper_modes_runner")
    self.temp = tempfile.TemporaryDirectory(prefix="omarchy-notification-helper-modes-")
    self.root = Path(self.temp.name)
    self.home = self.root / "home"
    self.home.mkdir()
    self.runner.HOME_DIR = self.home
    self.runner.STATE = self.home / ".local/state/omarchy/notifications"

  def tearDown(self):
    self.temp.cleanup()

  def status(self, required, bwrap, operational=False):
    with patch.object(self.runner, "bubblewrap_path", return_value=bwrap), \
            patch.object(self.runner, "probe_sandbox", return_value=operational) as probe:
      status, selected = self.runner.mode_status(required)
    self.assertEqual(selected, bwrap)
    self.assertEqual(probe.call_count, 1 if bwrap else 0)
    return status

  def test_status_reports_missing_broken_and_operational_modes_without_writes(self):
    missing = self.status(False, None)
    self.assertEqual(missing, {
        "bubblewrapAvailable": False,
        "sandboxOperational": False,
        "required": False,
        "unsandboxedFallback": True,
        "mode": "direct",
    })
    self.assertEqual(self.status(True, None)["mode"], "blocked")

    broken = self.status(False, "/usr/bin/bwrap", False)
    self.assertTrue(broken["bubblewrapAvailable"])
    self.assertFalse(broken["sandboxOperational"])
    self.assertEqual(broken["mode"], "direct")
    self.assertEqual(self.status(True, "/usr/bin/bwrap", False)["mode"], "blocked")

    available = self.status(False, "/usr/bin/bwrap", True)
    self.assertEqual(available["mode"], "sandboxed")
    self.assertTrue(available["unsandboxedFallback"])
    required = self.status(True, "/usr/bin/bwrap", True)
    self.assertEqual(required["mode"], "sandboxed")
    self.assertFalse(required["unsandboxedFallback"])
    probe_command = self.runner.sandbox_command("check", [], "/usr/bin/bwrap", {})
    self.assertEqual(probe_command[-1], "/usr/bin/true")
    self.assertFalse(self.runner.STATE.exists())

  def test_status_main_treats_absent_policy_as_opportunistic(self):
    with patch.object(self.runner, "bubblewrap_path", return_value=None), \
            contextlib.redirect_stdout(io.StringIO()) as stdout:
      result = self.runner.main(["status"], {})
    self.assertEqual(result, 0)
    self.assertEqual(json.loads(stdout.getvalue())["mode"], "direct")

  def test_main_refuses_a_malformed_policy_and_unknown_kinds_before_probing(self):
    # Capabilities and the per-kind wrapper names were plugin-era modes; icons
    # are resolved in the shell now.
    cases = [(["status"], {"OMARCHY_NOTIFICATIONS_REQUIRE_SANDBOX": "yes"})] + [
        (argv, {}) for argv in ([], ["capabilities"], ["action"], ["helper", "store"],
                                ["check"], ["status", "extra"], ["icon", "--key=x"],
                                ["icon", "--sender-image"])]
    for argv, environ in cases:
      with self.subTest(argv=argv, environ=environ), \
              patch.object(self.runner, "mode_status", side_effect=AssertionError("probed")), \
              contextlib.redirect_stdout(io.StringIO()) as stdout, \
              contextlib.redirect_stderr(io.StringIO()) as stderr:
        self.assertEqual(self.runner.main(argv, environ), 1)
      self.assertEqual(stdout.getvalue(), "")
      self.assertIn("helper unavailable", stderr.getvalue())

  def test_helpers_resolve_beside_the_real_launcher(self):
    self.assertEqual(self.runner.BASE, HELPERS.resolve())
    self.assertEqual(load_helper("run", "fresh_runner").STATE,
                     Path.home() / ".local/state/omarchy/notifications")
    self.assertEqual(self.runner.python_helper("store", ["restore"], str(self.runner.BASE))[-2:],
                     [str(HELPERS.resolve() / "store"), "restore"])
    self.assertEqual(self.runner.python_helper("kdeconnect", [])[-1],
                     "/opt/omarchy-notifications/kdeconnect")
    for kind in ("store", "kdeconnect"):
      self.assertTrue(os.access(HELPERS / kind, os.X_OK), kind)

  def test_symlinked_checkout_runs_the_store(self):
    # A dev OMARCHY_PATH can reach the plugin through a symlink. The
    # launcher must still find its siblings and, when sandboxed, mount
    # the real directory rather than the link.
    linked = self.root / "linked-omarchy"
    linked.symlink_to(HELPERS.parents[3], target_is_directory=True)
    launcher = linked / "shell/plugins/notifications/helpers/run"
    environment = {"HOME": str(self.home), "PATH": "/usr/bin", "LANG": "C.UTF-8",
                   "PYTHONDONTWRITEBYTECODE": "1"}
    status = subprocess.run([str(launcher), "status"], capture_output=True,
                            text=True, env=environment, timeout=20)
    self.assertEqual(status.returncode, 0, status.stderr)
    self.assertIn(json.loads(status.stdout)["mode"], ("sandboxed", "direct"))
    restored = subprocess.run([str(launcher), "store", "restore"], capture_output=True,
                              text=True, env=environment, timeout=60)
    self.assertEqual(restored.returncode, 0, restored.stderr)
    self.assertEqual(json.loads(restored.stdout), [])
    self.assertTrue((self.home / ".local/state/omarchy/notifications/live").is_dir())

  def make_effect_helper(self):
    plugin = self.root / "helpers"
    plugin.mkdir(exist_ok=True)
    helper = plugin / "store"
    helper.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "effect = Path(sys.argv[1])\n"
        "count = json.loads(effect.read_text())['count'] + 1 if effect.exists() else 1\n"
        "effect.write_text(json.dumps({\n"
        "    'count': count,\n"
        "    'stdin': sys.stdin.read(),\n"
        "    'home': os.environ.get('HOME'),\n"
        "    'path': os.environ.get('PATH'),\n"
        "    'lang': os.environ.get('LANG'),\n"
        "    'bad': sorted(k for k in (\n"
        "        'PYTHONPATH', 'LD_PRELOAD', 'AWS_SECRET_ACCESS_KEY',\n"
        "        'http_proxy', 'HTTPS_PROXY', 'XDG_CONFIG_HOME',\n"
        "        'OMARCHY_NOTIFICATIONS_REQUIRE_SANDBOX'\n"
        "    ) if k in os.environ),\n"
        "}))\n"
        "raise SystemExit(int(sys.argv[2]))\n"
    )
    self.runner.BASE = plugin
    return plugin

  def test_missing_or_broken_bwrap_runs_direct_once_with_stdin_and_a_clean_environment(self):
    self.make_effect_helper()
    source_environment = {
        "OMARCHY_NOTIFICATIONS_REQUIRE_SANDBOX": "0",
        "PYTHONPATH": "/attacker",
        "LD_PRELOAD": "/attacker/library.so",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "http_proxy": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "XDG_CONFIG_HOME": "/attacker/config",
    }
    for bwrap in (None, "/usr/bin/bwrap"):
      effect = self.root / ("missing.json" if bwrap is None else "broken.json")
      with self.subTest(bwrap=bwrap), \
              patch.object(self.runner, "bubblewrap_path", return_value=bwrap), \
              patch.object(self.runner, "probe_sandbox", return_value=False) as probe, \
              stdin_bytes(b"preserved stdin"):
        self.assertEqual(self.runner.main(["store", str(effect), "7"], source_environment), 7)
      self.assertEqual(probe.call_count, 1 if bwrap else 0)
      self.assertEqual(json.loads(effect.read_text()), {
          "count": 1, "stdin": "preserved stdin", "home": str(self.home),
          "path": "/usr/bin", "lang": "C.UTF-8", "bad": []})

  def test_required_mode_blocks_missing_and_broken_bwrap_before_helper_effect(self):
    self.make_effect_helper()
    for bwrap in (None, "/usr/bin/bwrap"):
      effect = self.root / ("required-missing.json" if bwrap is None else "required-broken.json")
      with self.subTest(bwrap=bwrap), \
              patch.object(self.runner, "bubblewrap_path", return_value=bwrap), \
              patch.object(self.runner, "probe_sandbox", return_value=False) as probe, \
              contextlib.redirect_stderr(io.StringIO()):
        result = self.runner.main(["store", str(effect), "0"],
                                  {"OMARCHY_NOTIFICATIONS_REQUIRE_SANDBOX": "1"})
      self.assertEqual(result, 1)
      self.assertFalse(effect.exists())
      self.assertEqual(probe.call_count, 1 if bwrap else 0)

  def test_actual_sandbox_failure_is_not_retried_direct(self):
    self.make_effect_helper()
    effect = self.root / "failed-sandbox.json"
    args = [str(effect), "23"]
    sandbox_argv = self.runner.python_helper("store", args, str(self.runner.BASE))
    with patch.object(self.runner, "bubblewrap_path", return_value="/usr/bin/bwrap"), \
            patch.object(self.runner, "probe_sandbox", return_value=True), \
            patch.object(self.runner, "sandbox_command", return_value=sandbox_argv), \
            stdin_bytes(b""):
      result = self.runner.main(["store", *args], {"OMARCHY_NOTIFICATIONS_REQUIRE_SANDBOX": "0"})
    self.assertEqual(result, 23)
    self.assertEqual(json.loads(effect.read_text())["count"], 1)

  def test_a_helper_stops_at_its_deadline(self):
    started = time.monotonic()
    with self.assertRaises(subprocess.TimeoutExpired):
      self.runner.run_supervised(["/usr/bin/sleep", "30"], {"PATH": "/usr/bin"}, 1)
    self.assertLess(time.monotonic() - started, 6)

  def test_child_unblocks_wrapper_signals_and_cancellation_kills_descendant(self):
    child_info = self.root / "child-info"
    leader_info = self.root / "leader-info"
    helper = self.root / "spawning-helper.py"
    child_code = (
        "import os, signal, sys, time\n"
        "from pathlib import Path\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])\n"
        "Path(sys.argv[1]).write_text(f'{os.getpid()},{int(signal.SIGTERM in mask)}')\n"
        "time.sleep(30)\n"
    )
    helper.write_text(
        "import os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        f"child_code = {child_code!r}\n"
        "Path(sys.argv[2]).write_text(str(os.getpid()))\n"
        "subprocess.Popen([sys.executable, '-c', child_code, sys.argv[1]])\n"
        "deadline = time.monotonic() + 5\n"
        "while not Path(sys.argv[1]).exists() and time.monotonic() < deadline:\n"
        "    time.sleep(.01)\n"
        "time.sleep(30)\n"
    )
    wrapper = str(RUN)
    harness_code = (
        "import importlib.machinery, importlib.util, signal, sys\n"
        f"sys.path.insert(0, {str(HELPERS)!r})\n"
        f"loader = importlib.machinery.SourceFileLoader('cancel_runner', {wrapper!r})\n"
        "spec = importlib.util.spec_from_loader('cancel_runner', loader)\n"
        "runner = importlib.util.module_from_spec(spec); loader.exec_module(runner)\n"
        "signal.pthread_sigmask(signal.SIG_UNBLOCK, "
        "[signal.SIGTERM, signal.SIGINT, signal.SIGHUP])\n"
        "runner.TERMINATE_GRACE = .1\n"
        "try:\n"
        f"    result = runner.run_supervised([{str(self.runner.PYTHON)!r}, "
        f"{str(helper)!r}, {str(child_info)!r}, {str(leader_info)!r}], "
        "runner.clean_environment(), 45)\n"
        "except runner.WrapperInterrupted as error:\n"
        "    result = 128 + error.signum\n"
        "raise SystemExit(result)\n"
    )
    harness = subprocess.Popen([sys.executable, "-c", harness_code],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               text=True)
    child_pid = None
    leader_pid = None
    forced_cleanup = False
    try:
      deadline = time.monotonic() + 5
      while not child_info.exists() and harness.poll() is None and time.monotonic() < deadline:
        time.sleep(.01)
      if not child_info.exists():
        if leader_info.exists():
          leader_pid = int(leader_info.read_text())
        harness.kill()
        harness.wait()
        forced_cleanup = True
        self.fail(harness.stderr.read())
      child_pid_text, blocked = child_info.read_text().split(",")
      child_pid = int(child_pid_text)
      self.assertEqual(blocked, "0")
      if leader_info.exists():
        leader_pid = int(leader_info.read_text())
      harness.send_signal(signal.SIGTERM)
      self.assertEqual(harness.wait(timeout=5), 128 + signal.SIGTERM)
      deadline = time.monotonic() + 5
      while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
        try:
          state = Path(f"/proc/{child_pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except OSError:
          break
        if state == "Z":
          break
        time.sleep(.01)
      if Path(f"/proc/{child_pid}").exists():
        state = Path(f"/proc/{child_pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        self.assertEqual(state, "Z")
    finally:
      if harness.poll() is None:
        harness.kill()
        harness.wait()
        forced_cleanup = True
      if forced_cleanup and leader_pid is not None:
        try:
          os.killpg(leader_pid, signal.SIGKILL)
        except ProcessLookupError:
          pass
      if child_pid is not None and Path(f"/proc/{child_pid}").exists():
        try:
          os.kill(child_pid, signal.SIGKILL)
        except ProcessLookupError:
          pass
      harness.stderr.close()

if __name__ == "__main__":
  unittest.main()
