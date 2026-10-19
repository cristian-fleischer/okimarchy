"""Sender images become self-contained data: URLs through `run icon --sender-image`."""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from support import RUN, have_magick, png
import notification_images as images

DATA_URL_PREFIX = "data:image/png;base64,"


class SenderImage(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    if not have_magick():
      raise unittest.SkipTest("imagemagick is not installed")

  def setUp(self):
    self.temp = tempfile.TemporaryDirectory(prefix="omarchy-notification-sender-image-")
    self.root = Path(self.temp.name)
    self.home = self.root / "home"
    self.inputs = self.root / "inputs"
    self.home.mkdir()
    self.inputs.mkdir()

  def tearDown(self):
    self.temp.cleanup()

  def launch(self, args, stdin=b"", required="0"):
    environment = {"HOME": str(self.home), "LANG": "C.UTF-8", "PATH": "/usr/bin",
                   "PYTHONDONTWRITEBYTECODE": "1", "OMARCHY_NOTIFICATIONS_REQUIRE_SANDBOX": required}
    return subprocess.run([str(RUN), *args], input=stdin, capture_output=True, env=environment,
                          timeout=10, check=False)

  def run_sender(self, path, required="0"):
    return self.launch(["icon", "--sender-image"], str(path).encode(), required)

  def make_png(self, name="sender.png"):
    path = self.inputs / name
    path.write_bytes(png((192, 96), (17, 83, 149, 255)))
    return path

  def assert_decoded_png(self, result):
    self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
    output = result.stdout.decode("ascii")
    self.assertTrue(output.startswith(DATA_URL_PREFIX))
    self.assertLessEqual(len(output), 131072)
    data = base64.b64decode(output[len(DATA_URL_PREFIX):], validate=True)
    self.assertEqual(images.sniff(data), "PNG")
    width, height, rgba = images.decode(data, ("PNG",), 128, 128 * 128, 128)
    self.assertEqual((width, height), (128, 64))
    i = (32 * width + 64) * 4
    self.assertEqual(tuple(rgba[i:i + 4]), (17, 83, 149, 255))

  def sandbox_works(self):
    result = self.launch(["status"])
    self.assertEqual(result.returncode, 0, result.stderr)
    return json.loads(result.stdout)["sandboxOperational"]

  def assert_decoded_only_in_sandbox(self, result, sandboxed):
    if sandboxed:
      self.assert_decoded_png(result)
    else:
      self.assertNotEqual(result.returncode, 0)
      self.assertEqual(result.stdout, b"")

  def test_png_becomes_self_contained_bounded_data_url_only_in_a_sandbox(self):
    sandboxed = self.sandbox_works()
    for index, required in enumerate(("0", "1")):
      with self.subTest(required=required):
        source = self.make_png(f"sender-{index}.png")
        result = self.run_sender(source, required)
        source.unlink()
        self.assertFalse(source.exists())
        self.assert_decoded_only_in_sandbox(result, sandboxed)

    self.assertEqual(list(self.home.rglob("*.png")), [])

  def test_fifo_is_rejected_promptly_and_does_not_poison_next_request(self):
    fifo = self.inputs / "sender.fifo"
    os.mkfifo(fifo)
    rejected = self.run_sender(fifo)
    self.assertNotEqual(rejected.returncode, 0)
    self.assertEqual(rejected.stdout, b"")

    source = self.make_png("after-fifo.png")
    accepted = self.run_sender(source)
    source.unlink()
    self.assert_decoded_only_in_sandbox(accepted, self.sandbox_works())

  def test_unsafe_or_invalid_sources_emit_nothing(self):
    target = self.make_png("target.png")
    symlink = self.inputs / "sender-link.png"
    symlink.symlink_to(target)

    directory = self.inputs / "sender-directory"
    directory.mkdir()

    oversized = self.inputs / "oversized.png"
    oversized.write_bytes(b"x" * (1024 * 1024 + 1))

    invalid = self.inputs / "invalid.png"
    invalid.write_bytes(b"not an image")

    empty = self.inputs / "empty.png"
    empty.write_bytes(b"")

    # Kernel interfaces report themselves as regular files; they are refused
    # by where the opened file really is, even through a symlinked directory.
    proc_link = self.inputs / "proc"
    proc_link.symlink_to("/proc/self", target_is_directory=True)

    for label, path in (
        ("symlink", symlink),
        ("directory", directory),
        ("oversized", oversized),
        ("invalid", invalid),
        ("empty", empty),
        ("proc", Path("/proc/self/environ")),
        ("proc through a symlinked directory", proc_link / "environ"),
        ("sys", Path("/sys/kernel/mm/transparent_hugepage/enabled")),
    ):
      with self.subTest(case=label):
        result = self.run_sender(path)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
  unittest.main()
