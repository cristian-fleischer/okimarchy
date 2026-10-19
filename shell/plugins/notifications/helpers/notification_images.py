"""Bounded image decoding for the notification helpers, through ImageMagick.

ImageMagick is a base Omarchy package, so icons and sender images need no
Python imaging library. It is never left to guess a format: the bytes are
sniffed here first, and only a PNG, JPEG, WebP or ICO signature is handed to
the matching native coder (`png:-`), so a file cannot talk its way into an
SVG, MSL or text coder. Every run carries memory, size and time limits, reads
from stdin, and returns raw RGBA through PAM, which this module checks before
using. PNGs are written here, with zlib.
"""
import struct
import subprocess
import zlib

MAGICK = "/usr/bin/magick"
TIMEOUT = 10
MAX_OUTPUT = 64 * 1024 * 1024

# Signatures of the raster formats the helpers accept, and the coder each one
# is read with. Anything else is not an image as far as they are concerned.
FORMATS = {"PNG": "png", "JPEG": "jpeg", "WEBP": "webp", "ICO": "ico"}

LIMITS = [
  "-limit", "memory", "128MiB", "-limit", "map", "256MiB", "-limit", "disk", "0",
  "-limit", "width", "4096", "-limit", "height", "4096", "-limit", "area", "16MP",
  "-limit", "list-length", "64", "-limit", "time", str(TIMEOUT), "-limit", "thread", "1",
]

ENVIRONMENT = {"PATH": "/usr/bin", "LANG": "C.UTF-8", "OMP_NUM_THREADS": "1", "MAGICK_OCL_DEVICE": "OFF"}


def sniff(data):
  """The format a byte string's signature names, or None."""
  if not isinstance(data, (bytes, bytearray)):
    return None
  if data.startswith(b"\x89PNG\r\n\x1a\n"):
    return "PNG"
  if data.startswith(b"\xff\xd8\xff"):
    return "JPEG"
  if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
    return "WEBP"
  if data.startswith(b"\x00\x00\x01\x00"):
    return "ICO"
  return None


def _magick(args, data):
  try:
    result = subprocess.run([MAGICK, *args], input=bytes(data), stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, env=ENVIRONMENT, timeout=TIMEOUT,
                            check=False)
  except (OSError, subprocess.TimeoutExpired) as error:
    raise ValueError("image decoder unavailable") from error
  if result.returncode != 0 or len(result.stdout) > MAX_OUTPUT:
    raise ValueError("image rejected by decoder")
  return result.stdout


def frames(data, fmt):
  """Each frame's (width, height), read without decoding pixels."""
  out = _magick(["identify", *LIMITS, "-ping", "-format", "%w %h\n", FORMATS[fmt] + ":-"], data)
  sizes = []
  for line in out.decode("ascii", "strict").splitlines():
    width, height = (int(part) for part in line.split())
    sizes.append((width, height))
  if not sizes:
    raise ValueError("no frames")
  return sizes


def parse_pam(data):
  """(width, height, rgba) from an RGB_ALPHA PAM, or ValueError."""
  marker = b"ENDHDR\n"
  end = data.find(marker, 0, 256)
  if not data.startswith(b"P7\n") or end < 0:
    raise ValueError("unexpected decoder output")
  header = {}
  for line in data[3:end].decode("ascii", "strict").splitlines():
    if line and not line.startswith("#"):
      key, _, value = line.partition(" ")
      header[key] = value.strip()
  width, height = int(header.get("WIDTH", 0)), int(header.get("HEIGHT", 0))
  pixels = data[end + len(marker):]
  if (header.get("DEPTH") != "4" or header.get("MAXVAL") != "255"
          or width <= 0 or height <= 0 or len(pixels) != width * height * 4):
    raise ValueError("unexpected decoder output")
  return width, height, bytes(pixels)


def _rgba_args():
  return ["-alpha", "on", "-colorspace", "sRGB", "-type", "TrueColorAlpha", "-depth", "8", "pam:-"]


def decode(data, formats, max_side, max_pixels, out_side):
  """Verify and decode bounded image bytes to (width, height, rgba).

  The image must be one of `formats` by signature, a single frame (an ICO's
  largest frame is used), no larger than `max_side` or `max_pixels`, and is
  shrunk, never enlarged, to fit an `out_side` square.
  """
  fmt = sniff(data)
  if fmt not in formats:
    raise ValueError("unsupported image")
  sizes = frames(data, fmt)
  if fmt != "ICO" and len(sizes) != 1:
    raise ValueError("animated or multi-frame image")
  for width, height in sizes:
    if not width or not height or max(width, height) > max_side or width * height > max_pixels:
      raise ValueError("image too large")
  frame = max(range(len(sizes)), key=lambda i: sizes[i][0] * sizes[i][1])
  source = "%s:-[%d]" % (FORMATS[fmt], frame)
  return parse_pam(_magick([*LIMITS, source, "-thumbnail", "%dx%d>" % (out_side, out_side),
                            *_rgba_args()], data))


def resize(width, height, rgba, new_width, new_height):
  """Resample raw RGBA to an exact size."""
  pam = (b"P7\nWIDTH %d\nHEIGHT %d\nDEPTH 4\nMAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n"
         % (width, height)) + rgba
  out = parse_pam(_magick([*LIMITS, "pam:-", "-filter", "Lanczos",
                           "-resize", "%dx%d!" % (new_width, new_height), *_rgba_args()], pam))
  if out[:2] != (new_width, new_height):
    raise ValueError("unexpected decoder output")
  return out[2]


def encode_png(width, height, rgba):
  """An 8-bit RGBA PNG of raw pixels."""
  stride = width * 4
  raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(height))

  def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

  return (b"\x89PNG\r\n\x1a\n"
          + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
          + chunk(b"IDAT", zlib.compress(raw, 9))
          + chunk(b"IEND", b""))
