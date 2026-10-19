"""Hostile input on the image path: pages, SVGs, ICOs and the decoder policy."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from support import have_magick, load_helper, png

import notification_images as images


def needs_magick(test):
  return unittest.skipUnless(have_magick(), "imagemagick is not installed")(test)


EXTERNAL_IMAGE_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
  width="16" height="16">
  <image width="16" height="16" xlink:href="%s"/>
  <image width="16" height="16" xlink:href="file://%s"/>
</svg>"""

ENTITY_SVG = b"""<?xml version="1.0"?>
<!DOCTYPE svg [<!ENTITY secret SYSTEM "file:///etc/hostname">]>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="20"><text y="15">&secret;</text></svg>"""


class FaviconPages(unittest.TestCase):
  def test_unclosed_tags_parse_in_linear_time(self):
    icon = load_helper("icon")
    # A regex over raw HTML took 30 seconds on this page before it was killed.
    for page in ("<link " * 87380, "<link rel=icon href=" + "x" * 500000, "<" * 500000):
      started = time.monotonic()
      self.assertEqual(icon.icon_links(page, "https://source.test/", "dark"), [])
      self.assertLess(time.monotonic() - started, 2.0)

  def test_link_attributes_are_still_read(self):
    icon = load_helper("icon")
    page = ('<link rel="icon" sizes="32x32" href="/a.png"><link rel=icon href=/b.png />'
            '<LINK REL="apple-touch-icon" href="https://source.test/c.png"><link rel="manifest" href="/m.json">')
    self.assertEqual(icon.icon_links(page, "https://source.test/", "dark"), [
        "https://source.test/a.png", "https://source.test/c.png", "https://source.test/b.png",
        ("manifest", "https://source.test/m.json")])


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
    with tempfile.TemporaryDirectory() as temp, patch.object(icon, "CACHE", temp):
      source = Path(temp) / "mark.svg"
      source.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">'
                         b'<circle cx="16" cy="16" r="12" fill="red"/></svg>')
      rgba, mono = icon.normalise(str(source))
      self.assertEqual(len(rgba), 128 * 128 * 4)
      self.assertEqual(tuple(rgba[(64 * 128 + 64) * 4:(64 * 128 + 64) * 4 + 4])[3], 255)
      source.write_bytes(b"not an svg")
      self.assertIsNone(icon.normalise(str(source)))

  def test_svg_is_never_a_remote_or_sender_format(self):
    icon = load_helper("icon")
    self.assertNotIn("SVG", icon.REMOTE_FORMATS)
    with self.assertRaises(ValueError):
      icon.normalised_remote_png(b'<svg xmlns="http://www.w3.org/2000/svg"/>')


class Ico(unittest.TestCase):
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
  def test_frame_count_is_bounded_before_decoding(self):
    self.assertEqual(images.decode(self.ico(64), ("ICO",), 2048, 2048 * 2048, 128)[:2], (4, 4))
    for count in (0, 65, 1024):
      with self.subTest(count=count), self.assertRaises(ValueError):
        images.decode(self.ico(count), ("ICO",), 2048, 2048 * 2048, 128)


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
    for source, data in (("label:secret", b""), ("caption:secret", b""), ("svg:-", svg), ("msvg:-", svg),
                         ("mvg:-", b"viewbox 0 0 8 8 fill red rectangle 0,0 8,8"),
                         ("text:-", b"secret"), ("gif:-", b"GIF89a"), ("@/etc/hostname", b"")):
      with self.subTest(source=source):
        result = self.convert(source, data)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

  @needs_magick
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

  def test_malformed_pixel_output_publishes_nothing(self):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    for output in (b"", svg, b"/home/user/.ssh/id_ed25519\n",
                   b'{"width":4,"height":4,"mono":false}\n' + bytes(63),
                   b'{"width":129,"height":1,"mono":false}\n' + bytes(129 * 4),
                   b'{"width":1,"height":1,"mono":"yes"}\n' + bytes(4),
                   b'{"none":true}\n' + svg, b"x" * 600):
      with self.subTest(output=output[:40]), self.assertRaises(ValueError):
        self.runner.publish_icon(output, False, False)
    self.assertFalse(self.published.exists() and any(self.published.iterdir()))

  def test_the_published_directory_is_outside_every_sandbox(self):
    real = load_helper("run")
    for kind, args in (("icon", ["--fetch"]), ("icon", ["--sender-image"]), ("store", ["restore"])):
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
