"""Local dev server: serves web/ and /api/report using the same core as Lambda."""
import json
import os
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import api

WEB = os.path.join(os.path.dirname(__file__), "web")


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=WEB, **k)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path.startswith("/api/"):
            qs = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            code, body = api.handle(u.path, qs)
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            super().do_GET()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"CampusShield on http://localhost:{port}")
    ThreadingHTTPServer(("", port), H).serve_forever()
