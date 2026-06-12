# filelocker — 檔案儲物櫃服務(path traversal 漏洞)

A/D CTF 攻防工坊的「易/基線」服務。Python 標準庫 `http.server` 實作,**零第三方依賴**,
監聽 `:9090`。嚴格遵循 [`CONTRACTS.md §2.2`](../../CONTRACTS.md) 的 wire API。

> ⚠️ 故意埋洞,僅供隔離網段內攻防鍛造,切勿部署到公開環境。

---

## 合法 API(JSON over HTTP,session cookie)

| 方法 | 路徑 | Body / Query | 需登入 | 成功 | 失敗 |
|---|---|---|---|---|---|
| `POST` | `/register` | `{"u","p"}` | 否 | `200 {"ok":true}` | 重複帳號 `409` |
| `POST` | `/login` | `{"u","p"}` | 否 | `200` + `Set-Cookie: session=...` | 帳密錯 `401` |
| `PUT` | `/file` | `{"name","content"}` | 是 | `200 {"stored": name}` | 未登入 `401` |
| `GET` | `/file` | `?name=<name>` | 是 | `200 {"name","content"}` | 未登入 `401` / 找不到 `404` |
| `GET` | `/files` | — | 是 | `200 {"files":[<name>...]}`(只列自己的) | 未登入 `401` |

- 檔案實際存放於 `data/<user>/<name>`(目錄結構為真,traversal 才成立)。
- session 以 cookie `session=<token>` 維持;登入回 `Set-Cookie`,後續請求帶 `Cookie`。
- `PUT /file`(寫入)走**安全路徑**:`name` 正規化後限制在自己目錄內,越界回 `403`。
  漏洞只埋在 `GET`(讀取),符合 §2.2「讀」的 path traversal 定義。

---

## 漏洞:path traversal(GET /file)

`GET /file?name=` 的 `name` **未經正規化**,直接拼進路徑並 `open()`,
因此 `name=../<victim>/<file>` 可跳出自己的目錄,讀到其他使用者的檔案。

漏洞位置 **`app.py`**:

- **第 190 行** — `filepath = os.path.join(DATA_DIR, user, name)`(未正規化,`name` 含 `../` 直接生效)
- **第 192 行** — `with open(filepath, "r", ...) as f:`(直接開啟跨目錄的路徑)

(對應 `_handle_get_file()` 方法內已用框線註解標出。)

attack_data(§2.2)= `{"user","name"}`,即受害者的 `user` 與 `name`。

---

## 怎麼跑

```bash
# 直接跑(零依賴)
python3 app.py
# → filelocker listening on :9090, data dir = .../services/filelocker/data

# 或用 Docker(低權限 user,EXPOSE 9090)
docker build -t filelocker .
docker run --rm -p 9090:9090 filelocker
```

## 怎麼打(exploit)

```bash
# 用法:python3 exploit.py <host> <victim_user> <victim_name> [--port 9090]
python3 exploit.py 127.0.0.1 bob flag.txt
```

exploit 流程:自建攻擊者帳號 → 登入取得 session →
`GET /file?name=../<victim_user>/<victim_name>` 讀出受害者 flag。

實測輸出:

```
[*] 攻擊者帳號 atk_xxxxxxxx 已建立
[*] 登入成功,已取得 session cookie
[+] traversal name = ../bob/flag.txt
[+] 偷到 bob/flag.txt 的內容(flag):
FLAG{bob_secret_123}
```

---

## 安全堵法(§2.2)

`name` 經 `os.path.normpath` 正規化後,須仍落在 `data/<user>/` 目錄內,否則回 `403`。
這樣可擋掉 `../` 跳目錄,同時保留合法的同目錄存取。修補範例(改 `_handle_get_file`):

```python
user_dir = os.path.join(DATA_DIR, user)
filepath = os.path.normpath(os.path.join(user_dir, name))
# 正規化後仍須在自己的目錄內,否則拒絕
if os.path.commonpath([os.path.abspath(filepath), os.path.abspath(user_dir)]) != os.path.abspath(user_dir):
    self._send_json(403, {"error": "forbidden"})
    return
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()
```

> 註:本服務的 `PUT /file`(寫入)已採用此堵法,可直接照抄到 `GET` 路徑修補。
