# gameserver — ROLE G 計分主機(ForcAD)

ForcAD 計分主機的設定與 checkers。本目錄不放 AI、不跑漏洞服務,
只負責「每 round 對各 team 的服務種 flag / 取 flag / 判活性」並計分。

依據:[`../CONTRACTS.md`](../CONTRACTS.md) §1(checker API)、§2.*(各服務 wire API)、
[`../topology.yml`](../topology.yml)(teams / 埠 / round 參數)。

---

## 目錄結構

```
gameserver/
├── config.yml.example          # ForcAD 設定範本(複製為 config.yml 使用)
└── checkers/
    ├── requirements.txt         # checklib==0.7.0、requests
    ├── notes/checker.py         # notes(:8080,IDOR)checker
    ├── filelocker/checker.py    # filelocker(:9090,path traversal)checker
    └── vault/checker.py         # vault(:10000,OOB read,TCP)checker
```

- checker 皆為 checklib==0.7.0 的 **class-based `BaseChecker`**(非函式式),
  方法 `check()` / `put(flag_id, flag, vuln)` / `get(flag_id, flag, vuln)`。
- 退出碼:OK=101、CORRUPT=102、MUMBLE=103、DOWN=104、ERROR=110。
- `checker_type: pfr` —— put 的 `public` 即攻擊方可見的 attack_data。
- 可重現性:put / get 收到同一個 `flag_id`,checker 由 flag_id **決定性導出帳號**
  (notes/filelocker 用 sha256;vault 用 README §2 的 FNV-1a slot/token 方案),
  使 get 能用同帳號合法取回 flag 比對,毋須跨進程保存狀態。

---

## 1. 取得 ForcAD 並放入 checker(對齊 CTF_SPEC §2.G)

```bash
# 1) 取得 ForcAD(計分框架)
git clone https://github.com/pomo-mondreganto/ForcAD.git
cd ForcAD

# 2) 把本目錄的 checker 放進 ForcAD 的 checkers/ 下,維持 <service>/checker.py 結構
mkdir -p checkers/notes checkers/filelocker checkers/vault
cp /path/to/gameserver/checkers/notes/checker.py       checkers/notes/checker.py
cp /path/to/gameserver/checkers/filelocker/checker.py  checkers/filelocker/checker.py
cp /path/to/gameserver/checkers/vault/checker.py       checkers/vault/checker.py

# 3) 確認 checker 可被 ForcAD 執行(其他使用者可讀可執行)
chmod o+rx checkers/notes/checker.py checkers/filelocker/checker.py checkers/vault/checker.py

# 4) checker 執行環境依賴(ForcAD 的 checker 容器/環境內安裝)
pip install -r /path/to/gameserver/checkers/requirements.txt
```

> config.yml 內 task 的 `checker` 欄位用相對路徑 `<service>/checker.py`,
> 對應 ForcAD `checkers/<service>/checker.py`。

---

## 2. 設定 config.yml

```bash
cp /path/to/gameserver/config.yml.example config.yml
# 編輯 config.yml:
#   - game.start_time 改成實際開賽時刻(timezone 已設 Asia/Taipei)
#   - teams 的 ip / name 已依 topology.yml 填(defense 10.80.1.1、attack-1 10.80.2.1)
#   - round_time=60、flag_lifetime=5 對齊 topology.yml forcad
```

config 重點(對齊契約):

- `game`:`mode: classic`、`round_time: 60`、`flag_lifetime: 5`、
  `default_score: 2500`、`game_hardness: 3000.0`、`inflation: true`、`timezone: Asia/Taipei`。
- `tasks`:notes / filelocker / vault 三筆,每筆 `checker_type: pfr`、
  `gets/puts/places: 1`、`checker_timeout: 15`、`checker: <service>/checker.py`。
- `teams`:`defense`(highlighted)、`attack-1`,IP 取自 topology.yml。

---

## 3. setup / start(ForcAD 標準流程)

```bash
# 初始化(讀 config.yml,建 DB、產生 team 提交 token 等)
./control.py setup

# 啟動整個計分系統(scoreboard、checker 排程、flag 接收)
./control.py start

# 印出各 team 的 flag 提交 token(攻擊方提交 flag 用;不放進 repo)
./control.py print_tokens
```

- scoreboard 預設埠見 topology.yml(`gameserver.scoreboard_port: 8080`)。
- flag 提交埠以 ForcAD config 為準(topology.yml 註記預期 `31337`)。

---

## 4. 本機驗證 checker(部署前)

```bash
# 建 venv、裝依賴
python3 -m venv .venv && . .venv/bin/activate
pip install -r checkers/requirements.txt

# 暫時起對應漏洞服務(見各 services/<svc> 的 README)後,對 checker 跑三動作:
#   check <host> / put <host> <flag_id> <flag> <vuln> / get <host> <flag_id> <flag> <vuln>
./checkers/notes/checker.py      check 127.0.0.1
./checkers/notes/checker.py      put   127.0.0.1 fid001 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=' 1   # stdout 印出 public(note_id)
./checkers/notes/checker.py      get   127.0.0.1 fid001 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=' 1

./checkers/filelocker/checker.py put   127.0.0.1 fid002 'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=' 1   # public 為 {"user","name"} JSON
./checkers/vault/checker.py      put   127.0.0.1 fid003 'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC=' 1   # public 為 my_slot(int)
```

判讀:OK 的退出碼為 **101**;flag 不符回 **102(CORRUPT)**;服務壞回 103/104。
put 的 stdout 第一行即 `public`(attack_data)。
