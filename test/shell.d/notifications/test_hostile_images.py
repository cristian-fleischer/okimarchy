"""Hostile input on the image path: SVGs, ICOs and the decoder policy."""
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from support import SVG, load_helper, magick, needs_magick, png

import notification_images as images


EXTERNAL_IMAGE_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
  width="16" height="16">
  <image width="16" height="16" xlink:href="%s"/>
  <image width="16" height="16" xlink:href="file://%s"/>
</svg>"""

ENTITY_SVG = b"""<?xml version="1.0"?>
<!DOCTYPE svg [<!ENTITY secret SYSTEM "file:///etc/hostname">]>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="20"><text y="15">&secret;</text></svg>"""


class Svg(unittest.TestCase):
  @needs_magick
  def test_external_images_in_an_svg_are_never_loaded(self):
    with tempfile.TemporaryDirectory() as temp:
      private = Path(temp) / "private.png"
      private.write_bytes(png((16, 16), (0, 255, 0, 255)))
      svg = EXTERNAL_IMAGE_SVG % (str(private).encode(), str(private).encode())
      width, height, rgba = images.rasterize_svg(svg, 512)
      self.assertEqual((width, height), (32, 32))   # 16px at 192 dpi
      self.assertEqual(sum(rgba[3::4]), 0, "the referenced file was drawn")

  @needs_magick
  def test_external_entities_are_refused(self):
    with self.assertRaises(ValueError):
      images.rasterize_svg(ENTITY_SVG, 512)

  @needs_magick
  def test_local_svg_icons_come_back_as_pixels(self):
    icon = load_helper("icon")
    with tempfile.TemporaryDirectory() as temp:
      source = Path(temp) / "mark.svg"
      source.write_bytes(SVG)
      rgba, mono = icon.normalise(str(source))
      self.assertEqual(len(rgba), 128 * 128 * 4)
      self.assertEqual(tuple(rgba[(64 * 128 + 64) * 4:(64 * 128 + 64) * 4 + 4])[3], 255)
      source.write_bytes(b"not an svg")
      self.assertIsNone(icon.normalise(str(source)))


class Frames(unittest.TestCase):
  def test_rejected_counts_never_reach_the_decoder(self):
    def forbidden(*_args):
      raise AssertionError("ImageMagick ran on a rejected icon")
    with patch.object(images, "_magick", forbidden):
      for count in (0, 65, 1024):
        with self.subTest(count=count), self.assertRaises(ValueError):
          images.decode(self.ico(count), ("ICO",), 2048, 2048 * 2048, 128)

  def ico(self, count):
    entry = png((4, 4))
    header = bytes([0, 0, 1, 0]) + count.to_bytes(2, "little")
    offset = 6 + 16 * count
    directory = b"".join(bytes([4, 4, 0, 0, 1, 0, 32, 0]) + len(entry).to_bytes(4, "little")
                         + offset.to_bytes(4, "little") for _ in range(count))
    return header + directory + entry

  @needs_magick
  def test_an_icon_decodes_its_largest_frame_and_an_animation_is_refused(self):
    self.assertEqual(images.decode(self.ico(64), ("ICO",), 2048, 2048 * 2048, 128)[:2], (4, 4))
    sizes = magick("-size", "64x64", "xc:red", "-define", "icon:auto-resize=16,32,64", "ico:-")
    self.assertEqual(images.decode(sizes, ("ICO",), 2048, 2048 * 2048, 128)[:2], (64, 64))
    animation = magick("-size", "8x8", "xc:red", "xc:blue", "-loop", "0", "webp:-")
    with self.assertRaises(ValueError):
      images.decode(animation, ("WEBP",), 2048, 2048 * 2048, 128)


class Policy(unittest.TestCase):
  @needs_magick
  def test_the_bundled_policy_is_the_one_in_force(self):
    listing = subprocess.run([images.MAGICK, "-list", "policy"], env=images.ENVIRONMENT,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False).stdout.decode()
    self.assertIn(str(Path(images.POLICY_DIR) / "policy.xml"), listing)

  def convert(self, source, data):
    # PAM is the output the helpers are allowed, so a refusal here can only be
    # the input coder's.
    return subprocess.run([images.MAGICK, source, "-depth", "8", "pam:-"], input=data, env=images.ENVIRONMENT,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)

  @needs_magick
  def test_policy_denies_coders_the_helpers_never_use(self):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8"/></svg>'
    allowed = self.convert("png:-", png((8, 8)))
    self.assertEqual(allowed.returncode, 0, "the allowed path must work, or every refusal below is moot")
    self.assertTrue(allowed.stdout.startswith(b"P7\n"))
    self.assertEqual(self.convert("rsvg:-", svg).returncode, 0)
    with tempfile.TemporaryDirectory() as temp:
      listed = Path(temp) / "listed.png"
      listed.write_bytes(png((8, 8)))
      image_list = Path(temp) / "list.txt"
      image_list.write_text(str(listed) + "\n")
      # Real inputs for every denied coder: under ImageMagick's own policy each
      # one converts, so a refusal under ours is the policy and not a bad file.
      gif = magick("-size", "8x8", "xc:red", "gif:-")
      cases = (("label:secret", b""), ("caption:secret", b""), ("svg:-", svg), ("msvg:-", svg),
               ("mvg:-", b"viewbox 0 0 8 8 fill red rectangle 0,0 8,8"), ("text:-", b"secret"),
               ("gif:-", gif), ("@" + str(image_list), b""))
      permissive = {"PATH": "/usr/bin", "LANG": "C.UTF-8"}
      for source, data in cases:
        with self.subTest(source=source):
          control = subprocess.run([images.MAGICK, source, "-depth", "8", "pam:-"], input=data, env=permissive,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
          if control.returncode != 0:
            self.skipTest("the system policy already refuses " + source)
          result = self.convert(source, data)
          self.assertNotEqual(result.returncode, 0)
          self.assertEqual(result.stdout, b"")

  def test_decoded_output_is_bounded(self):
    with self.assertRaises(ValueError):
      images._bounded((129, 1, b""), 128)


class Publishing(unittest.TestCase):
  """The launcher, outside every sandbox, turns a helper's pixels into the PNG
  the shell loads."""

  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.runner = load_helper("run")
    self.published = Path(self.temp.name) / "published"
    patcher = patch.object(self.runner, "PUBLISHED", self.published)
    patcher.start()
    self.addCleanup(patcher.stop)
    self.addCleanup(self.temp.cleanup)

  def test_icons_are_published_by_digest_and_rebuilt_from_pixels(self):
    red = images.pack_pixels(128, 128, bytes((200, 0, 0, 255)) * (128 * 128), False, "theme")
    blue = images.pack_pixels(128, 128, bytes((0, 0, 200, 255)) * (128 * 128), True, "theme")
    first, second = self.runner.publish_icon(red, False, False), self.runner.publish_icon(blue, False, True)
    self.assertRegex(first, r"/[0-9a-f]{64}\.png$")
    self.assertRegex(second, r"/[0-9a-f]{64}-mono\.png\ttheme$")
    self.assertEqual(self.runner.publish_icon(red, False, False), first, "one icon, one file")
    data = Path(first).read_bytes()
    self.assertEqual(images.sniff(data), "PNG")
    self.assertEqual(Path(first).stat().st_mode & 0o777, 0o600)
    self.assertEqual(self.runner.publish_icon(images.pack_nothing("none"), False, True), "\tnone")

  def test_sender_images_come_back_as_data_urls_of_a_rebuilt_png(self):
    url = self.runner.publish_icon(images.pack_pixels(16, 8, bytes(16 * 8 * 4)), True, False)
    self.assertTrue(url.startswith("data:image/png;base64,iVBORw0KGgoAAAANSUhEUg"))
    with self.assertRaises(ValueError):
      self.runner.publish_icon(images.pack_nothing(), True, False)

  def test_anything_but_the_pixel_protocol_publishes_nothing(self):
    import base64
    outputs = [b"", SVG, b"/home/user/.ssh/id_ed25519\n",
               b'{"width":4,"height":4,"mono":false}\n' + bytes(63),
               b'{"width":129,"height":1,"mono":false}\n' + bytes(129 * 4),
               b'{"width":1,"height":1,"mono":"yes"}\n' + bytes(4),
               b'{"none":true}\n' + SVG, b"x" * 600]
    # Not even a data: URL of a real PNG: the launcher builds every PNG itself.
    for body in (SVG, b"<html></html>", png((4, 4))):
      url = b"data:image/png;base64," + base64.b64encode(body)
      outputs += [url, b" " + url, url + b"\n", url + b"data:image/png;base64,AAAA"]
    for output in outputs:
      for sender_image in (False, True):
        with self.subTest(output=output[:40], sender_image=sender_image), self.assertRaises(ValueError):
          self.runner.publish_icon(output, sender_image, False)
    self.assertFalse(self.published.exists() and any(self.published.iterdir()))

  def test_the_published_directory_is_outside_every_sandbox(self):
    real = load_helper("run")
    for kind, args in (("icon", ["--key=x"]), ("icon", ["--sender-image"]), ("store", ["restore"])):
      command = real.sandbox_command(kind, args, "/usr/bin/bwrap", {})
      mounted = [command[i + 1] for i, word in enumerate(command) if word in ("--bind", "--ro-bind")]
      for path in mounted:
        self.assertFalse(str(real.PUBLISHED).startswith(path.rstrip("/") + "/") or path.startswith(str(real.PUBLISHED)),
                         (kind, path))

  def test_a_flooding_helper_is_cut_off(self):
    started = time.monotonic()
    with self.assertRaises(ValueError):
      self.runner.run_supervised(["/usr/bin/yes"], {"PATH": "/usr/bin"}, 10, None, 4096)
    self.assertLess(time.monotonic() - started, 5)


class SenderFiles(unittest.TestCase):
  def setUp(self):
    self.runner = load_helper("run")

  def stream(self, path):
    return io.BytesIO(str(path).encode())

  def test_a_stalled_open_is_abandoned_at_the_deadline(self):
    # A file on a stalled FUSE mount blocks lookup and open however the file is
    # opened; the reader runs in a child the launcher kills at its deadline.
    with patch.object(self.runner, "read_sender_file", lambda _path: time.sleep(3600)):
      started = time.monotonic()
      with self.assertRaises(TimeoutError):
        self.runner.open_sender_image(self.stream("/stalled/image.png"), timeout=1)
      self.assertLess(time.monotonic() - started, 4)

  def test_the_copy_handed_on_is_sealed_in_memory(self):
    with tempfile.TemporaryDirectory() as temp:
      source = Path(temp) / "image.png"
      source.write_bytes(png((8, 8)))
      fd = self.runner.open_sender_image(self.stream(source))
      try:
        source.write_bytes(b"replaced afterwards")
        self.assertTrue(os.readlink("/proc/self/fd/%d" % fd).startswith("/memfd:"))
        self.assertEqual(os.read(fd, 65536), png((8, 8)))
        import fcntl
        seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
        for seal in (fcntl.F_SEAL_WRITE, fcntl.F_SEAL_GROW, fcntl.F_SEAL_SHRINK, fcntl.F_SEAL_SEAL):
          self.assertTrue(seals & seal, seal)
        for change in (lambda: os.pwrite(fd, b"x", 0), lambda: os.ftruncate(fd, 1),
                       lambda: os.ftruncate(fd, 1 << 20)):
          with self.assertRaises(PermissionError):
            change()
      finally:
        os.close(fd)

  def test_the_reader_dies_with_its_launcher(self):
    # A launcher killed mid-read takes its reader with it.
    with tempfile.TemporaryDirectory() as temp:
      marker = Path(temp) / "reader.pid"
      script = (
          "import io, os, sys, time\n"
          "sys.path.insert(0, %r)\n"
          "from support import load_helper\n"
          "runner = load_helper('run')\n"
          "runner.read_sender_file = lambda _p: (open(%r, 'w').write(str(os.getpid())), time.sleep(3600))\n"
          "runner.open_sender_image(io.BytesIO(b'/stalled.png'), timeout=600)\n"
      ) % (str(Path(__file__).parent), str(marker))
      launcher = subprocess.Popen([sys.executable, "-B", "-c", script])
      reader = None

      def alive():
        try:
          return Path("/proc/%d/stat" % reader).read_text().split()[2] != "Z"
        except OSError:
          return False

      try:
        deadline = time.monotonic() + 10
        while not (marker.exists() and marker.read_text()) and time.monotonic() < deadline:
          time.sleep(0.05)
        reader = int(marker.read_text())
        launcher.kill()
        launcher.wait(timeout=5)
        deadline = time.monotonic() + 5
        while alive() and time.monotonic() < deadline:
          time.sleep(0.05)
        self.assertFalse(alive(), "the reader outlived its launcher")
      finally:
        if launcher.poll() is None:
          launcher.kill()
        if reader:
          try:
            os.kill(reader, 9)
          except ProcessLookupError:
            pass

  def test_pseudo_filesystems_are_refused_by_type_wherever_they_are_mounted(self):
    with tempfile.TemporaryDirectory() as temp:
      source = Path(temp) / "image.png"
      source.write_bytes(png((8, 8)))
      fd = os.open(source, os.O_RDONLY)
      try:
        info = os.fstat(fd)
        for kind, refused in (("sysfs", True), ("proc", True), ("debugfs", True), (None, True),
                              ("ext4", False), ("btrfs", False), ("", False)):
          with self.subTest(kind=kind), patch.object(self.runner, "filesystem_type", lambda _dev, k=kind: k):
            self.assertEqual(self.runner.opened_in_pseudo_filesystem(fd, info), refused)
      finally:
        os.close(fd)
    with open("/proc/self/environ", "rb") as environ:
      self.assertEqual(self.runner.filesystem_type(os.fstat(environ.fileno()).st_dev), "proc")

  def test_any_failure_while_supervising_stops_the_helper(self):
    def broken(*_args):
      raise OSError("selector failed")
    with patch.object(self.runner, "read_bounded", broken):
      started = time.monotonic()
      with self.assertRaises(OSError):
        self.runner.run_supervised(["/usr/bin/sleep", "60"], {"PATH": "/usr/bin"}, 30, None, 4096)
      self.assertLess(time.monotonic() - started, 10)
    leftover = subprocess.run(["pgrep", "-f", "^/usr/bin/sleep 60$"], stdout=subprocess.PIPE, check=False)
    self.assertEqual(leftover.stdout.strip(), b"", "the supervised child outlived the failure")


class Unsandboxed(unittest.TestCase):
  def test_icons_are_never_decoded_without_the_sandbox(self):
    runner = load_helper("run")
    direct = {"bubblewrapAvailable": False, "sandboxOperational": False, "required": False,
              "unsandboxedFallback": True, "mode": "direct"}
    with patch.object(runner, "mode_status", return_value=(direct, None)), \
            patch.object(runner, "run_supervised") as supervised:
      with self.assertRaises(RuntimeError):
        runner.run_helper("icon", ["--key=app:x"], False, {})
      supervised.assert_not_called()
      runner.run_helper("store", ["restore"], False, {})
      supervised.assert_called_once()


if __name__ == "__main__":
  unittest.main()
