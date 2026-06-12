# defense-recipe — 可複製的防禦配方(成品 A)

把這整個資料夾搬到任一 vulnbox,設好前置、跑 `run.sh`,這台機器就有了**自動防禦力**:
一個非互動 AI agent 依 `PROMPT.md` 每輪巡檢三個漏洞服務、出最小 diff 堵漏洞、用 `self_verify`
確認「洞堵住且 SLA 沒壞」(否則回滾),並把學到的東西累積進 `playbook.md`。

> 純防守。只堵漏洞路徑、保留所有合法功能、出最小 diff、改完必跑 self_verify。
> 不攻擊、不掃描別人、不碰計分主機、不製造流量。

---

## 1. 資料夾內容

| 檔案 | 作用 |
|---|---|
| `PROMPT.md` | 防禦守護的系統提示(agent 的「腦」)。純防守鐵律 + 每輪工作流程 + 三洞堵法要點。 |
| `run.sh` | 固定運行流程:`while true` 輪詢迴圈,每輪起一個非互動 agent 巡檢+修補,`sleep` 一個 round。含 systemd 常駐說明。 |
| `self_verify/` | 每洞一支驗證腳本 + `run_all.sh`。判定「exploit 失敗(洞堵住)+ 合法功能通過(SLA 沒壞)」,兩條都過才算數。 |
| `playbook.md` | 配方的記憶:三個已知洞(IDOR / path traversal / OOB read)+ 各自安全堵法步驟 + 每輪巡檢日誌。 |
| `README.md` | 本檔。 |

`self_verify/` 內:
- `notes_verify.sh` — notes(IDOR)
- `filelocker_verify.sh` — filelocker(path traversal)
- `vault_verify.sh` — vault(OOB read)
- `run_all.sh` — 一次跑完三支,任一 FAIL 即整體非零退出

---

## 2. 如何取得(clone)

配方隨主 repo 出貨。取得整個 repo 後,本資料夾位於 `defense/defense-recipe/`:

```bash
git clone <ctf.works repo>
cd ctf.works/defense/defense-recipe
```

部署到 vulnbox 時,可只把 `defense-recipe/` 連同它要守的 `services/` 一起搬到固定路徑
(如 `/opt/`)。`self_verify` 用相對路徑 `../../../services/<svc>` 定位服務碼與 exploit,
請保持 `defense-recipe/` 與 `services/` 的相對位置(同在 repo 根下)。

---

## 3. 前置(prerequisites)

在 vulnbox 上需要:

- **agent runner**:`claude` CLI(非互動模式)或等價的模型 runner。
  `run.sh` 用 `AGENT_CMD`(預設 `claude`)起 agent,把 `PROMPT.md` 當系統提示。
  換別的 runner 改 `AGENT_CMD` 並調整 `run.sh` 內的旗標(`-p` / `--append-system-prompt` 視 CLI 而定)。
- **Python 3** + `requests`(notes 的 checker/exploit 用;filelocker/vault 的 exploit 用標準庫)。
- **curl**、**jq**(self_verify 的合法功能測試用)。
- **gcc / make**(vault 是 C daemon,修補後需重新編譯)。

快速自檢:

```bash
command -v claude python3 curl jq gcc make
python3 -c 'import requests; print("requests", requests.__version__)'
```

---

## 4. 怎麼跑 run.sh

最簡:

```bash
./run.sh
```

它會:
1. 進入 `while true` 迴圈;
2. 每輪起一個非互動 agent(依 `PROMPT.md`)對 notes/filelocker/vault 巡檢+修補,過程寫到 `logs/round_N.log`;
3. `sleep $ROUND_INTERVAL`(預設 60s,對齊 `topology.yml` 的 `round_time`)後進下一輪。

可用環境變數調整:

| 變數 | 預設 | 說明 |
|---|---|---|
| `ROUND_INTERVAL` | `60` | 每輪間隔秒數,部署時對齊計分機 `round_time`。 |
| `AGENT_CMD` | `claude` | 非互動 agent CLI。 |
| `DRY_RUN` | `0` | `1`=不起 agent,每輪只跑 `self_verify/run_all.sh`(驗迴圈骨架 / 純巡檢)。 |
| `MAX_ROUNDS` | `0` | `0`=無限;`>0` 跑指定輪數後停(測試用)。 |
| `LOG_DIR` | `./logs` | 每輪日誌目錄。 |

例:乾跑 2 輪(不起 agent,只巡檢),確認迴圈骨架與 self_verify 能跑:

```bash
DRY_RUN=1 MAX_ROUNDS=2 ROUND_INTERVAL=5 ./run.sh
```

**常駐**:正式部署用 systemd(開機自啟、崩潰自重啟),設定範本見 `run.sh` 末尾註解;
臨時可用 `tmux new -s defense './run.sh'`。

---

## 5. self_verify 怎麼運作

每支 `<svc>_verify.sh` 對一個服務做兩條判定,**兩條都過才回 0**:

1. **合法功能(模擬 checker / SLA)**:用服務的**合法 API** register/login → 建立資料 → 讀回自己的資料,
   驗證成功且內容正確。這保證補丁沒有誤傷合法路徑。
2. **exploit 應失敗(洞已堵)**:跑該服務對應的 `services/<svc>/exploit.py`(IDOR / traversal / OOB read),
   期望**偷不到 flag**。另含變體測試(filelocker 測 `%2e%2e` URL 編碼繞過;vault 測負數 / 超大 idx)。

退出碼語意:`0` = 兩條都過(洞堵住且 SLA 正常);非 `0` = 有 FAIL。
防禦 agent 據此決定**接受補丁**還是**回滾**:只要合法功能那條 FAIL,寧可回滾、這輪不交該改動。

手動跑(需先起對應服務):

```bash
# 各支可單獨跑,參數 [HOST] [PORT]
self_verify/notes_verify.sh      127.0.0.1 8080
self_verify/filelocker_verify.sh 127.0.0.1 9090
self_verify/vault_verify.sh      127.0.0.1 10000

# 一次跑完三支
self_verify/run_all.sh
```

> 重要語意:在**洞還沒補**的初始 vulnbox 上跑,exploit 那條會成功偷到 flag,
> 因此 verify **判 FAIL(非零退出)**——這正是「偵測到洞還開著」的訊號,告訴 agent 本輪要修補。
> 補好之後再跑,exploit 失敗 + 合法功能通過,才會 PASS。

---

## 6. 會碰你主機什麼 / 隔離建議

**會碰**:
- **讀寫 `services/<svc>/` 內的服務原始碼**(agent 修補洞;notes/filelocker 是 Python、vault 是 C)。
- vault 修補後**重新編譯**(`make`)並重啟該 daemon。
- 對 **`127.0.0.1` 本機服務埠**(8080/9090/10000)發合法 API 與 exploit 請求做驗證。
- 在 `defense-recipe/` 內寫 `logs/` 與 append `playbook.md`。

**不會碰**:不連別人主機、不掃描、不送大量流量、不改 checker / ForcAD / 共用契約檔。

**隔離建議**:
- 在**隔離網段、無對外 egress** 的 vulnbox / VM 內跑(見 `CTF_SPEC.md §1.4`、`topology.yml`)。
- 用**低權限使用者**跑 `run.sh`,並限制其只能改 `services/` 目錄;agent runner 的檔案/網路權限收到最小。
- 服務本身建議跑在容器或低權限使用者下(各 `services/<svc>/Dockerfile` 已備)。
- 先用 `DRY_RUN=1` 乾跑確認骨架與 self_verify,再開真正的 agent 修補迴圈。

---

## 7. 本輪交付邊界(誠實標註)

- **可在本機驗**:`self_verify` 能正確偵測「洞存在(exploit 成功 → FAIL)」與「合法功能正常」;
  `run.sh` 迴圈骨架可 `DRY_RUN` 乾跑。
- **留部署期**:真實多 round 攻防迴圈(agent 每輪自動修補 + 攻擊 harness 跨 round 重打 + ForcAD 計分 +
  黃金映像/VM)需 ForcAD + VM 環境才完整跑。本輪做到「結構正確 + self_verify 可驗」。
