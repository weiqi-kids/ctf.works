# Playbook — 已知攻法與安全堵法(配方記憶起點)

> 這是 defense-recipe 的記憶。種子內容是三個已知洞 + 各自的安全堵法(可操作步驟)。
> `run.sh` 每輪的防禦 agent 讀此檔快速上手,並在末尾 append「這輪擋下/沒擋下什麼」。
> 規則:**只 append,不刪改歷史條目。** 三洞安全堵法皆對齊 `CONTRACTS.md §2.*` 與各服務 README。

---

## 洞 1 — notes:IDOR(Insecure Direct Object Reference)

- **服務**:notes(Flask, `:8080`)
- **漏洞點**:`services/notes/app.py` 的 `get_note()`(`GET /note?id=<int>`)。
  該端點只驗「有沒有登入」,**沒有**驗「這篇 note 的 owner 是不是目前使用者」,
  因此任何登入者可用任意 `id` 讀出別人的 note body(= flag)。
- **攻法**:攻擊者自建帳號登入 → `GET /note?id=<victim note_id>` → 直接拿到他人 flag。
  attack_data = victim 的 `note_id`(int)。
- **安全堵法(可操作步驟)**:
  1. 開 `services/notes/app.py`,找 `def get_note()`。
  2. 在取得 `note`(`note = notes.get(nid)`、`not found` 檢查之後)、`return jsonify({...})` **之前**,加:
     ```python
     if note["owner"] != user:
         return jsonify({"error": "forbidden"}), 403
     ```
  3. **不要動** `list_notes()`(`GET /notes`)—— 它本來就以 `owner == user` 過濾,checker GET 走這裡,動了會壞 SLA。
- **為何不破壞合法功能**:擁有者讀自己的 note 仍 200;`/notes` 不受影響;checker put/get/check 照常。
- **驗證**:`self_verify/notes_verify.sh` —— exploit 應被 403 擋下(偷不到);
  合法使用者讀自己 note 應 200 且 body 正確。

---

## 洞 2 — filelocker:path traversal

- **服務**:filelocker(Python `http.server`, `:9090`)
- **漏洞點**:`services/filelocker/app.py` 的 `_handle_get_file()`(`GET /file?name=<name>`)。
  約第 190 行 `filepath = os.path.join(DATA_DIR, user, name)` 未正規化,`name=../<victim>/<file>`
  可跳出自己目錄,讀他人檔。(寫入端 `_handle_put_file()` 已安全,只有讀端有洞。)
- **攻法**:攻擊者自建帳號登入 → `GET /file?name=../<victim_user>/<victim_name>` → 讀出他人 flag。
  attack_data = `{"user","name"}`。
- **安全堵法(可操作步驟)**:
  1. 開 `services/filelocker/app.py`,找 `def _handle_get_file(self, parsed)`。
  2. 把「直接 join + open」改成「正規化後驗證仍在使用者目錄內」(照抄同檔 `_handle_put_file` 的堵法):
     ```python
     user_dir = os.path.join(DATA_DIR, user)
     filepath = os.path.normpath(os.path.join(user_dir, name))
     if os.path.commonpath([os.path.abspath(filepath), os.path.abspath(user_dir)]) != os.path.abspath(user_dir):
         self._send_json(403, {"error": "forbidden"})
         return
     # ...原本的 open(filepath) 讀檔不變
     ```
  3. 一併確認 **URL 編碼繞過**(`%2e%2e` = `..`)也被擋:`http.server` 解析 query 時已 decode,
     正規化能涵蓋;驗證時要實測 `%2e%2e%2f` 變體。
- **為何不破壞合法功能**:合法 `name`(自己目錄內的檔名)正規化後仍在 `user_dir`,照常 200;
  只有跳目錄的 `name` 被擋。checker put/get/check 不受影響。
- **驗證**:`self_verify/filelocker_verify.sh` —— traversal exploit 應被 403 擋下;
  合法使用者 PUT 再 GET 自己的檔應 200 且 content 正確。

---

## 洞 3 — vault:OOB read(越界 / 跨 slot 讀取)

- **服務**:vault(C daemon, line-based TCP `:10000`)
- **漏洞點**:`services/vault/vault.c` 的 `GET` 指令處理(約 253–262 行)。
  第 253 行 `int idx = atoi(arg);` 直接取使用者輸入;第 262 行 `snprintf(...secrets[idx]...)`
  **未檢查 `0 <= idx < N`** 就索引,任何已 AUTH session 可 `GET <別人的 slot>` 讀他人 secret;
  極端 idx(負數 / 超大值)更會越界讀陣列外記憶體。
- **攻法**:攻擊者 `REGISTER` → `AUTH`(合法 session)→ `GET <victim_slot>` → 讀出他人 secret(flag)。
  attack_data = victim 的 `slot`(int)。
- **安全堵法(可操作步驟)**:
  1. 開 `services/vault/vault.c`,找 `GET` 指令處理(`int idx = atoi(arg);` 那段)。
  2. 在 `snprintf(out, ... secrets[idx])` **之前**加邊界檢查,**只允許讀自己的 slot**:
     ```c
     int idx = atoi(arg);
     if (idx != my_slot) {            /* 同時擋負數、超大值、atoi 溢位回的怪值 */
         send_str(fd, "ERR\n");
         continue;
     }
     ```
     (若需保留讀任意「自己有效」slot 的語意,至少 `if (idx < 0 || idx >= N || idx != my_slot)`。)
  3. **重新編譯並重啟 daemon**:`cd services/vault && make && (重啟 ./vault)`。C 服務改碼必須重編,否則無效。
- **要點**:`idx != my_slot` 天然涵蓋負數與整數溢位(`atoi` 對溢位回的怪值也 `!= my_slot`)。
  這正是 PROMPT 鐵律「vault 補丁須同時擋負數 idx 與整數溢位」的落點。
- **為何不破壞合法功能**:`GET <own_slot>` 仍正常,checker get 與合法使用者讀自己 slot 不受影響。
- **驗證**:`self_verify/vault_verify.sh` —— 跨 slot / 負數 / 超大 idx 的 GET 應回 ERR(偷不到);
  合法使用者 SET 後 `GET <own_slot>` 應回 `SECRET <自己的值>`;`PING` 應回 `PONG`。

---

## 巡檢與修補總則(每輪共通)

1. 對三服務各跑一次對應 self_verify,先確認「洞是否已堵」「合法功能是否正常」。
2. 對還開著的洞,照上面「安全堵法」步驟出**最小 diff**。
3. 改完跑 self_verify:**exploit 失敗 + 合法功能通過**,兩條都過才接受;否則**回滾**。
4. 把本輪結果 append 到下方「巡檢日誌」。

---

## 巡檢日誌(防禦 agent 每輪 append,只增不刪)

> 種子狀態:三洞皆**已知未堵**(初始 vulnbox 即帶洞)。run.sh 第一輪起會逐一堵並記錄於此。

<!-- 範例格式(agent 每輪追加):
## round 1 (2026-06-12T12:00:00Z)
- notes: IDOR 仍可讀他人 note → get_note() 加 owner 檢查 → self_verify PASS,已堵
- filelocker: GET /file traversal 仍可跳目錄 → _handle_get_file 加 normpath+commonpath → self_verify PASS,已堵
- vault: GET <victim_slot> 仍可跨 slot 讀 → 加 idx==my_slot 檢查並 make 重啟 → self_verify PASS,已堵
-->
