# attack/harness — 機械重打骨架

把攻擊方 agent(LLM)找出的**可動 exploit**,每 round 自動拉 attack_data、
重打防禦主機、提交 flag、記情報。**LLM 思考與機械提交分層**:harness 不思考,
只執行;找洞與繞補丁是 agent(`prompts/attacker.md`)的事。

## 檔案

| 檔 | 作用 |
|---|---|
| `submit_loop.py` | 主迴圈:拉 attack_data → 跑 `services/<svc>/exploit.py` → 抽 flag → 提交 → 記情報 |
| `intel_log.py` | 攻擊情報記錄:每次得手寫一筆 `{model,service,method,round,flag}` 到 JSONL |
| `fake_receiver.py` | 離線示範用假 flag 接收埠(非 dry-run 又沒有真 gameserver 時用) |
| `mock/attack_data.*.json` | 離線 mock attack_data,模擬計分主機回傳 |

`submit_loop.py` 透過 **subprocess** 呼叫 `../../services/<svc>/exploit.py`,
不修改 services/。各 exploit 介面:

- notes:`exploit.py <host> <port> <note_id>`,attack_data = `note_id`(int)
- filelocker:`exploit.py <host> <victim_user> <victim_name> --port <port>`,attack_data = `{"user","name"}`
- vault:`exploit.py <host> <port> <victim_slot>`,attack_data = `slot`(int)

## 一輪流程

1. **拉 attack_data** — 線上 `GET {gameserver}/api/client/attack_data`(帶 token);
   離線讀 `--mock` JSON。攤平成 targets:`{service, attack_data, round, victim_team}`。
2. **跑 exploit** — 依服務把 attack_data 轉成該 exploit 的 CLI,subprocess 執行。
3. **抽 flag** — 用 `[A-Z0-9]{31}=` regex 從 exploit stdout 抽 flag,格式不對就跳過。
4. **提交 flag** — `--dry-run` 只記「將提交」;否則 PUT 到 flag 接收埠(帶 token)。
5. **記情報** — `intel_log.log_hit(...)` append 一行到 intel JSONL。

## 參數(submit_loop.py)

| 參數 | 預設 | 說明 |
|---|---|---|
| `--model` | `claude-opus-4-8` | 攻擊方模型名(記入 intel) |
| `--defense-host` | `127.0.0.1` | 防禦主機 IP(部署期填 topology.yml 的 defense ip) |
| `--notes-port` / `--filelocker-port` / `--vault-port` | 8080 / 9090 / 10000 | 各服務埠 |
| `--gameserver-host` | `10.80.0.2` | 計分主機 IP |
| `--gameserver-port` | 8080 | 計分主機 attack_data API 埠 |
| `--flag-submit-port` | 31337 | flag 接收埠 |
| `--token` | env `CTF_TEAM_TOKEN` | team 提交 token |
| `--mock` | 無 | 離線:讀本地 mock attack_data JSON(給了就走離線,不連 gameserver) |
| `--round` | 1 | 起始 round 編號 |
| `--rounds` | 1 | 連跑幾輪 |
| `--round-sleep` | 0 | 每輪間隔秒(節流,守紅線「不洪水打點」) |
| `--dry-run` | off | 不真提交,只記「將提交」(離線示範用) |
| `--intel` | `attack/intel/hits.jsonl` | intel JSONL 輸出路徑 |
| `--python` | 同本 harness | 跑 exploit 用的 python(離線可指向裝了 requests 的 venv) |
| `--exploit-timeout` | 30 | 單支 exploit 逾時秒 |

## 離線 mock 測試(實測可跑一輪)

需求:跑 exploit 的 python 要有 `requests`(notes/filelocker exploit 用到);
跑 notes 服務要有 `Flask`。本 repo 的 `.venv` 已備齊。

```bash
# 1) 起 notes 服務(背景)
cd services/notes && ../../.venv/bin/python app.py &

# 2) 用合法 API 種一個含 flag 的 note(flag 格式 [A-Z0-9]{31}=,共 32 字元)
FLAG="ABCDEFGHIJKLMNOPQRSTUVWXYZ01234="
curl -s -c /tmp/c.txt -X POST localhost:8080/register -H 'Content-Type: application/json' -d '{"u":"victim","p":"vpass"}'
curl -s -c /tmp/c.txt -X POST localhost:8080/login    -H 'Content-Type: application/json' -d '{"u":"victim","p":"vpass"}'
curl -s -b /tmp/c.txt -X POST localhost:8080/note     -H 'Content-Type: application/json' -d "{\"body\":\"$FLAG\"}"
# 回傳的 note_id 寫進 mock/attack_data.notes.json 的 attack_data

# 3) 跑一輪 harness(dry-run,不真提交)
cd ../..
.venv/bin/python attack/harness/submit_loop.py \
  --model claude-opus-4-8 --defense-host 127.0.0.1 --notes-port 8080 \
  --mock attack/harness/mock/attack_data.notes.json \
  --round 1 --dry-run --intel attack/intel/hits.jsonl \
  --python "$PWD/.venv/bin/python"

# 4) 看情報
cat attack/intel/hits.jsonl

# 5) 關服務
pkill -f services/notes/app.py
```

### 想跑非 dry-run(用假接收埠)

```bash
.venv/bin/python attack/harness/fake_receiver.py --port 31337 &   # 假 flag 接收埠
.venv/bin/python attack/harness/submit_loop.py ... \
  --gameserver-host 127.0.0.1 --flag-submit-port 31337            # 去掉 --dry-run
```

## mock 結構

```json
{
  "round": 1,
  "targets": [
    {"service": "notes", "attack_data": 2, "round": 1, "victim_team": "defense-mock"}
  ]
}
```

`attack_data` 依服務:notes/vault 是 int(note_id / slot),filelocker 是
`{"user","name"}`。多服務就在 `targets[]` 多放幾筆。

## 部署期(留待)

- 線上 attack_data:`_parse_forcad_attack_data` 是寬鬆攤平,接真 gameserver 時依
  當場 ForcAD 回傳 schema 校正(已標 TODO)。
- flag 提交協定(HTTP PUT vs TCP):依 ForcAD 部署實際接收埠協定調整 `submit_flag`。
- 真實多 round + 真 LLM 找新洞 + 繞補丁:部署期由常駐 agent 驅動。

## 紅線(harness 也受約束)

- 只打防禦主機三服務,**不碰 gameserver / 基礎設施**。
- 用 `--round-sleep` 節流,**不洪水打點、不 DoS**。
