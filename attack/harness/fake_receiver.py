#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fake_receiver.py — 離線示範用的假 flag 接收埠。

只在「想跑非 dry-run、又沒有真 gameserver」時用。它假裝成 ForcAD 的 flag
接收埠:PUT /flags(body 為 flag list)一律回 200 並印出收到的 flag。
真實部署用 ForcAD 提供的接收埠,不用這支。

用法:
  python3 fake_receiver.py --port 31337
然後 submit_loop.py 用:
  --gameserver-host 127.0.0.1 --flag-submit-port 31337   (不要 --dry-run)
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_PUT(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else "[]"
        token = self.headers.get("X-Team-Token", "<none>")
        try:
            flags = json.loads(raw)
        except Exception:
            flags = [raw]
        for fl in flags:
            print(f"[fake-receiver] 收到 flag(token={token}):{fl}", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"accepted": true}')

    def log_message(self, *a):
        pass  # 靜音預設存取日誌,只留我們自己的列印


def main():
    ap = argparse.ArgumentParser(description="離線假 flag 接收埠")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=31337)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[fake-receiver] 監聽 http://{args.host}:{args.port}/flags (PUT)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
