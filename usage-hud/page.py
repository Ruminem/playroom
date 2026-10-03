# SPDX-License-Identifier: Apache-2.0
"""HUD 와 같은 값을 브라우저에 레트로 게임 화면으로 — 7일치 일별 정가 막대를 더해서.

  python page.py              http://127.0.0.1:8765 를 띄우고 브라우저로 엶
  python page.py --port 9000
  python page.py --no-open

127.0.0.1 에만 연다. 세션 기록에서 뽑은 값이라 같은 망의 다른 기기에 보일 이유가 없다.
"""
import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import usage
from font import COLORS, GLYPHS, ICONS

PAGE = Path(__file__).resolve().parent / "page.html"
FONT = json.dumps({"glyphs": GLYPHS, "icons": ICONS, "colors": COLORS})
lock = threading.Lock()  # usage 의 캐시는 프로세스 전역이라 요청 스레드끼리 겹치지 않게


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            # 요청마다 읽는다 — page.html 을 고치면 새로고침만 하면 된다
            body = PAGE.read_text(encoding="utf-8").replace("/*FONT*/null", FONT)
            self.send(body, "text/html; charset=utf-8")
        elif self.path == "/data.json":
            with lock:
                body = json.dumps(usage.snapshot(days=7))
            self.send(body, "application/json")
        else:
            self.send_error(404)

    def send(self, body, ctype):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass  # 30초마다 오는 요청으로 콘솔을 채우지 않음


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="브라우저를 열지 않음")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = "http://127.0.0.1:%d/" % args.port
    print(url, "— 끄려면 Ctrl+C")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
