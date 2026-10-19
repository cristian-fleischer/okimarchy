"""Sender images become self-contained data: URLs through `run icon --sender-image`."""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


from support import RUN, have_magick, png

DATA_URL_PREFIX = "data:image/png;base64,"


class SenderImage(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    if not have_magick():
      raise unittest.SkipTest("imagemagick is not installed")
    import notification_images
    cls.images = notification_images

  def setUp(self):
    self.temp = tempfile.TemporaryDirectory(prefix="omarchy-notification-sender-image-")
    self.root = Path(self.temp.name)
    self.home = self.root / "home"
    self.inputs = self.root / "inputs"
    self.home.mkdir()
    self.inputs.mkdir()

  def tearDown(self):
    self.temp.cleanup()

  def environment(self, required="0"):
    return {
        "HOME": str(self.home),
        "LANG": "C.UTF-8",
        "PATH": "/usr/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMARCHY_NOTIFICATIONS_REQUIRE_SANDBOX": required,
    }

  def mode_status(self):
    result = subprocess.run(
        [str(RUN), "status"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=self.environment(),
        timeout=10,
        check=False,
    )
    self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
    return json.loads(result.stdout)

  def run_sender(self, path, required="0", timeout=10):
    self.assertTrue(path.is_absolute())
    return subprocess.run(
        [str(RUN), "icon", "--sender-image"],
        input=str(path).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=self.environment(required),
        timeout=timeout,
        check=False,
    )

  def make_png(self, name="sender.png"):
    path = self.inputs / name
    path.write_bytes(png((192, 96), (17, 83, 149, 255)))
    return path

  def assert_decoded_png(self, result):
    self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
    output = result.stdout.decode("ascii")
    self.assertTrue(output.startswith(DATA_URL_PREFIX))
    self.assertLessEqual(len(output), 131072)
    png = base64.b64decode(output[len(DATA_URL_PREFIX):], validate=True)
    self.assertEqual(self.images.sniff(png), "PNG")
    width, height, rgba = self.images.decode(png, ("PNG",), 128, 128 * 128, 128)
    self.assertEqual((width, height), (128, 64))
    i = (32 * width + 64) * 4
    self.assertEqual(tuple(rgba[i:i + 4]), (17, 83, 149, 255))

  def test_png_becomes_self_contained_bounded_data_url_in_available_modes(self):
    status = self.mode_status()
    modes = [(status["mode"], "0")]
    if status["sandboxOperational"]:
      modes.append(("required-sandbox", "1"))

    for index, (mode, required) in enumerate(modes):
      with self.subTest(mode=mode):
        source = self.make_png(f"sender-{index}.png")
        result = self.run_sender(source, required)
        source.unlink()
        self.assertFalse(source.exists())
        self.assert_decoded_png(result)

    self.assertEqual(list(self.home.rglob("*.png")), [])

  def test_fifo_is_rejected_promptly_and_does_not_poison_next_request(self):
    fifo = self.inputs / "sender.fifo"
    os.mkfifo(fifo)
    rejected = self.run_sender(fifo, timeout=10)
    self.assertNotEqual(rejected.returncode, 0)
    self.assertEqual(rejected.stdout, b"")

    source = self.make_png("after-fifo.png")
    accepted = self.run_sender(source)
    source.unlink()
    self.assert_decoded_png(accepted)

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
