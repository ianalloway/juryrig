"""A judge endpoint that redirects must not receive-and-forward the API key."""

import http.server
import threading
import unittest

from juryrig.providers import RetryPolicy, _http_json


class _Sink(http.server.BaseHTTPRequestHandler):
    seen: list = []

    def do_GET(self):  # noqa: N802
        _Sink.seen.append(self.headers.get("Authorization"))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    do_POST = do_GET  # noqa: N815

    def log_message(self, *args):
        pass


def _serve(handler, host):
    server = http.server.HTTPServer((host, 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class NoRedirectTest(unittest.TestCase):
    def test_cross_host_redirect_is_refused_and_key_not_forwarded(self):
        _Sink.seen = []
        sink = _serve(_Sink, "127.0.0.1")
        target = f"http://localhost:{sink.server_port}/steal"

        class _Redirector(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                self.send_response(302)
                self.send_header("Location", target)
                self.end_headers()

            def log_message(self, *args):
                pass

        origin = _serve(_Redirector, "127.0.0.1")
        try:
            with self.assertRaises(RuntimeError):
                _http_json(
                    f"http://127.0.0.1:{origin.server_port}/v1",
                    {"Authorization": "Bearer fake-test-key"},
                    {},
                    retry=RetryPolicy(attempts=1),
                    sleep=lambda _s: None,
                )
        finally:
            origin.shutdown()
            sink.shutdown()
        self.assertEqual(_Sink.seen, [])


if __name__ == "__main__":
    unittest.main()
