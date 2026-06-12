#!/usr/bin/env python3
"""notes 服務 — A/D CTF 攻防工坊故意埋洞標的(Flask, port 8080)。

實作 CONTRACTS.md §2.1 的合法 wire API(JSON over HTTP,session cookie)。
**故意漏洞(IDOR)**:GET /note?id= 不檢查 note 擁有者,任何登入者可讀任何 id 的 note。
其餘合法功能正確:register 重複帳號回 409、未登入回 401。

儲存:純記憶體 dict(本服務每輪重置即可,flag 由 checker 重新種入)。
"""
import os
from flask import Flask, request, jsonify, session

app = Flask(__name__)
# session cookie 簽章用的密鑰;固定值即可(本服務的價值不在 cookie 防偽,而在示範 IDOR)
app.secret_key = os.environ.get("NOTES_SECRET", "ctf-works-notes-demo-key")

# ── 記憶體儲存 ────────────────────────────────────────────────
# users:{username: password}
users: dict[str, str] = {}
# notes:{note_id: {"note_id": int, "body": str, "owner": str}}
notes: dict[int, dict] = {}
# 遞增整數 id 計數器(下一個要配發的 note_id)
next_note_id = 1


def current_user():
    """回傳目前 session 登入的使用者名稱,未登入回 None。"""
    return session.get("u")


# ── POST /register ───────────────────────────────────────────
@app.route("/register", methods=["POST"])
def register():
    """註冊帳號。成功 200 {"ok":true};帳號重複 409。"""
    data = request.get_json(silent=True) or {}
    u = data.get("u")
    p = data.get("p")
    # 帳號/密碼皆必填,缺欄位視為 400 壞請求
    if not u or not p:
        return jsonify({"error": "missing u or p"}), 400
    # 帳號重複 → 409 Conflict(契約規定)
    if u in users:
        return jsonify({"error": "user exists"}), 409
    users[u] = p
    return jsonify({"ok": True}), 200


# ── POST /login ──────────────────────────────────────────────
@app.route("/login", methods=["POST"])
def login():
    """登入。成功 200 並 set-cookie session;帳密錯誤 401。"""
    data = request.get_json(silent=True) or {}
    u = data.get("u")
    p = data.get("p")
    # 帳號不存在或密碼不符 → 401(契約規定)
    if u not in users or users[u] != p:
        return jsonify({"error": "invalid credentials"}), 401
    # 寫入 session,Flask 會回 set-cookie
    session["u"] = u
    return jsonify({"ok": True}), 200


# ── POST /note ───────────────────────────────────────────────
@app.route("/note", methods=["POST"])
def create_note():
    """建立 note(需登入)。回 200 {"note_id": <int>}。未登入 401。"""
    user = current_user()
    if user is None:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    body = data.get("body")
    if body is None:
        return jsonify({"error": "missing body"}), 400
    global next_note_id
    nid = next_note_id
    next_note_id += 1
    # owner 欄位記錄擁有者,合法讀取(/notes)與安全堵法都靠它
    notes[nid] = {"note_id": nid, "body": body, "owner": user}
    return jsonify({"note_id": nid}), 200


# ── GET /note?id=<int> ───────────────────────────────────────
@app.route("/note", methods=["GET"])
def get_note():
    """讀單篇 note(需登入)。回 200 {"note_id","body","owner"}。

    **故意漏洞(IDOR)**:見下方註解標記的那一行 —
    這裡只檢查「有沒有登入」,卻不檢查「這篇 note 是不是你的」,
    所以任何登入者都能用任意 id 讀出別人的 note(含 flag)。
    """
    user = current_user()
    if user is None:
        return jsonify({"error": "unauthorized"}), 401
    # 解析 id 參數,非整數 → 400
    try:
        nid = int(request.args.get("id", ""))
    except (TypeError, ValueError):
        return jsonify({"error": "bad id"}), 400
    note = notes.get(nid)
    if note is None:
        return jsonify({"error": "not found"}), 404
    # ★★★ IDOR 漏洞就在這裡:直接回傳 note,完全沒有
    #     `if note["owner"] != user: return 403` 的擁有者檢查。
    #     安全堵法:在這一行前加上
    #         if note["owner"] != user:
    #             return jsonify({"error": "forbidden"}), 403
    return jsonify(
        {"note_id": note["note_id"], "body": note["body"], "owner": note["owner"]}
    ), 200


# ── GET /notes ───────────────────────────────────────────────
@app.route("/notes", methods=["GET"])
def list_notes():
    """列出「自己的」note(需登入),checker GET 用。

    這個端點有正確做擁有者過濾(owner == 目前使用者),
    所以 checker 取 flag 走這裡是安全的;漏洞只在單篇 GET /note。
    """
    user = current_user()
    if user is None:
        return jsonify({"error": "unauthorized"}), 401
    mine = [
        {"note_id": n["note_id"], "body": n["body"]}
        for n in notes.values()
        if n["owner"] == user
    ]
    return jsonify({"notes": mine}), 200


if __name__ == "__main__":
    # 0.0.0.0 讓容器外可連;port 固定 8080(契約)
    app.run(host="0.0.0.0", port=8080)
