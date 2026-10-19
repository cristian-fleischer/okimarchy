"""The pinned HTTPS client and remote icon resolution.

DNS is synthetic. Only public fixture addresses are routed to a loopback TLS
server owned by this test; every other connect is refused before any network
operation. Redirects, TLS handshakes and certificate hostname checks are real.
"""
import argparse
import collections
import contextlib
import http.server
import errno
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

from support import fetch_site, have_magick, have_openssl, load_helper, png

PUBLIC = "93.184.216.34"
PUBLIC_V6 = "2606:4700:4700::1111"
BLOCKED = (
    "127.0.0.1", "10.0.0.1", "169.254.169.254", "240.0.0.1",
    "::1", "fd00::1", "fe80::1", "4000::1",
)

class IconNetworkTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    if not have_openssl():
      raise unittest.SkipTest("openssl is not installed; cannot make the TLS fixture")
    cls.temp = tempfile.TemporaryDirectory(prefix="omarchy-notification-network-")
    cls.addClassCleanup(cls.temp.cleanup)
    cert = Path(cls.temp.name) / "cert.pem"
    key = Path(cls.temp.name) / "key.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(cert), "-days", "1",
        "-subj", "/CN=source.test",
        "-addext", "subjectAltName=DNS:source.test,DNS:target.test",
    ], check=True, capture_output=True)
    cls.server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    cls.server_context.minimum_version = ssl.TLSVersion.TLSv1_2
    cls.server_context.load_cert_chain(cert, key)
    cls.client_context = ssl.create_default_context(cafile=str(cert))
    cls.client_context.minimum_version = ssl.TLSVersion.TLSv1_2

  @contextlib.contextmanager
  def transport(self, scheme="https", rebound=None, redirect=False,
                redirect_scheme=None, answers=None, fail_first=False,
                proxy=False, slow=False):
    calls = collections.Counter()
    attempts, requests, request_headers, sni = [], [], [], []
    state = {"calls": calls, "attempts": attempts, "requests": requests,
             "request_headers": request_headers, "sni": sni}

    class Handler(http.server.BaseHTTPRequestHandler):
      def do_GET(self):
        requests.append((self.headers["Host"], self.path))
        request_headers.append(dict(self.headers.items()))
        location = {"/loop": "/loop", "/private": "https://127.0.0.1/secret"}.get(self.path)
        if redirect and self.path == "/start":
          location = f"{redirect_scheme or scheme}://target.test/icon"
        body = b"" if location else b"x" * 2048 if self.path in ("/large", "/stream") else b"fixture icon"
        self.send_response(302 if location else 200)
        if location:
          self.send_header("Location", location)
        # /stream is close-delimited: only the bytes read can bound it.
        if self.path != "/stream":
          self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
          if slow:
            for byte in body:
              self.wfile.write(bytes([byte]))
              self.wfile.flush()
              time.sleep(.04)
          else:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
          pass

      def log_message(self, *_args):
        pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    if scheme == "https":
      self.server_context.set_servername_callback(
          lambda _sock, name, _ctx: sni.append(name))
      server.socket = self.server_context.wrap_socket(
          server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
    thread.start()
    real_connect = socket.socket.connect

    def resolve(host, port, *args, **kwargs):
      if host not in ("source.test", "target.test", "mismatch.test"):
        raise AssertionError("Unexpected DNS query: " + str(host))
      calls[host] += 1
      addresses = [PUBLIC]
      if answers is not None:
        addresses = answers(host)
      elif rebound and calls[host] > 1 and (not redirect or host == "target.test"):
        addresses = [rebound]
      return [
          (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP,
           "", (address, port, 0, 0)) if ":" in address else
          (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
           "", (address, port))
          for address in addresses
      ]

    def connect(sock, address):
      attempts.append(address[0])
      if address[0] not in (PUBLIC, PUBLIC_V6):
        raise OSError("Test blocked unapproved destination: " + address[0])
      if fail_first and address[0] == PUBLIC_V6:
        raise OSError("Synthetic IPv6 route failure")
      # Only our own loopback fixture can receive bytes. No external or
      # pre-existing local service is ever contacted, even before the fix.
      return real_connect(sock, server.server_address)

    environment = {"HOME": self.temp.name}
    if proxy:
      environment.update(
          http_proxy="http://proxy.test:3128",
          https_proxy="http://proxy.test:3128",
          HTTP_PROXY="http://proxy.test:3128",
          HTTPS_PROXY="http://proxy.test:3128",
          ALL_PROXY="http://proxy.test:3128",
          HTTP_COOKIE="session=ambient",
          NETRC=str(Path(self.temp.name) / "ambient-netrc"),
      )
    try:
      with mock.patch.dict(os.environ, environment, clear=True), \
              mock.patch.object(socket, "getaddrinfo", resolve), \
              mock.patch.object(socket.socket, "connect", connect), \
              mock.patch.object(ssl, "create_default_context",
                                return_value=self.client_context):
        yield load_helper("icon").get, state
    finally:
      server.shutdown()
      thread.join(timeout=3)
      server.server_close()

  def test_rebinding_never_triggers_a_second_resolution(self):
    for address in BLOCKED:
      for redirect in (False, True):
        with self.subTest(address=address, redirect=redirect):
          with self.transport("https", address, redirect) as (get, state):
            url = "https://source.test/start"
            body, final = get(url)
            self.assertEqual(body, b"fixture icon")
            self.assertEqual(final, "https://target.test/icon"
                             if redirect else url)
            expected = [("source.test", "/start")]
            if redirect:
              expected.append(("target.test", "/icon"))
            self.assertEqual(state["requests"], expected)
            self.assertEqual(state["attempts"], [PUBLIC] * len(expected))
            self.assertEqual(dict(state["calls"]),
                             {host: 1 for host, _ in expected})
            self.assertEqual(state["sni"], [host for host, _ in expected])

  def test_non_public_answers_block_initial_and_redirect_requests(self):
    # An IPv4-mapped address is refused even when the IPv4 address is public.
    for address in BLOCKED + ("172.16.0.1", "192.168.1.1", "224.0.0.1", "ff02::1", "0.0.0.0", "::",
                              "::ffff:" + PUBLIC):
      for redirect in (False, True):
        with self.subTest(address=address, redirect=redirect):
          def answers(host):
            return [PUBLIC] if redirect and host == "source.test" else [address]
          with self.transport(answers=answers, redirect=redirect) as (get, state):
            with self.assertRaises(ValueError):
              get("https://source.test/start")
            self.assertEqual(state["attempts"], [PUBLIC] if redirect else [])
            self.assertEqual(state["requests"],
                             [("source.test", "/start")] if redirect else [])

  def test_empty_and_mixed_answers_fail_before_connect(self):
    for addresses in ([], [PUBLIC, "10.0.0.1"], [PUBLIC, "fd00::1"]):
      with self.subTest(addresses=addresses):
        with self.transport(answers=lambda _host: addresses) as (get, state):
          with self.assertRaises(ValueError):
            get("https://source.test/icon")
          self.assertEqual(state["attempts"], [])
          self.assertEqual(state["requests"], [])

  def test_a_failed_address_falls_back_to_the_next_validated_one(self):
    real_socket = socket.socket

    def no_ipv6(family, *args, **kwargs):
      if family == socket.AF_INET6:
        raise OSError(errno.EAFNOSUPPORT, "Synthetic IPv6 unavailable")
      return real_socket(family, *args, **kwargs)

    for failure in ("connect", "socket"):
      with self.subTest(failure=failure), \
              self.transport(answers=lambda _host: [PUBLIC_V6, PUBLIC], fail_first=failure == "connect") as (get, state), \
              mock.patch.object(socket, "socket", no_ipv6 if failure == "socket" else real_socket):
        self.assertEqual(get("https://source.test/icon"), (b"fixture icon", "https://source.test/icon"))
        self.assertEqual(state["attempts"], [PUBLIC_V6, PUBLIC] if failure == "connect" else [PUBLIC])
        self.assertEqual(dict(state["calls"]), {"source.test": 1})
        self.assertEqual(state["sni"], ["source.test"])

  def test_tls_rejects_wrong_hostname_before_http(self):
    # The pinned transport talks http.client directly, so certificate
    # failures surface as raw ssl exceptions.
    with self.transport("https") as (get, state):
      with self.assertRaises(ssl.SSLCertVerificationError):
        get("https://mismatch.test/icon")
      self.assertEqual(state["requests"], [])
      self.assertEqual(state["sni"], ["mismatch.test"])

  def test_environment_proxy_cannot_bypass_pinning_or_add_credentials(self):
    with self.transport(proxy=True) as (get, state):
      self.assertEqual(get("https://source.test/icon")[0], b"fixture icon")
      self.assertEqual(state["attempts"], [PUBLIC])
      self.assertEqual(state["requests"], [("source.test", "/icon")])
      headers = state["request_headers"][0]
      self.assertNotIn("Cookie", headers)
      self.assertNotIn("Authorization", headers)
      self.assertNotIn("Proxy-Authorization", headers)

  def test_http_initial_and_redirect_downgrade_fail_before_destination_lookup(self):
    with self.transport(redirect=True, redirect_scheme="http") as (get, state):
      with self.assertRaises(ValueError):
        get("http://source.test/start")
      self.assertEqual(state["attempts"], [])
      self.assertEqual(dict(state["calls"]), {})

      with self.assertRaises(ValueError):
        get("https://source.test/start")
      self.assertEqual(state["requests"], [("source.test", "/start")])
      self.assertEqual(state["attempts"], [PUBLIC])
      self.assertEqual(dict(state["calls"]), {"source.test": 1})

  def test_credentials_numeric_hosts_local_names_and_ports_are_rejected(self):
    forbidden = (
        "file:///etc/passwd",
        "http://169.254.169.254/",
        "https://127.1/icon",
        "https://source.test/%250a",
        "https://user:password@source.test/icon",
        "https://127.0.0.1/icon",
        "https://[::1]/icon",
        "https://localhost/icon",
        "https://service.local/icon",
        "https://service.localdomain/icon",
        "https://service.home.arpa/icon",
        "https://source.test:444/icon",
        "https://source.test:0/icon",
        "https://0x7f.0x0.0x0.0x1/icon",
    )
    with self.transport() as (get, state):
      for url in forbidden:
        with self.subTest(url=url), self.assertRaises(ValueError):
          get(url)
      self.assertEqual(state["attempts"], [])
      self.assertEqual(dict(state["calls"]), {})

  def test_redirect_loops_private_redirects_and_oversized_bodies_fail(self):
    with self.transport() as (get, state):
      for route in ("loop", "private", "large", "stream"):
        with self.subTest(route=route), self.assertRaises(ValueError):
          get("https://source.test/" + route, 100)
      self.assertEqual(state["requests"].count(("source.test", "/loop")), 4)
      self.assertEqual(dict(state["calls"]), {"source.test": 7})

  def test_dns_answer_count_is_bounded_before_connect(self):
    too_many = [f"93.184.216.{last}" for last in range(1, 10)]
    with self.transport(answers=lambda _host: too_many) as (get, state):
      with self.assertRaises(ValueError):
        get("https://source.test/icon")
      self.assertEqual(state["attempts"], [])
      self.assertEqual(state["requests"], [])

  def test_response_limit_is_positive_and_capped(self):
    with self.transport() as (get, state):
      maximum = get.__globals__["MAX_RESPONSE_BYTES"]
      for limit in (0, -1, True, maximum + 1):
        with self.subTest(limit=limit), self.assertRaises(ValueError):
          get("https://source.test/icon", limit)
      self.assertEqual(state["attempts"], [])
      self.assertEqual(dict(state["calls"]), {})

  def test_slow_connection_close_body_obeys_total_deadline(self):
    with self.transport(slow=True) as (get, state), \
            mock.patch("notification_http.REQUEST_DEADLINE", .12):
      with self.assertRaises(TimeoutError):
        get("https://source.test/icon")
      self.assertEqual(state["requests"], [("source.test", "/icon")])


class IconResolutionTest(unittest.TestCase):
  def setUp(self):
    self.icon = load_helper("icon")
    temp = tempfile.TemporaryDirectory()
    self.addCleanup(temp.cleanup)
    self.cache = temp.name
    for name, value in (("CACHE", self.cache), ("from_config", lambda _names: None),
                        ("from_icon_theme", lambda _names: None), ("from_desktop_entries", lambda _names: None)):
      patcher = mock.patch.object(self.icon, name, value)
      patcher.start()
      self.addCleanup(patcher.stop)

  def site(self, pages):
    """A fake fetch serving `pages` by URL, recording what was asked for."""
    self.requested = []

    def get(url, _limit=None):
      self.requested.append(url)
      if url not in pages:
        raise ValueError("no such page " + url)
      return pages[url], url
    return mock.patch.object(self.icon, "get", get)

  def test_manifest_candidates_are_https_only_and_malformed_ones_are_contained(self):
    good = json.dumps({"icons": [
        {"src": "icon.png", "sizes": "128x128"},
        {"src": "http://target.test/downgrade.png", "sizes": "64x64"},
        None,
        {"src": "https://127.0.0.1/private.png", "sizes": "32x32"},
        {"src": 7},
    ]}).encode()
    for payload, expected in ((good, ["https://source.test/assets/icon.png"]), (b"{", []), (b"[]", []),
                              (b'{"icons":{}}', []), (b'{"icons":[null,4,{"src":3}]}', [])):
      with self.subTest(payload=payload[:20]), self.site({"https://source.test/assets/m.json": payload}):
        self.assertEqual(self.icon.from_manifest("https://source.test/assets/m.json", "https://source.test/"),
                         expected)

  def test_malformed_manifest_does_not_hide_a_later_page_icon(self):
    if not have_magick():
      self.skipTest("imagemagick is not installed")
    pages = {"https://source.test/": b'<link rel="manifest" href="/bad.webmanifest"><link rel="icon" href="/icon.png">',
             "https://source.test/bad.webmanifest": b'{"icons":{}}',
             "https://source.test/icon.png": png((32, 32))}
    with self.site(pages):
      self.assertTrue(Path(fetch_site(self.icon, "source.test", "dark")).is_file())
    self.assertEqual(self.requested[:3], list(pages))

  def test_oversized_and_invalid_images_are_not_cached(self):
    for payload in (b"x" * (self.icon.REMOTE_ICON_BYTES + 1), b"not an image"):
      with self.subTest(size=len(payload)), \
              self.site({"https://source.test/": b'<link rel="icon" href="/icon.png">',
                         "https://source.test/icon.png": payload, "https://source.test/favicon.ico": payload}):
        self.assertIsNone(fetch_site(self.icon, "source.test", "dark"))
        self.assertEqual(list(Path(self.cache).iterdir()), [])

  def test_fetch_disabled_never_requests(self):
    args = argparse.Namespace(source="source.test", app_icon="", app="", key="", scheme="dark", fetch=False)
    cached = self.icon.remote_cache_path("source.test", "dark")
    Path(cached).write_bytes(png((32, 32)))
    cases = [({}, (None, "none"))]
    if have_magick():  # a cache hit is decoded before it is trusted
      cases.append(({"source.test": {"dark": cached}}, (cached, "cache")))
    for index, expected in cases:
      with self.subTest(cached=bool(index)), self.site({}), \
              mock.patch.object(self.icon, "load_index", lambda i=index: i):
        # No fetcher, and fetching off: a lookup without --fetch never asks the launcher.
        self.assertEqual(self.icon.resolve(args), expected)
        self.assertEqual(self.requested, [])


if __name__ == "__main__":
  unittest.main()
