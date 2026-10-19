"""Misnamed and disguised input, and attempts to get out of a boundary.

Every image is judged by its bytes, never its name; every name and argument is
data, never an option, coder or path outside its root; no lookup reaches the
network; and every sandbox keeps what it holds to itself.
"""
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from support import SVG, load_helper, magick, needs_magick, png

import notification_images as images


class MisnamedLocalIcons(unittest.TestCase):
  """The decoder is chosen by content: the same bytes give the same answer
  under any name."""

  @needs_magick
  def test_the_decoder_follows_the_bytes_not_the_extension(self):
    icon = load_helper("icon")
    jpeg = magick("-size", "24x24", "xc:#204080", "jpeg:-")
    with tempfile.TemporaryDirectory() as temp:
      for label, data in (("png", png((24, 24))), ("jpeg", jpeg), ("svg", SVG)):
        answers = set()
        for suffix in (".png", ".jpg", ".ico", ".svg", ""):
          path = Path(temp) / (label + suffix)
          path.write_bytes(data)
          found = icon.normalise(str(path))
          self.assertIsNotNone(found, label + suffix)
          answers.add(found[0])
        self.assertEqual(len(answers), 1, label + " decoded differently under different names")

  @needs_magick
  def test_files_that_are_no_image_give_nothing_under_any_name(self):
    icon = load_helper("icon")
    with tempfile.TemporaryDirectory() as temp:
      for data in (b"", b"plain text", b"<html><body>hi</body></html>",
                   b'<?xml version="1.0"?><image><read filename="/etc/hostname"/></image>'):
        for suffix in (".png", ".svg"):
          path = Path(temp) / ("x" + suffix)
          path.write_bytes(data)
          self.assertIsNone(icon.normalise(str(path)), (data[:20], suffix))


class Polyglots(unittest.TestCase):
  formats = ("PNG", "JPEG", "WEBP", "ICO")

  def decoded(self, data):
    try:
      return images.decode(data, self.formats, 2048, 2048 * 2048, 128)
    except ValueError:
      return None

  @needs_magick
  def test_a_signature_in_front_of_something_else_is_refused(self):
    for tail in (SVG, b'<?xml version="1.0"?><image><read filename="/etc/hostname"/></image>',
                 b"<html><script>alert(1)</script></html>"):
      with self.subTest(tail=tail[:20]):
        self.assertIsNone(self.decoded(b"\x89PNG\r\n\x1a\n" + tail))

  @needs_magick
  def test_a_real_image_with_a_tail_comes_back_as_its_pixels_only(self):
    jpeg = magick("-size", "16x16", "xc:#123456", "jpeg:-")
    for data in (png((16, 16)) + SVG, png((16, 16)) + b"<html></html>",
                 jpeg + b"PK\x03\x04zip-member", jpeg + b"#!/bin/sh\nid\n"):
      with self.subTest(head=data[:4]):
        width, height, rgba = self.decoded(data)
        rebuilt = images.encode_png(width, height, rgba)
        self.assertNotIn(b"<svg", rebuilt)
        self.assertNotIn(b"PK\x03\x04", rebuilt)
        self.assertNotIn(b"/bin/sh", rebuilt)

  @needs_magick
  def test_signature_only_and_truncated_files_are_refused(self):
    jpeg = magick("-size", "16x16", "xc:red", "jpeg:-")
    webp = magick("-size", "16x16", "xc:red", "webp:-")
    for data in (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF\x00\x00\x00\x00WEBP", b"\x00\x00\x01\x00\x01\x00",
                 jpeg[:20], webp[:24], png((16, 16))[:40]):
      with self.subTest(data=data[:12]):
        self.assertIsNone(self.decoded(data))

  @needs_magick
  def test_icons_that_wrap_another_format_are_refused(self):
    def ico(entry):
      header = bytes([0, 0, 1, 0, 1, 0])
      return header + bytes([16, 16, 0, 0, 1, 0, 32, 0]) + len(entry).to_bytes(4, "little") + (22).to_bytes(4, "little") + entry
    for entry in (SVG, ico(png((4, 4)))):
      with self.subTest(entry=entry[:8]):
        self.assertIsNone(self.decoded(ico(entry)))


class NamesNeverReachTheDecoder(unittest.TestCase):
  @needs_magick
  def test_coder_prefixes_frame_selectors_and_dashes_in_names_stay_inert(self):
    icon = load_helper("icon")
    seen = []
    real = images.subprocess.run

    def record(argv, *args, **kwargs):
      seen.append(argv)
      return real(argv, *args, **kwargs)

    with tempfile.TemporaryDirectory() as temp, patch.object(images.subprocess, "run", record):
      for name in ("svg:x.png", "msl:x", "label:x", "@list", "x.png[0]", "x.png[99999]", "-x.png"):
        with self.subTest(name=name):
          path = Path(temp) / name
          path.write_bytes(png((12, 12)))
          self.assertIsNotNone(icon.normalise(str(path)))
    for argv in seen:
      self.assertFalse(any(temp in arg or arg.startswith("@") for arg in argv), argv)
      inputs = [arg for arg in argv if arg.endswith(":-") or ":-[" in arg]
      self.assertTrue(all(arg.split(":")[0] in ("png", "jpeg", "webp", "ico", "rsvg", "pam") for arg in inputs), argv)


class Arguments(unittest.TestCase):
  def setUp(self):
    self.runner = load_helper("run")

  def test_lookups_take_only_their_own_shapes(self):
    fields, why = self.runner.icon_lookup(
        ["--key=-x", "--app=--fetch", "--app-icon=--sender-image", "--source=x\n--download", "--why"])
    self.assertEqual(fields, ["--key=-x", "--app=--fetch", "--app-icon=--sender-image", "--source=x\n--download"])
    self.assertTrue(why)
    for bad in (["--sender-image", "--key=x"], ["--key", "x"], ["--scheme", "dark"], ["--scheme=light"],
                ["-x"], ["x"], ["--wh"]):
      with self.subTest(args=bad), self.assertRaises(ValueError):
        self.runner.icon_lookup(bad)

  def test_the_icon_helper_takes_no_abbreviations(self):
    icon = load_helper("icon")
    with patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(b""))), \
            patch.object(sys, "stderr", io.StringIO()), self.assertRaises(SystemExit):
      icon.main(["--sender", "--key=x"])

  def test_dash_leading_values_are_values(self):
    icon = load_helper("icon")
    captured = {}

    def resolve(args):
      captured.update(vars(args))
      return None, "none"

    out = io.BytesIO()
    with patch.object(icon, "resolve", resolve), patch.object(sys, "stdout", io.TextIOWrapper(out)):
      icon.main(["--key=--fetch", "--app=--sender-image", "--app-icon=-x", "--source=--scheme=light"])
    self.assertEqual((captured["key"], captured["app"], captured["app_icon"], captured["source"]),
                     ("--fetch", "--sender-image", "-x", "--scheme=light"))
    self.assertFalse(captured["sender_image"])

  def test_sender_path_spellings_are_refused_before_anything_is_opened(self):
    with patch.object(self.runner, "read_sender_file", lambda _p: self.fail("opened a refused path")):
      for path in (b"relative.png", b"", b"/tmp/x.png\n", b"/tmp/x\x00.png", b"/tmp/\x7fx.png",
                   b"/" + b"a" * 5000, b"\xff\xfe/not-utf8"):
        with self.subTest(path=path[:30]), self.assertRaises((ValueError, UnicodeError)):
          self.runner.open_sender_image(io.BytesIO(path))

  def test_normalised_spellings_of_a_real_file_still_work(self):
    with tempfile.TemporaryDirectory() as temp:
      folder = Path(temp) / "sender"
      folder.mkdir()
      (folder / "-x.png").write_bytes(png((8, 8)))
      for spelling in (str(folder / ".." / "sender" / "-x.png"), "/" + str(folder / "-x.png")):
        fd = self.runner.open_sender_image(io.BytesIO(spelling.encode()))
        os.close(fd)


class SiteIconsAreNeverFetched(unittest.TestCase):
  """A browser-lifted site name is chosen by the sender, so a lookup for one
  must never become a request to that host: there is no fetch mode to ask
  for, and the one sandbox a lookup runs in has no network."""

  def setUp(self):
    self.runner = load_helper("run")

  def test_fetch_and_download_modes_are_refused(self):
    icon = load_helper("icon")
    for mode in (["--fetch"], ["--download"], ["--fetched"], ["--download", "--source=example.com"]):
      args = ["--key=web:example.com", "--source=example.com"] + mode
      with self.subTest(mode=mode):
        with self.assertRaises(ValueError):
          self.runner.icon_lookup(args)
        with patch.object(self.runner, "mode_status", return_value=({"mode": "sandboxed"}, "/usr/bin/bwrap")), \
                patch.object(self.runner, "run_supervised", side_effect=AssertionError("ran a sandbox")), \
                patch.object(sys, "stderr", io.StringIO()):
          self.assertEqual(self.runner.main(["icon", *args], {}), 1)
        with patch.object(sys, "stderr", io.StringIO()), self.assertRaises(SystemExit):
          icon.main(args)

  def test_a_site_lookup_runs_once_without_a_network(self):
    calls = []

    def supervised(argv, environ, timeout, stdin=None, capture=None):
      calls.append(argv)
      return 0, images.pack_nothing("none")

    with tempfile.TemporaryDirectory() as temp, patch.object(self.runner, "STATE", Path(temp) / "state"), \
            patch.object(self.runner, "PUBLISHED", Path(temp) / "out"), \
            patch.object(self.runner, "mode_status", return_value=({"mode": "sandboxed"}, "/usr/bin/bwrap")), \
            patch.object(self.runner, "run_supervised", supervised), patch.object(sys, "stdout", io.StringIO()):
      self.assertEqual(self.runner.run_helper("icon", ["--key=web:app.slack.com", "--app=Google Chrome",
                                                       "--app-icon=google-chrome", "--source=app.slack.com"],
                                                      False, {}), 0)
    [argv] = calls
    inner = argv[argv.index("/usr/bin/python3"):]
    self.assertIn("--unshare-all", argv)
    self.assertFalse({"--share-net", "--share-net-ns", "--seccomp", "--bind"} & set(argv), argv)
    self.assertFalse({"--fetch", "--download", "--fetched"} & set(inner), inner)

  def test_an_icon_job_stops_at_its_deadline(self):
    started = time.monotonic()
    with self.assertRaises(TimeoutError):
      self.runner.run_supervised(["/usr/bin/sleep", "30"], {"PATH": "/usr/bin"}, 1, None, 4096)
    self.assertLess(time.monotonic() - started, 6)


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
          cmd = self.runner.sandbox_command("icon", args, self.bwrap, {})
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

  def test_icon_sandboxes_reach_nothing(self):
    for args in ([], ["--sender-image"]):
      with self.subTest(args=args):
        found = self.probe(args)
        self.assertEqual({k for k, v in found.items() if v == "ALLOWED"}, {"unix-socket"}, found)


if __name__ == "__main__":
  unittest.main()
