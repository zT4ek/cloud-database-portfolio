"""Run the portfolio locally with `python preview.py`. No AWS credentials are needed."""

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


SITE = Path(__file__).resolve().parent / "site"
PUBLIC_URL = "https://d3toenag1cweob.cloudfront.net"


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def do_GET(self):
        if urlsplit(self.path).path != "/config.json":
            return super().do_GET()

        try:
            with urlopen(PUBLIC_URL + "/config.json", timeout=10) as response:
                live = json.load(response)
            settings = {
                "apiUrl": live["apiUrl"],
                "readKey": live["readKey"],
                "previewGuestbookUrl": PUBLIC_URL + "/guestbook.html",
            }
        except (URLError, TimeoutError, ValueError, KeyError):
            self.send_error(503, "Public guestbook settings are unavailable")
            return

        body = json.dumps(settings).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    with ThreadingHTTPServer(("127.0.0.1", parser.parse_args().port), PreviewHandler) as server:
        print(f"Portfolio preview: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
