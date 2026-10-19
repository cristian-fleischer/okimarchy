"""Small HTTPS client with pinned public DNS answers and bounded responses."""
import http.client
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import urlsplit, urlunsplit, urljoin

MAX_REDIRECTS = 3
MAX_DNS_ANSWERS = 8
MAX_RESPONSE_BYTES = 1024 * 1024
CONNECT_TIMEOUT = 5
REQUEST_DEADLINE = 12

def public_hostname(raw):
  if not isinstance(raw, str) or len(raw) > 253:
    return None
  h = raw.lower().removesuffix('.')
  if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+', h):
    return None
  if (h.split('.')[-1].isdigit() or re.fullmatch(r'0x[0-9a-f]*', h.split('.')[-1])
          or h.endswith(('.local', '.localhost', '.localdomain', '.internal',
                         '.home', '.home.arpa', '.lan'))):
    return None
  return h

def parse_url(raw):
  if (not isinstance(raw, str) or len(raw) > 4096
          or re.search(r'[\x00-\x20\x7f-\x9f\\<>"\']|%(?:0[0-9a-f]|1[0-9a-f]|7f|25|5c)', raw, re.I)):
    raise ValueError('invalid URL')
  p = urlsplit(raw)
  h = public_hostname(p.hostname)
  try:
    port = p.port if p.port is not None else 443
  except ValueError as error:
    raise ValueError('forbidden destination') from error
  if (p.scheme != 'https' or not h or p.username is not None
          or p.password is not None or port != 443):
    raise ValueError('forbidden destination')
  return p, h, port

def resolve_public_answers(host, port):
  """One bounded DNS answer set, every address checked before any connect.

  These numeric addresses are the only ones the connection may try, so a
  later resolver change cannot redirect the request to a local service."""
  answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM,
                               proto=socket.IPPROTO_TCP)
  if not answers:
    raise ValueError('empty DNS response')
  checked = []
  seen = set()
  for family, socktype, proto, canonname, address in answers:
    if family not in (socket.AF_INET, socket.AF_INET6):
      raise ValueError('non-public DNS response')
    ip = ipaddress.ip_address(address[0])
    if (not ip.is_global or ip.is_multicast or ip.is_reserved
            or (isinstance(ip, ipaddress.IPv6Address)
                and ip.ipv4_mapped is not None)):
      raise ValueError('non-public DNS response')
    key = (family, socktype, proto, address)
    if key not in seen:
      if len(checked) == MAX_DNS_ANSWERS:
        raise ValueError('too many DNS answers')
      seen.add(key)
      checked.append((family, socktype, proto, canonname, address))
  return checked

class PinnedHTTPConnection(http.client.HTTPConnection):
  def __init__(self, host, port, answers, deadline):
    super().__init__(host, port, timeout=CONNECT_TIMEOUT)
    self.answers = answers
    self.deadline = deadline

  def remaining(self):
    remaining = self.deadline - time.monotonic()
    if remaining <= 0:
      raise TimeoutError('request deadline')
    return min(CONNECT_TIMEOUT, remaining)

  def connect(self):
    last_error = None
    for family, socktype, proto, _, address in self.answers:
      sock = None
      try:
        sock = socket.socket(family, socktype, proto)
        sock.settimeout(self.remaining())
        # Numeric sockaddr from the validated resolution: no second lookup.
        sock.connect(address)
      except OSError as error:
        if sock is not None:
          sock.close()
        last_error = error
        continue
      try:
        # TLS validation is inseparable from every connection. A bad
        # certificate or hostname is not masked by trying another IP.
        sock.settimeout(self.remaining())
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.sock = context.wrap_socket(sock, server_hostname=self.host)
        return
      except BaseException:
        sock.close()
        raise
    if last_error is not None:
      raise last_error
    raise OSError('no validated DNS answer')

def fetch_once(url, limit, deadline):
  p, host, port = parse_url(url)
  answers = resolve_public_answers(host, port)
  conn = PinnedHTTPConnection(host, port, answers, deadline)
  try:
    conn.request('GET', urlunsplit(('', '', p.path or '/', p.query, '')),
                 headers={'Host': host, 'User-Agent': 'omarchy-notifications/1',
                          'Accept-Encoding': 'identity', 'Connection': 'close'})
    stream_socket = conn.sock
    if stream_socket is not None:
      stream_socket.settimeout(conn.remaining())
    response = conn.getresponse()
    if response.status in (301, 302, 303, 307, 308):
      location = response.getheader('Location')
      if not location:
        raise ValueError('missing redirect')
      return None, location
    if response.status != 200 or response.getheader('Content-Encoding', 'identity') != 'identity':
      raise ValueError('unsupported response')
    length = response.getheader('Content-Length')
    if length is not None:
      try:
        declared = int(length)
      except ValueError as error:
        raise ValueError('invalid content length') from error
      if declared < 0 or declared > limit:
        raise ValueError('oversized response')
    body = bytearray()
    while len(body) <= limit:
      # HTTPConnection clears conn.sock for Connection: close responses;
      # the response's file still owns this socket until the body closes.
      remaining = conn.remaining()
      if stream_socket is not None:
        stream_socket.settimeout(remaining)
      block = response.read1(min(16384, limit + 1 - len(body)))
      if not block:
        break
      body.extend(block)
      if response.isclosed():
        break
    if len(body) > limit:
      raise ValueError('oversized response')
    return bytes(body), None
  finally:
    conn.close()

def fetch(url, limit=512*1024):
  if type(limit) is not int or not 0 < limit <= MAX_RESPONSE_BYTES:
    raise ValueError('invalid response limit')
  deadline = time.monotonic() + REQUEST_DEADLINE
  for hop in range(MAX_REDIRECTS + 1):
    data, location = fetch_once(url, limit, deadline)
    if location is None:
      return data, url
    if hop == MAX_REDIRECTS:
      raise ValueError('redirect limit')
    # Validate Location before joining: urljoin can strip hostile controls.
    if (not isinstance(location, str) or len(location) > 4096
            or re.search(r'[\x00-\x20\x7f-\x9f\\]', location)):
      raise ValueError('invalid redirect')
    url = urljoin(url, location)
    # Fail before another DNS lookup or connect on HTTPS downgrade,
    # credentials, numeric/local names, or a forbidden port.
    parse_url(url)
