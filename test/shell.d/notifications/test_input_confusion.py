"""Misnamed and disguised input, and attempts to get out of a boundary.

Every image is judged by its bytes, never its name; every name and argument is
data, never an option, coder or path outside its root; and every sandbox keeps
what it holds to itself.
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
    with tempfile.TemporaryDirectory() as temp, patch.object(icon, "CACHE", temp):
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
    with tempfile.TemporaryDirectory() as temp, patch.object(icon, "CACHE", temp):
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

    with tempfile.TemporaryDirectory() as temp, patch.object(icon, "CACHE", temp), \
            patch.object(images.subprocess, "run", record):
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
    fields, flags, scheme = self.runner.icon_lookup(
        ["--key=-x", "--app=--fetch", "--app-icon=--sender-image", "--source=x\n--download",
         "--scheme", "light", "--fetch", "--why"])
    self.assertEqual(fields, ["--key=-x", "--app=--fetch", "--app-icon=--sender-image", "--source=x\n--download"])
    self.assertEqual((flags, scheme), ({"--fetch", "--why"}, "light"))
    for bad in (["--download"], ["--fetched"], ["--fetche"], ["--down"], ["--sender-image", "--key=x"],
                ["--key", "x"], ["--scheme", "sepia"], ["--scheme"], ["-x"], ["x"], ["--source=x", "--fetch=1"]):
      with self.subTest(args=bad), self.assertRaises(ValueError):
        self.runner.icon_lookup(bad)

  def test_the_icon_helper_takes_no_abbreviations(self):
    icon = load_helper("icon")
    with tempfile.TemporaryDirectory() as temp, patch.object(icon, "CACHE", temp), \
            patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(b""))), \
            patch.object(sys, "stderr", io.StringIO()), self.assertRaises(SystemExit):
      icon.main(["--fetche", "--key=x"])

  def test_dash_leading_values_are_values(self):
    icon = load_helper("icon")
    captured = {}

    def resolve(args, fetcher=None):
      captured.update(vars(args))
      return None, "none"

    out = io.BytesIO()
    with tempfile.TemporaryDirectory() as temp, patch.object(icon, "CACHE", temp), \
            patch.object(icon, "resolve", resolve), patch.object(sys, "stdout", io.TextIOWrapper(out)):
      icon.main(["--key=--fetch", "--app=--sender-image", "--app-icon=-x", "--source=--scheme=light"])
    self.assertEqual((captured["key"], captured["app"], captured["app_icon"], captured["source"]),
                     ("--fetch", "--sender-image", "-x", "--scheme=light"))
    self.assertFalse(captured["fetch"] or captured["sender_image"] or captured["download"])
    self.assertEqual(captured["scheme"], "dark")

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


class FetchingAndDecodingAreApart(unittest.TestCase):
  """The sandbox with a network decodes nothing; the decoder has no network."""

  def test_downloading_never_decodes(self):
    icon = load_helper("icon")
    jpeg_like = b"\xff\xd8\xff" + b"x" * 64

    def get(url, _limit):
      if url == "https://source.test/":
        return b'<link rel="icon" href="/svg.png"><link rel="icon" href="/a.jpg"><link rel="icon" href="/html.ico">', url
      if url.endswith("svg.png"):
        return SVG, url
      if url.endswith("html.ico"):
        return b"<html></html>", url
      return jpeg_like, url

    # svg.png and html.ico are refused by signature; a.jpg and the
    # /favicon.ico fallback are kept, and nothing past MAX_DOWNLOADS is asked for.
    with patch.object(icon, "get", get), patch.object(images, "decode", lambda *_a: self.fail("decoded")), \
            patch.object(images, "rasterize_svg", lambda *_a: self.fail("rasterised")):
      blobs = icon.download_candidates("source.test", "dark")
    # Only bodies whose signature names a decoder format survive the download;
    # whatever the URL or Content-Type said.
    self.assertEqual(blobs, [jpeg_like, jpeg_like])

  @needs_magick
  def test_a_lying_body_is_refused_when_decoded(self):
    icon = load_helper("icon")
    with tempfile.TemporaryDirectory() as temp, patch.object(icon, "CACHE", temp):
      self.assertIsNone(icon.store_fetched("source.test", "dark", [b"\x89PNG\r\n\x1a\n" + SVG]))
      self.assertIsNotNone(icon.store_fetched("source.test", "dark", [png((16, 16))]))
      self.assertIsNone(icon.store_fetched("not a host", "dark", [png((16, 16))]))

  def test_downloaded_bytes_are_framed_and_bounded(self):
    icon = load_helper("icon")
    blobs = [b"a" * 10, b"b" * 20]
    self.assertEqual(icon.unpack_blobs(icon.pack_blobs(blobs)), blobs)
    for data in (b"", b"{}\n", b'{"blobs":[5]}\nabc', b'{"blobs":[1,1,1]}\nabc', b'{"blobs":[0]}\n',
                 b'{"blobs":[2000000]}\n', b'{"blobs":["1"]}\nx', b"[1]\nx"):
      with self.subTest(data=data[:24]), self.assertRaises((ValueError, AttributeError)):
        icon.unpack_blobs(data)


class SeccompProgram(unittest.TestCase):
  """Evaluate the download sandbox's filter the way the kernel would."""

  @staticmethod
  def evaluate(program, arch, nr, arg0):
    import struct
    data = struct.pack("<iI", nr, arch) + struct.pack("<Q", 0) + struct.pack("<Q", arg0)
    ops = [struct.unpack("=HBBI", program[i:i + 8]) for i in range(0, len(program), 8)]
    pc, acc = 0, 0
    while True:
      code, jt, jf, k = ops[pc]
      if code == 0x20:
        acc = struct.unpack_from("<I", data, k)[0]
        pc += 1
      elif code in (0x15, 0x35):
        hit = acc == k if code == 0x15 else acc >= k
        pc += 1 + (jt if hit else jf)
      elif code == 0x06:
        return k
      else:
        raise AssertionError("unexpected opcode %#x" % code)

  def test_each_architecture(self):
    runner = load_helper("run")
    allow, kill, refuse = 0x7FFF0000, 0x80000000, 0x0005000D
    for machine, (arch, socket_nr) in runner.SECCOMP_ARCH.items():
      with self.subTest(machine=machine), patch.object(runner.os, "uname",
                                                      lambda m=machine: os.uname_result(("", "", "", "", m))):
        program = runner.no_unix_sockets_filter()
        run = lambda a, nr, arg0: self.evaluate(program, a, nr, arg0)
        self.assertEqual(run(arch, socket_nr, 1), refuse, "AF_UNIX")
        self.assertEqual(run(arch, socket_nr, 2), allow, "AF_INET")
        self.assertEqual(run(arch, socket_nr, 10), allow, "AF_INET6")
        self.assertEqual(run(arch, 63, 1), allow, "another syscall")
        self.assertEqual(run(0x40000003, socket_nr, 2), kill, "a foreign ABI")
        for nr in (0x40000000, 0x40000000 | 41, 0x40000000 | 0x200):
          self.assertEqual(run(arch, nr, 2), kill, "x32 %#x" % nr)


class PhaseProtocol(unittest.TestCase):
  """The launcher's three icon phases, with every sandbox run faked."""

  def setUp(self):
    self.runner = load_helper("run")
    self.calls = []

  def run_job(self, lookup_output):
    def supervised(argv, environ, timeout, stdin=None, capture=None, pass_fds=(), deadline=None):
      inner = argv[argv.index("/usr/bin/python3"):]
      self.calls.append((argv, inner, pass_fds, deadline))
      if "--download" in inner:
        return 0, b'{"blobs":[]}\n'
      if "--fetched" in inner:
        return 0, images.pack_nothing("none")
      return 0, lookup_output

    with tempfile.TemporaryDirectory() as temp, patch.object(self.runner, "STATE", Path(temp) / "state"), \
            patch.object(self.runner, "PUBLISHED", Path(temp) / "out"), \
            patch.object(self.runner, "mode_status", return_value=({"mode": "sandboxed"}, "/usr/bin/bwrap")), \
            patch.object(self.runner, "run_supervised", supervised), patch.object(sys, "stdout", io.StringIO()):
      try:
        self.runner.run_helper("icon", ["--key=web:source.test", "--source=source.test", "--scheme", "dark",
                                        "--fetch"], False, {})
      except ValueError:
        pass
    return [inner for _, inner, _, _ in self.calls if "--download" in inner]

  def test_each_half_runs_in_its_own_sandbox_under_one_deadline(self):
    self.run_job(images.pack_nothing("fetch:source.test", fetch="source.test"))
    phases = [next(arg for arg in inner if arg in ("--fetch", "--download", "--fetched"))
              for _, inner, _, _ in self.calls]
    self.assertEqual(phases, ["--fetch", "--download", "--fetched"])
    self.assertEqual(len({deadline for *_, deadline in self.calls} - {None}), 1)
    for argv, inner, fds, _ in self.calls:
      networked = "--share-net" in argv
      self.assertEqual(networked, "--download" in inner, argv)
      if networked:
        self.assertIn("--seccomp", argv)
        self.assertEqual(len(fds), 1)
        self.assertFalse(any(word == "--bind" for word in argv), "the download sandbox writes nowhere")
        self.assertIn("--source=source.test", inner)

  def test_only_a_well_formed_request_for_the_source_is_downloaded(self):
    # Another site, a differently spelled host, or anything after the answer.
    for output in (images.pack_nothing("fetch:other.test", fetch="other.test"),
                   images.pack_nothing("fetch:source.test", fetch="SOURCE.test."),
                   images.pack_nothing("fetch:source.test", fetch="source.test") + b"extra"):
      with self.subTest(output=output[:60]):
        self.calls.clear()
        self.assertEqual(self.run_job(output), [])

  def test_a_phase_stops_at_the_job_deadline_not_its_own_limit(self):
    started = time.monotonic()
    with self.assertRaises(TimeoutError):
      self.runner.run_supervised(["/usr/bin/sleep", "30"], {"PATH": "/usr/bin"}, 20, None, 4096, (),
                                 time.monotonic() + 1)
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

  def probe(self, args, seccomp=False):
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
      seccomp_fd = None
      try:
        with patch.object(self.runner, "HOME_DIR", home), patch.object(self.runner, "STATE", home / "state"):
          if seccomp:
            seccomp_fd = self.runner.sealed_memfd("seccomp", self.runner.no_unix_sockets_filter())
            os.set_inheritable(seccomp_fd, True)
          cmd = self.runner.sandbox_command("icon", args, self.bwrap, {}, seccomp_fd)
        cmd = cmd[:cmd.index("/usr/bin/python3")]
        code = (self.PROBE.replace("SECRET", repr(str(secret))).replace("FD", str(fd))
                .replace("ABSTRACT", repr("\0omarchy-escape-%d" % os.getpid()))
                .replace("HOSTPID", str(os.getpid())).replace("ADDRESS", repr(listener.getsockname())))
        fds = (seccomp_fd,) if seccomp_fd is not None else ()
        result = subprocess.run(cmd + ["/usr/bin/python3", "-c", code], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, pass_fds=fds, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return json.loads(result.stdout)
      finally:
        os.close(fd)
        if seccomp_fd is not None:
          os.close(seccomp_fd)
        abstract.close()
        listener.close()

  def test_decoding_sandboxes_reach_nothing(self):
    for args in ([], ["--fetch"], ["--fetched"], ["--sender-image"]):
      with self.subTest(args=args):
        found = self.probe(args)
        self.assertEqual({k for k, v in found.items() if v == "ALLOWED"}, {"unix-socket"}, found)

  def test_the_download_sandbox_has_the_network_and_nothing_else(self):
    found = self.probe(["--download"], seccomp=True)
    self.assertEqual(found.pop("loopback"), "ALLOWED", "DNS needs loopback; the HTTP client refuses it")
    self.assertEqual({k for k, v in found.items() if v == "ALLOWED"}, set(), found)


if __name__ == "__main__":
  unittest.main()
