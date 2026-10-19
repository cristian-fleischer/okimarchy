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
  def test_local_svg_icons_come_back_as_cache_pngs(self):
    icon = load_helper("icon")
    with tempfile.TemporaryDirectory() as temp, patch.object(icon, "CACHE", temp):
      source = Path(temp) / "mark.svg"
      source.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">'
                         b'<circle cx="16" cy="16" r="12" fill="red"/></svg>')
      out = icon.normalise(str(source))
      self.assertTrue(out.startswith(temp + os.sep) and out.endswith(".png"), out)
      self.assertEqual(images.sniff(Path(out).read_bytes()), "PNG")
      source.write_bytes(b"not an svg")
      self.assertIsNone(icon.normalise(str(source)))

  def test_svg_is_never_a_remote_or_sender_format(self):
    icon = load_helper("icon")
    self.assertNotIn("SVG", icon.REMOTE_FORMATS)
    with self.assertRaises(ValueError):
      icon.normalised_remote_png(b'<svg xmlns="http://www.w3.org/2000/svg"/>')


class Ico(unittest.TestCase):
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

  @needs_magick
  def test_policy_denies_coders_the_helpers_never_use(self):
    for source in ("label:secret", "caption:secret", "svg:-", "msvg:-", "text:/etc/hostname", "@/etc/hostname"):
      with self.subTest(source=source):
        result = subprocess.run([images.MAGICK, source, "png:-"], input=b"<svg/>", env=images.ENVIRONMENT,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

  @needs_magick
  def test_decoded_output_is_bounded(self):
    with self.assertRaises(ValueError):
      images._bounded((129, 1, b""), 128)


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
