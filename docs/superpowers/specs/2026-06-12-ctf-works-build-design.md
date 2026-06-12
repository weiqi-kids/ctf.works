# CTF 攻防工坊 — 製品建置設計 (v1)

> 日期:2026-06-12
> 對應規格:[`CTF_SPEC.md`](../../../CTF_SPEC.md)
> 狀態:設計已核可,待轉 writing-plans

## 1. 目的與本輪範圍

把工坊的**全部製品/程式碼/內容**在本機建好並驗證,網站先用符合資料契約的 mock 資料。**真實多 round 攻防迴圈**(防禦 run.sh 輪詢、攻擊 harness 重打、ForcAD 計分、黃金映像/VM)屬部署期,不在本輪。

本輪交付:
- `services/` — notes / filelocker / vault 三個漏洞服務(含 Dockerfile + 可動 exploit)
- `gameserver/` — 三個 checker + `config.yml.example`
- `defense/defense-recipe/` — PROMPT.md / run.sh / self_verify / playbook.md(種子)
- `attack/` — 攻擊 prompt + harness 骨架 + 三支 exploit PoC
- `astro/` — 採用導向靜態網站(讀 mock 資料):首頁直給 prompt+套用步驟、配方依模型分軌、攻防歷史 + 完整回放播放器
- `data/` — 符合 §3.2 契約的 mock 資料
- 根目錄 `docker-compose.dev.yml` + 整合驗證報告

## 2. 建置策略:契約優先,再扇出(三段式)

```
Phase 0 (序列) → Phase 1 (平行 7 agents) → Phase 2 (序列)
```

六個資料夾靠兩組契約綁定:**服務 API 契約**(service/checker/exploit 三方一致)、**資料契約**(astro/匯出腳本一致)。先凍結契約再平行,避免返工。

### Phase 0 — 凍結契約(序列,由主導者親手做)

產出 `CONTRACTS.md`,內容:
1. 三個服務的 wire API(見 §3)。
2. **fetch ForcAD wiki/repo 核對**:checklib `Status`/`cquit` 名稱、三動作 exit code、`config.yml` 欄位格式。實作 checker 前必須完成。
3. astro 站點地圖(見 §6)。
4. 在 `data/` 種一組符合 §3.2 的 mock 資料。

### Phase 1 — 平行扇出(7 agents,各負責一資料夾/服務)

| agent | 交付 | 依賴(凍結契約) |
|---|---|---|
| notes 服務 | Flask app + Dockerfile + exploit.py + README | 服務 API 契約 |
| filelocker 服務 | app + Dockerfile + exploit + README | 服務 API 契約 |
| vault 服務 | C daemon + Makefile/Dockerfile + exploit + README | 服務 API 契約 |
| gameserver | checkers/{notes,filelocker,vault}/checker.py + requirements.txt + config.yml.example + README | 服務 API + ForcAD checklib 事實 |
| defense-recipe | PROMPT.md + run.sh + self_verify/ + playbook.md(種子) | 三洞的安全堵法 |
| attack | prompts/ + harness/ + 三支 exploit PoC + README | 三洞的 exploit 路徑 |
| astro | 採用導向網站(6 路由,含回放播放器) + astro.config | 站點地圖 + data mock(含回放資料) |

### Phase 2 — 整合驗證(序列)

`docker-compose.dev.yml` 拉起三服務(不含 ForcAD)→ 每個 checker 跑 check/put/get 期望 OK → 每支 exploit 期望偷到 flag → `npm run build` astro 期望成功 → 產驗證報告。

## 3. 服務與漏洞設計(每服務單層洞,先端到端跑通)

三洞皆為**服務內串接**(flag 正常種在該服務),符合 ForcAD 計分相容性;跨服務串接列第二階段。

| 服務 | 技術 | 合法 API | 漏洞 | exploit 路徑 |
|---|---|---|---|---|
| notes | Flask :8080 | register / login / `POST /note` / `GET /note?id=` / `GET /notes` | `GET /note?id=` 不檢查擁有者 = **IDOR** | attack_data=note_id → GET 別人的 note 讀 flag |
| filelocker | Python :9090 | register / login / `PUT /file` / `GET /file?name=` | `GET /file?name=` 不過濾路徑 = **path traversal** | attack_data=victim 帳號+檔名 → `../` 讀他人檔 |
| vault | C daemon :10000 | line TCP:`REGISTER` / `AUTH` / `SET <secret>` / `GET <idx>` | secrets 存全域陣列、`GET <idx>` 無邊界檢查 = **OOB read** | attack_data=victim slot id → 越界讀他人 secret |

**vault 選 OOB read 而非 stack smash 的理由**:自動化攻防迴圈要每 round 可重複跑;OOB read 確定性高(無 ASLR/leak 體操)、exploit 穩定、補丁單純(加邊界檢查),仍屬「記憶體破壞讀他人 secret」。更硬的 heap/stack 變體依 SPEC §1.6 之後再疊。

**對應的安全堵法(寫進 playbook 種子)**:IDOR→加擁有者檢查;path traversal→正規化並限制在使用者目錄;OOB→加邊界檢查。皆可在不破壞合法 API 下修補(SPEC §1.6 服務不變量)。

## 4. gameserver(checkers + config)

- 三個 checker,checklib 相容,全部 `checker_type: pfr`,各 `chmod o+rx`。
- 實作 CHECK/PUT/GET,正確回報 Status(DOWN/MUMBLE/CORRUPT/OK)。vault checker 走 TCP。
- `config.yml.example`:teams/tasks 依 `topology.yml`,`round_time`/`flag_lifetime` 對齊。
- checklib API / exit code / config 格式以 Phase 0 fetch 的 ForcAD 官方文件為準。

## 5. defense / attack(本機只驗結構,真實迴圈留部署期)

**defense-recipe**(成品 A):
- PROMPT.md 純防守(只堵漏洞路徑、保留合法功能、最小 diff、改完必跑 self_verify)。
- run.sh 輪詢迴圈(SPEC §2.D 範本),systemd/tmux 常駐。
- self_verify/ 每洞一支:exploit 確認堵住 + 合法功能測試確認 SLA;兩條過才算,否則回滾。
- playbook.md **種子**:三個已知洞 + 安全堵法,當 v1 記憶起點。

**attack**(磨刀石):
- prompts/ 放野精神 + 唯一紅線(不碰計分主機、不 DoS、不洪水)。
- harness/ 機械重打骨架:拉 attack_data → 跑已知 exploit → 提交 flag。
- 三支可動 exploit PoC,兼作 Phase 2 驗證工具。
- 攻擊情報記錄:每次得手記「模型/方法/服務/round」→ 輸出 B。

## 6. astro 站點地圖(採用導向 + 歷史 + 回放,Phase 0 凍結)

**定位修正**:SPEC §3.1 把網站定為「介紹/展示」。本設計改為**採用導向**——主要工作是**讓人取得並運行防禦配方(prompt+playbook)**,成效/可攜性/攻擊情報降為支撐「值得採用」的信任證據。對外可複製的核心是 `PROMPT.md`(防禦 agent 的腦)+ `playbook.md`(攻法→安全堵法的記憶)。

**統一敘事**:鍛造軌跡(版本史)↔ 每版背後產生它的 run ↔ 那場 run 的完整回放。版本史就是歷史;點任一版進它的 run 看回放。

**模型為第一級維度**:防禦方/攻擊方可為不同 AI(Claude / OpenAI…)與不同模型。配方**依模型分軌**,每模型有自己的版本軌跡;訪客可挑自己用的模型拿對應 prompt。

採用脊椎:**看懂 → 信任(證據)→ 取得 → 運行**。六條路由:

| 路由 | 頁面 | 讀哪些資料 | 性質 |
|---|---|---|---|
| `/` | 首頁:理念一句話 + **直接秀 prompt 摘要 + 3 步套用到你主機** + 模型切換(拿你模型的配方)+ CTA。§1.1/1.3/1.4 拓樸 mermaid | `data/recipe/<model>/` 最新版 | 資料 |
| `/recipe/`(主角) | **依模型分軌**:完整 PROMPT/playbook、版本+鍛造軌跡曲線、**如何取得**(clone `defense-recipe/`)、**如何運行**(前置/run.sh/會碰你主機什麼/隔離)、**已會擋什麼**(playbook 攻法清單);可展開單版 + 與上版 diff;每版連到產生它的 run | `data/recipe/<model>/v*/`、`trajectory.json` | 資料 |
| `/runs/` | 攻防歷史:所有場次列表,依**模型 / 配方版本 / 日期**篩 | `data/runs/*.json`(索引) | 資料 |
| `/runs/[run_id]/` | **攻防回放(完整播放器)**:可拖曳 round 的播放器,看棋盤狀態(team×服務×狀態×偷/守)逐 round 演進 + 版本邊界的 prompt/playbook diff + 攻擊方得手方法/防禦方補洞事件 | `data/runs/<run_id>.json`(含 timeseries 事件) | 資料 |
| `/evidence/` | 信任證據(合併 defense+portability):守住率、SLA over rounds、修補成效、自殘、**不補基線對照**、搬乾淨主機仍守得住 | `data/runs/*.json` | 資料 |
| `/attack/` | 攻擊情報 B(次要):「捶打它的壓力來源」,模型×方法榜單 + 攻法時間軸 | `data/attack_intel.json` + runs | 資料 |

- 頂部 nav;`/recipe/` 唯一主角(成品 A);`/attack/`(輸出 B)明確次要。`/process/` 流程圖解併入 `/`/`/runs/` 視需要呈現。
- `/recipe/` 與 `/` 的「取得/運行」用可複製貼上程式碼區塊;playbook 攻法清單讓訪客知道「拿到手就有哪些戰力」。
- 回放播放器是網站最重的互動元件,client-side 渲染 timeseries;為 astro agent 的核心交付。
- Content collections:`recipe`(md,依模型)、`runs`(JSON)、`attackIntel`(JSON)、`trajectory`(JSON)。
- 建站用 `frontend-design` skill,美術風格屆時定。

### 6.1 資料契約擴充(Phase 0 凍結,擴充 SPEC §3.2)

為支撐模型維度、版本↔run 連結、完整回放,在 §3.2 基礎上擴充:

- **防禦方模型入帳**:`fingerprint.defender` 加 `model`(防禦方是哪個 AI/模型)。原本只有攻擊方記 model,此為破綻修補。
- **配方依模型分軌**:目錄改 `data/recipe/<model>/v*/PROMPT.md|playbook.md`;`trajectory.json` 每筆帶 `model`、`version`、`run_id`、`effectiveness`、`diff_summary`——版本史即鍛造軌跡,每版可追到產生它的 run。
- **timeseries 擴充為帶事件(回放燃料)**:每 round 除 `status`/`stolen`,加
  - `board`:該 round 各 (team, 服務) 的狀態快照(供播放器畫棋盤)。
  - `attack_events`:`{model, service, method, victim, round}`——誰用什麼方法偷哪個服務。
  - `defense_events`:`{service, action, round, version_bump?}`——補了哪個洞 / 版本切換點。
- **回放資料自洽**:mock 資料要造到播放器能完整播放(逐 round board + 事件 + 版本邊界 diff);Phase 0 種一場資料豐富的 run 當樣本。

> 注意:`board`/`attack_events`/`defense_events` 真實來源是 [FORCAD-SQL]+[AGENT-LOG] 合併,需 agent 端埋對應日誌(留部署期);本輪以 mock 滿足契約。

### 部署設定(可快速切換網域)

現用 GitHub Pages 專案路徑 `https://weiqi-kids.github.io/ctf.works/`;自訂網域 `ctf.works`(購買中)就緒後切換。`astro.config` 把 `site`/`base` 抽成可切換常數,切換只改一處 + 加 CNAME:
- 現在:`site: 'https://weiqi-kids.github.io'`,`base: '/ctf.works'`
- 之後:`site: 'https://ctf.works'`,`base: '/'`

## 7. 本機驗證天花板

- **可驗**:服務 `compose up`、checker 三動作 OK、exploit 偷得到 flag、astro `build` 成功。
- **不可驗(留部署期)**:真實多 round 迴圈、防禦 run.sh 自動巡檢修補、攻擊 harness 跨 round 重打、ForcAD 計分、黃金映像/VM。本輪這些只驗「結構正確、可 dry-run」。

## 8. 風險

- **vault(C pwn)** 最易出錯:OOB read 設計已盡量降風險,但 C + TCP + checker 一致性仍是最難的一塊,Phase 2 重點驗。
- **ForcAD 介面假設**:checklib/config 必須以官方文件為準,不可憑記憶(SPEC 強制)。Phase 0 未 fetch 核對前不得開 checker agent。
- **三方 client 漂移**:checker、exploit、self_verify 各自實作「與服務對話」,靠 Phase 0 凍結的精確契約防漂移。
- **回放播放器 + 事件資料**:完整播放器是 astro agent 最重的互動件;且 `board`/`attack_events`/`defense_events` 的真實來源(FORCAD-SQL+AGENT-LOG 合併)留部署期,本輪靠 mock。風險在 mock 契約若不夠周全,部署期接真實資料要返工——故 Phase 0 的 timeseries 事件 schema 要一次定到位。
