# services — 漏洞服務(進黃金映像,D/A 共用)

故意埋洞的服務,隨黃金映像部署到防禦/攻擊主機。設計不變量見 [CTF_SPEC.md §1.6](../CTF_SPEC.md)。

| 服務 | 埠 | 類型 | 難度 | 漏洞方向 |
|---|---|---|---|---|
| `notes/` | 8080 | web (Flask) | 中(主力) | IDOR / 注入 |
| `filelocker/` | 9090 | injection | 易(基線) | path traversal / 命令注入 |
| `vault/` | 10000 | pwn (C daemon) | 難(上限) | 記憶體破壞 |

> ⚠️ 僅供隔離網段內的攻防鍛造,切勿部署到公開環境。
