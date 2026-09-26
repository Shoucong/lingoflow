"""Exercise real blocked sockets rather than an already-buffered mock response."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lingoflow.infrastructure.ollama_client import OllamaCancelledError, OllamaClient


@pytest.mark.parametrize("send_first_chunk", [False, True])
def test_cancellation_closes_blocked_http_stream(send_first_chunk):
    started = threading.Event()
    disconnected = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Connection", "close")
            self.end_headers()
            if send_first_chunk:
                self.wfile.write(b'{"message":{"content":"partial"},"done":false}\n')
            self.wfile.flush()
            started.set()
            self.connection.settimeout(3)
            try:
                if self.rfile.read(1) == b"":
                    disconnected.set()
            except OSError:
                pass

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    client = OllamaClient(f"http://127.0.0.1:{server.server_port}")
    errors = []

    def consume():
        try:
            list(client.chat_stream("synthetic input", "test-model"))
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=consume, daemon=True)
    try:
        worker.start()
        assert started.wait(2)
        client.cancel()
        worker.join(2)
        assert not worker.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], OllamaCancelledError)
        assert disconnected.wait(1)
        assert client._streams.active_count == 0
    finally:
        client.cancel()
        server.shutdown()
        server.server_close()
        worker.join(3)
