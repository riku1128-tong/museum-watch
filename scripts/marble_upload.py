"""marble_bake.html から PUT された大理石の JPEG を docs/ に保存するだけのローカルサーバー（127.0.0.1:8792）。

    uv run scripts/marble_upload.py
"""

from http.server import BaseHTTPRequestHandler, HTTPServer

from common import SITE

ALLOWED = {"marble-light.jpg", "marble-dark.jpg"}


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_PUT(self):
        name = self.path.lstrip("/")
        if name not in ALLOWED:
            self.send_response(404)
            self._cors()
            self.end_headers()
            return
        data = self.rfile.read(int(self.headers["Content-Length"]))
        (SITE / name).write_bytes(data)
        print(f"saved {name} {len(data) // 1024} KB", flush=True)
        self.send_response(204)
        self._cors()
        self.end_headers()


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8792), Handler).serve_forever()
