#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
filelocker — 故意埋 path traversal 漏洞的檔案儲物櫃服務(CONTRACTS.md §2.2)

只用 Python 標準庫(http.server),不依賴 Flask,部署零依賴。

合法 API(JSON over HTTP,session cookie):
  - POST /register {"u","p"}            → 200 {"ok":true}      ;重複帳號 → 409
  - POST /login    {"u","p"}            → 200 set-cookie       ;失敗 → 401
  - PUT  /file     {"name","content"}   → 200 {"stored": name} ;需登入,存到 data/<user>/<name>
  - GET  /file?name=<name>              → 200 {"name","content"};需登入
  - GET  /files                         → 200 {"files":[...]}  ;需登入,只列自己的

漏洞:GET /file 的 name 未正規化,直接 open(f"data/{user}/{name}"),
      所以 name=../<victim>/<file> 可跨目錄讀他人檔(path traversal)。
"""

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ── 設定 ────────────────────────────────────────────────────────────────
PORT = 9090
# 資料根目錄:固定在本檔案所在目錄下的 data/,確保 path traversal 的目錄結構為真
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# ── 記憶體狀態(單一進程,thread-safe 用一把鎖保護) ──────────────────────
_LOCK = threading.Lock()
USERS = {}      # username -> password(明碼,demo 用,真實環境請雜湊)
SESSIONS = {}   # session_token -> username


def _ensure_user_dir(user):
    """確保 data/<user>/ 目錄存在。"""
    user_dir = os.path.join(DATA_DIR, user)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


class Handler(BaseHTTPRequestHandler):
    # 關掉預設 stderr 存取記錄,保持輸出乾淨(驗證時較好讀)
    def log_message(self, fmt, *args):
        pass

    # ── 共用工具 ─────────────────────────────────────────────────────
    def _send_json(self, code, obj):
        """送出 JSON 回應。"""
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        """讀取請求 body 並解析 JSON;失敗回傳 None。"""
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _current_user(self):
        """從 Cookie 取出 session 對應的使用者;未登入回傳 None。"""
        cookie = self.headers.get("Cookie", "")
        token = None
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("session="):
                token = part[len("session="):]
                break
        if not token:
            return None
        with _LOCK:
            return SESSIONS.get(token)

    # ── POST:/register, /login, ────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/register":
            self._handle_register()
        elif path == "/login":
            self._handle_login()
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_register(self):
        data = self._read_json()
        if not data or "u" not in data or "p" not in data:
            self._send_json(400, {"error": "missing u/p"})
            return
        u, p = data["u"], data["p"]
        with _LOCK:
            if u in USERS:
                # 重複帳號 → 409(§2.2 / §2.1 慣例)
                self._send_json(409, {"error": "user exists"})
                return
            USERS[u] = p
        # 預先建立使用者目錄,確保之後 PUT/GET 路徑為真
        _ensure_user_dir(u)
        self._send_json(200, {"ok": True})

    def _handle_login(self):
        data = self._read_json()
        if not data or "u" not in data or "p" not in data:
            self._send_json(400, {"error": "missing u/p"})
            return
        u, p = data["u"], data["p"]
        with _LOCK:
            if USERS.get(u) != p:
                # 帳密不符 → 401
                self._send_json(401, {"error": "invalid credentials"})
                return
            token = secrets.token_hex(16)
            SESSIONS[token] = u
        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # 設定 session cookie
        self.send_header("Set-Cookie", f"session={token}; HttpOnly; Path=/")
        self.end_headers()
        self.wfile.write(body)

    # ── PUT:/file ───────────────────────────────────────────────────
    def do_PUT(self):
        path = urlparse(self.path).path
        if path == "/file":
            self._handle_put_file()
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_put_file(self):
        user = self._current_user()
        if user is None:
            self._send_json(401, {"error": "login required"})
            return
        data = self._read_json()
        if not data or "name" not in data or "content" not in data:
            self._send_json(400, {"error": "missing name/content"})
            return
        name, content = data["name"], data["content"]
        # PUT(寫入)走安全路徑:正規化後限制在自己的目錄內,避免寫到他人目錄。
        # 漏洞只埋在 GET(讀取)那條路徑,符合 §2.2「讀」的 path traversal。
        user_dir = _ensure_user_dir(user)
        target = os.path.normpath(os.path.join(user_dir, name))
        if os.path.commonpath([target, user_dir]) != user_dir:
            self._send_json(403, {"error": "invalid name"})
            return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else str(content))
        self._send_json(200, {"stored": name})

    # ── GET:/file, /files ──────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/file":
            self._handle_get_file(parsed)
        elif parsed.path == "/files":
            self._handle_get_files()
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_get_file(self, parsed):
        user = self._current_user()
        if user is None:
            self._send_json(401, {"error": "login required"})
            return
        qs = parse_qs(parsed.query)
        names = qs.get("name")
        if not names:
            self._send_json(400, {"error": "missing name"})
            return
        name = names[0]
        # ┌──────────────────────────────────────────────────────────┐
        # │ 故意漏洞(path traversal):name 未經正規化,直接拼進路徑   │
        # │ 並 open(),因此 name=../<victim>/<file> 可跳出自己目錄,    │
        # │ 讀到其他使用者(甚至系統)的檔案。                          │
        # │ 安全堵法見 README:normpath 後須仍落在 data/<user>/ 內。    │
        # └──────────────────────────────────────────────────────────┘
        filepath = os.path.join(DATA_DIR, user, name)   # ← 漏洞行:未正規化
        try:
            with open(filepath, "r", encoding="utf-8") as f:   # ← 漏洞行:直接 open
                content = f.read()
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            self._send_json(404, {"error": "not found"})
            return
        except OSError:
            self._send_json(404, {"error": "not found"})
            return
        self._send_json(200, {"name": name, "content": content})

    def _handle_get_files(self):
        user = self._current_user()
        if user is None:
            self._send_json(401, {"error": "login required"})
            return
        user_dir = os.path.join(DATA_DIR, user)
        files = []
        if os.path.isdir(user_dir):
            # 只列出自己目錄下的一般檔案(平面列表,checker GET 用)
            for entry in sorted(os.listdir(user_dir)):
                if os.path.isfile(os.path.join(user_dir, entry)):
                    files.append(entry)
        self._send_json(200, {"files": files})


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"filelocker listening on :{PORT}, data dir = {DATA_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
