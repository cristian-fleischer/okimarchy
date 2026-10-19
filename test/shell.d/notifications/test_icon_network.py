"""Focused tests for pinned HTTPS transport and remote icon resolution.

DNS is synthetic. Only public fixture addresses are routed to a server owned
by this test; every other connect is refused before any network operation.
Redirects, TLS handshakes and certificate hostname checks are real.
"""
import argparse
import collections
import contextlib
import http.server
import errno
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from support import have_magick, have_openssl, load_helper, png

PUBLIC = "93.184.216.34"
PUBLIC_V6 = "2606:4700:4700::1111"
BLOCKED = (
    "127.0.0.1", "10.0.0.1", "169.254.169.254", "240.0.0.1",
    "::1", "fd00::1", "fe80::1", "4000::1",
)

def load_icon_module():
  return load_helper("icon", "notification_icon_network")



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
        if redirect and self.path == "/start":
          self.send_response(302)
          target_scheme = redirect_scheme or scheme
          self.send_header("Location", f"{target_scheme}://target.test/icon")
          body = b""
        else:
          self.send_response(200)
          body = b"fixture icon"
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
        icon = load_icon_module()
        yield icon.get, state
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
    for address in BLOCKED + ("224.0.0.1", "ff02::1", "0.0.0.0", "::"):
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

  def test_public_address_fallback_retains_hostname(self):
    with self.transport("https", answers=lambda _host: [PUBLIC_V6, PUBLIC],
                        fail_first=True) as (get, state):
      self.assertEqual(get("https://source.test/icon"),
                       (b"fixture icon", "https://source.test/icon"))
      self.assertEqual(state["attempts"], [PUBLIC_V6, PUBLIC])
      self.assertEqual(state["requests"], [("source.test", "/icon")])
      self.assertEqual(state["sni"], ["source.test"])

  def test_socket_family_failure_uses_validated_fallback(self):
    with self.transport("https", answers=lambda _host: [PUBLIC_V6, PUBLIC]) as (get, state):
      real_socket = socket.socket

      def supported_socket(family, *args, **kwargs):
        if family == socket.AF_INET6:
          raise OSError(errno.EAFNOSUPPORT, "Synthetic IPv6 unavailable")
        return real_socket(family, *args, **kwargs)

      with mock.patch.object(socket, "socket", supported_socket):
        self.assertEqual(get("https://source.test/icon"),
                         (b"fixture icon", "https://source.test/icon"))
      self.assertEqual(state["attempts"], [PUBLIC])
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
  def load_icon(self):
    return vars(load_icon_module())

  def no_local_icons(self, icon):
    return mock.patch.dict(icon, {
        "from_config": lambda _names: None,
        "from_icon_theme": lambda _names: None,
        "from_desktop_entries": lambda _names: None,
    })

  def test_html_and_manifest_candidates_are_https_only(self):
    icon = self.load_icon()
    html = """
      <link rel="icon" sizes="256x256" href="https://cdn.test/icon.png">
      <link rel="icon" href="//target.test/icon.png">
      <link rel="icon" href="http://target.test/downgrade.png">
      <link rel="icon" href="https://user:secret@target.test/private.png">
      <link rel="manifest" href="/site.webmanifest">
    """
    links = icon["icon_links"](html, "https://source.test/app/", "dark")
    self.assertEqual(links, [
        "https://cdn.test/icon.png",
        "https://target.test/icon.png",
        ("manifest", "https://source.test/site.webmanifest"),
    ])
    self.assertEqual(icon["icon_links"](None, "https://source.test/", "dark"), [])
    self.assertEqual(icon["icon_links"](
        '<link href><link rel="icon" href="/still-valid.png">',
        "https://source.test/", "dark"),
        ["https://source.test/still-valid.png"])


    manifest = json_bytes({"icons": [
        {"src": "icon.png", "sizes": "128x128"},
        {"src": "http://target.test/downgrade.png", "sizes": "64x64"},
        None,
        {"src": "https://127.0.0.1/private.png", "sizes": "32x32"},
        {"src": 7},
    ]})
    with mock.patch.dict(icon, {"get": lambda *_args: (
            manifest, "https://target.test/assets/site.webmanifest")}):
      self.assertEqual(icon["from_manifest"](
          "https://source.test/site.webmanifest", "https://source.test/"),
          ["https://target.test/assets/icon.png"])

  def test_malformed_manifests_are_contained(self):
    icon = self.load_icon()
    malformed = (b"{", b"[]", b'{"icons":{}}',
                 b'{"icons":[null,4,{"src":3}]}')
    for payload in malformed:
      with self.subTest(payload=payload), \
              mock.patch.dict(icon, {"get": lambda *_args, p=payload: (
                  p, "https://source.test/site.webmanifest")}):
        self.assertEqual(icon["from_manifest"](
            "https://source.test/site.webmanifest", "https://source.test/"), [])

  def test_malformed_manifest_does_not_hide_a_later_page_icon(self):
    if not have_magick():
      self.skipTest("imagemagick is not installed")
    icon = self.load_icon()
    image = png((32, 32))
    requested = []

    def get(url, _limit):
      requested.append(url)
      if url == "https://source.test/":
        return (b'<link rel="manifest" href="/bad.webmanifest">'
                b'<link rel="icon" href="/icon.png">', url)
      if url.endswith("bad.webmanifest"):
        return b'{"icons":{}}', url
      if url.endswith("icon.png"):
        return image, url
      raise AssertionError("unexpected request " + url)

    with tempfile.TemporaryDirectory() as temp, \
            mock.patch.dict(icon, {"CACHE": temp, "get": get}):
      path = icon["fetch_site"]("source.test", "dark")
      self.assertIsNotNone(path)
      self.assertTrue(Path(path).is_file())
    self.assertEqual(requested, [
        "https://source.test/",
        "https://source.test/bad.webmanifest",
        "https://source.test/icon.png",
    ])

  def test_oversized_and_invalid_images_are_not_cached(self):
    icon = self.load_icon()
    for payload in (b"x" * (icon["REMOTE_ICON_BYTES"] + 1), b"not an image"):
      with self.subTest(size=len(payload)), tempfile.TemporaryDirectory() as temp:
        def get(url, _limit):
          if url == "https://source.test/":
            return b'<link rel="icon" href="/icon.png">', url
          return payload, url
        with mock.patch.dict(icon, {"CACHE": temp, "get": get}):
          self.assertIsNone(icon["fetch_site"]("source.test", "dark"))
          self.assertEqual(list(Path(temp).iterdir()), [])

  def test_fetch_disabled_uses_valid_cache_without_any_request(self):
    if not have_magick():
      self.skipTest("imagemagick is not installed")
    icon = self.load_icon()
    args = argparse.Namespace(source="source.test", app_icon="", app="", key="",
                              scheme="dark", fetch=False)
    with tempfile.TemporaryDirectory() as temp, mock.patch.dict(icon, {"CACHE": temp}):
      cached = icon["remote_cache_path"]("source.test", "dark")
      Path(cached).write_bytes(png((32, 32)))
      os.chmod(cached, 0o600)
      index = {"source.test": {"dark": cached}}

      def forbidden(*_args):
        raise AssertionError("fetching disabled must not request")

      with mock.patch.dict(icon, {"load_index": lambda: index,
                                  "fetch_site": forbidden, "get": forbidden}), \
              self.no_local_icons(icon):
        self.assertEqual(icon["resolve"](args), (cached, "cache"))

  def test_fetch_disabled_without_cache_never_calls_fetcher(self):
    icon = self.load_icon()
    args = argparse.Namespace(source="source.test", app_icon="", app="", key="",
                              scheme="dark", fetch=False)

    def forbidden(*_args):
      raise AssertionError("fetching disabled must not request")

    with mock.patch.dict(icon, {"load_index": lambda: {}, "fetch_site": forbidden,
                                "get": forbidden}), self.no_local_icons(icon):
      self.assertEqual(icon["resolve"](args), (None, "none"))


def json_bytes(value):
  import json
  return json.dumps(value).encode()


if __name__ == "__main__":
  unittest.main()
