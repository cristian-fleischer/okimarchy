"""Shared paths and loaders for the notification helper tests.

The helpers are extensionless executables, so tests load them through a
source loader to patch their module globals without running main().
"""
import importlib.machinery
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
HELPERS = ROOT / "shell/plugins/notifications/helpers"
RUN = HELPERS / "run"

if str(HELPERS) not in sys.path:
  sys.path.insert(0, str(HELPERS))


def load_helper(name, module_name=None):
  module_name = module_name or "notification_helper_" + name
  loader = importlib.machinery.SourceFileLoader(module_name, str(HELPERS / name))
  spec = importlib.util.spec_from_loader(module_name, loader)
  module = importlib.util.module_from_spec(spec)
  loader.exec_module(module)
  return module


SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">'
       b'<circle cx="16" cy="16" r="12" fill="red"/></svg>')


def have_magick():
  return Path("/usr/bin/magick").is_file()


def needs_magick(test):
  return unittest.skipUnless(have_magick(), "imagemagick is not installed")(test)


def magick(*args):
  """An image ImageMagick makes from scratch, for fixtures."""
  return subprocess.run(["/usr/bin/magick", *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        check=True).stdout


def png(size, colour=(20, 40, 60, 255)):
  """An RGBA PNG of one colour, written without any imaging library."""
  import notification_images
  width, height = size
  return notification_images.encode_png(width, height, bytes(colour) * (width * height))


def have_openssl():
  return shutil.which("openssl") is not None


def fetch_site(icon, host, scheme):
  """Both halves of a fetch in one process; the launcher runs them in separate sandboxes."""
  return icon.store_fetched(host, scheme, icon.download_candidates(host, scheme))
