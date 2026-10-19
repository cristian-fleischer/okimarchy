"""The previous notification service's state, sharing the store's directory.

Before the store moved in, Omarchy's notification service kept popups as
<ms>-<id>.json in ~/.local/state/omarchy/notifications/, history as
history/<ms>-<id>.json rows without a `key`, and sender images under images/.
The old shell can still write one more row before an update restarts it.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from support import HELPERS

STATE = ".local/state/omarchy/notifications"


def legacy_row(identifier, stamp):
  return {"id": identifier, "originalId": identifier, "app": "Old Service",
          "summary": "Legacy %d" % identifier, "body": "from before the store",
          "timestamp": stamp, "appIcon": "", "image": "images/%d-%d-image.png" % (stamp, identifier)}


class LegacyLayout(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory(prefix="omarchy-notification-legacy-")
    self.home = Path(self.temp.name)
    self.root = self.home / STATE
    self.env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1")

  def tearDown(self):
    self.temp.cleanup()

  def store(self, *args, payload=None):
    result = subprocess.run([sys.executable, str(HELPERS / "store"), *args],
                            input=json.dumps(payload) if payload is not None else "",
                            text=True, capture_output=True, env=self.env)
    self.assertEqual(result.returncode, 0, result.stderr)
    return result.stdout

  def write_legacy_state(self):
    stamp = int(time.time() * 1000)
    (self.root / "history").mkdir(parents=True)
    (self.root / "images").mkdir()
    (self.root / "images" / ("%d-7-image.png" % stamp)).write_bytes(b"\x89PNG")
    popup = self.root / ("%d-7.json" % stamp)
    popup.write_text(json.dumps(legacy_row(7, stamp)))
    old = self.root / "history" / ("%d-8.json" % (stamp - 1000))
    old.write_text(json.dumps(legacy_row(8, stamp - 1000)))
    old.chmod(0o644)
    return stamp, popup, old

  def test_keyless_history_is_dropped_and_never_surfaced(self):
    stamp, popup, old = self.write_legacy_state()
    self.store("put", payload={"key": "n1", "summary": "Current", "body": "kept"})
    self.store("close", "n1", "dismissed")
    history = json.loads(self.store("history", "10"))
    self.assertEqual([row["key"] for row in history], ["n1"])
    self.assertFalse(old.exists())
    self.assertEqual(json.loads(self.store("held", "10")), [])
    # Root-level popups are not the store's to read, so they stay until tidy.
    self.assertEqual(json.loads(self.store("restore")), [])
    self.assertTrue(popup.exists())

  def test_a_row_written_by_the_old_shell_mid_session_is_ignored(self):
    self.store("restore")
    stamp = int(time.time() * 1000)
    late = self.root / "history" / ("%d-9.json" % stamp)
    late.write_text(json.dumps(dict(legacy_row(9, stamp), closed_reason="snoozed")))
    stray = self.root / "live" / "9.json"
    stray.write_text(json.dumps(legacy_row(9, stamp)))
    self.assertEqual(json.loads(self.store("history")), [])
    self.assertEqual(json.loads(self.store("held")), [])
    self.assertEqual(json.loads(self.store("restore")), [])
    self.assertFalse(late.exists())
    self.assertFalse(stray.exists())

  def test_rows_must_carry_their_own_key_under_their_own_name(self):
    self.store("restore")
    stamp = int(time.time() * 1000)
    cases = {
        self.root / "live" / "a.json": {"key": "b", "body": "renamed"},
        self.root / "live" / "c.json": {"key": 3, "body": "numeric key"},
        self.root / "live" / "d.json": {"key": "../d", "body": "unsafe key"},
        self.root / "live" / "e.json": ["not", "an", "object"],
        self.root / "history" / ("%d-f.json" % stamp): {"key": "g", "body": "renamed"},
        self.root / "history" / ("%d-h.json" % (stamp // 10)): {"key": "h", "body": "short stamp"},
    }
    for path, row in cases.items():
      path.write_text(json.dumps(row))
    kept = self.root / "history" / ("%d-k.json" % stamp)
    kept.write_text(json.dumps({"key": "k", "body": "ours", "closed_reason": "silenced"}))
    self.assertEqual(json.loads(self.store("restore")), [])
    self.assertEqual([row["key"] for row in json.loads(self.store("history"))], ["k"])
    self.assertEqual([row["key"] for row in json.loads(self.store("held"))], ["k"])
    for path in cases:
      self.assertFalse(path.exists(), path.name)

  def test_tidy_removes_legacy_popups_and_images_only(self):
    stamp, popup, old = self.write_legacy_state()
    victim = self.home / "victim"
    victim.mkdir()
    (victim / "keep.png").write_bytes(b"keep")
    self.store("quiet-save", payload={"snoozes": {}, "silenced": False})
    self.store("policy", payload={"historyHours": 168})
    self.store("put", payload={"key": "n1", "body": "live"})
    output = self.store("tidy")
    self.assertRegex(output, r"^[0-9]+ history, [0-9]+ icons$")
    self.assertFalse(popup.exists())
    self.assertFalse((self.root / "images").exists())
    self.assertTrue((self.root / "quiet.json").exists())
    self.assertTrue((self.root / "policy.json").exists())
    self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                     ["history", "icons", "live", "policy.json", "quiet.json"])
    self.assertEqual([row["key"] for row in json.loads(self.store("restore"))], ["n1"])

    # A symlink where images/ was is unlinked, not followed.
    (self.root / "images").symlink_to(victim, target_is_directory=True)
    self.store("tidy")
    self.assertFalse((self.root / "images").exists())
    self.assertTrue((victim / "keep.png").exists())

  def test_old_layout_directories_are_tightened(self):
    self.write_legacy_state()
    for directory in (self.root, self.root / "history"):
      directory.chmod(0o755)
    self.store("restore")
    for directory in (self.root, self.root / "history", self.root / "live"):
      self.assertEqual(directory.stat().st_mode & 0o777, 0o700, directory)


if __name__ == "__main__":
  unittest.main()
