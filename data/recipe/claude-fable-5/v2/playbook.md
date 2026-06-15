# Playbook (v2)：已知攻法與安全堵法

## notes：IDOR
`GET /note?id=` 未檢查擁有者。堵法：加 `owner == current_user`；保留 `/notes`。

## filelocker：path traversal
`GET /file?name=` 未正規化。堵法：`normpath` 後須在 `data/<user>/` 內，否則 403。
另需擋 URL 編碼繞過（`%2e%2e`）。

## vault：OOB read
`GET <idx>` 未檢查邊界。堵法：只允許讀自己的 slot。
