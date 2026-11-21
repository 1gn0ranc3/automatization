import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest


@pytest.fixture
def http_server():
    calls = []
    release_slow_request = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            parsed = urlsplit(self.path)
            calls.append(parsed.path)
            if parsed.path == "/links":
                html = Path(__file__).with_name("links.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
            size = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(size) if size else b"null"
            payload = json.dumps(
                {
                    "method": self.command,
                    "query": parse_qs(parsed.query),
                    "body": json.loads(body),
                    "api_key": self.headers.get("x-api-key"),
                }
            ).encode()
            if parsed.path == "/slow":
                release_slow_request.wait(2)
            status = {
                "/redirect": 302,
                "/unavailable": 503,
                "/created": 201,
                "/no-content": 204,
                "/invalid-url": 404,
            }.get(parsed.path, 200)
            if status == 204:
                payload = b""
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "/echo")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Клиент с коротким timeout уже закрыл соединение.

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        yield SimpleNamespace(url=f"http://127.0.0.1:{server.server_port}", calls=calls)
    finally:
        release_slow_request.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), "Local HTTP server did not stop"
