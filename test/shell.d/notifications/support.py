"""Shared paths and loaders for the notification helper tests.

The helpers are extensionless executables, so tests load them through a
source loader to patch their module globals without running main().
"""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys

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
