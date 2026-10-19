"""Private, bounded, atomic helper storage. Paths are application-owned."""
import json
import os
from pathlib import Path
import stat
import tempfile

MAX_BYTES = 65536
os.umask(0o077)

def private_dir(path):
  path = Path(path).absolute()
  # Refuse symlink components, including pre-existing parent directories.
  for part in [*reversed(path.parents), path]:
    if part.is_symlink():
      raise ValueError('symlink directory refused')
  path.mkdir(parents=True, exist_ok=True, mode=0o700)
  if not path.is_dir():
    raise ValueError('not a directory')
  path.chmod(0o700)
  return path

def read_json(path):
  try:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
      st = os.fstat(f.fileno())
      if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
        return None
      data = f.read(MAX_BYTES + 1)
    return json.loads(data) if len(data) <= MAX_BYTES else None
  except (OSError, ValueError, RecursionError):
    return None

def write_bytes(path, data):
  path = Path(path)
  private_dir(path.parent)
  if path.is_symlink():
    raise ValueError('symlink file refused')
  fd, temp = tempfile.mkstemp(prefix='.omarchy-notification-', dir=path.parent)
  try:
    with os.fdopen(fd, 'wb') as f:
      f.write(data)
      f.flush()
      os.fsync(f.fileno())
    os.replace(temp, path)
  finally:
    if os.path.exists(temp):
      os.unlink(temp)

def write_json(path, value):
  data = json.dumps(value, separators=(',', ':')).encode()
  if len(data) > MAX_BYTES:
    raise ValueError('entry too large')
  write_bytes(path, data)

def input_json(stream):
  data = stream.read(MAX_BYTES + 1)
  if len(data) > MAX_BYTES:
    raise ValueError('entry too large')
  value = json.loads(data)
  if not isinstance(value, dict):
    raise ValueError('object required')
  return value
