"""The pinned HTTPS client against an owned loopback TLS server.

Only the DNS answer is substituted, so the request, TLS handshake, redirect
and size handling are the real code path; nothing leaves the machine.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from support import have_openssl
import notification_http as net


class Handler(BaseHTTPRequestHandler):
  def log_message(self, *args):
    pass

  def do_GET(self):
    if self.path == '/private':
      self.send_response(302)
      self.send_header('Location', 'https://127.0.0.1/secret')
      self.end_headers()
    elif self.path == '/loop':
      self.send_response(302)
      self.send_header('Location', '/loop')
      self.end_headers()
    else:
      body = b'ok' if self.path == '/ok' else b'x' * 2048
      self.send_response(200)
      self.send_header('Content-Length', str(len(body)))
      self.end_headers()
      try:
        self.wfile.write(body)
      except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
        pass


class HttpsTransport(unittest.TestCase):
  def test_body_private_redirect_loop_and_size_cap(self):
    if not have_openssl():
      self.skipTest("openssl is not installed; cannot make the TLS fixture")
    with tempfile.TemporaryDirectory(prefix='omarchy-notification-tls-') as directory:
      cert, key = Path(directory) / 'cert.pem', Path(directory) / 'key.pem'
      subprocess.run([
          'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
          '-keyout', str(key), '-out', str(cert), '-days', '1',
          '-subj', '/CN=example.com', '-addext', 'subjectAltName=DNS:example.com',
      ], check=True, capture_output=True)
      server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
      server_context.minimum_version = ssl.TLSVersion.TLSv1_2
      server_context.load_cert_chain(cert, key)
      client_context = ssl.create_default_context(cafile=str(cert))
      client_context.minimum_version = ssl.TLSVersion.TLSv1_2
      server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
      server.socket = server_context.wrap_socket(server.socket, server_side=True)
      thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
      thread.start()
      answer = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', server.server_address)]
      try:
        with patch.object(net, 'resolve_public_answers', return_value=answer), \
                patch.object(net.ssl, 'create_default_context', return_value=client_context):
          self.assertEqual(net.fetch('https://example.com/ok', 100)[0], b'ok')
          for route in ('private', 'loop', 'large'):
            with self.subTest(route=route), self.assertRaises(ValueError):
              net.fetch('https://example.com/' + route, 100)
      finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
  unittest.main()
