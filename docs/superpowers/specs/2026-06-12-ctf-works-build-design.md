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
- `astro/` — 六頁靜態網站(讀 mock 資料)
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
| astro | 六頁網站 + astro.config | 站點地圖 + data mock |

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

## 6. astro 站點地圖(Phase 0 凍結)

| 路由 | 頁面 | 讀哪些資料 | 性質 |
|---|---|---|---|
| `/` | 首頁/工坊理念(§1.1/1.3/1.4,拓樸 mermaid) | 無 | 靜態 |
| `/recipe/` | ★防禦配方:版本列表 + 鍛造軌跡曲線 | `data/recipe/trajectory.json` | 資料 |
| `/recipe/[version]/` | 單版配方:PROMPT/playbook + 與上版 diff | `data/recipe/v*/` | 資料 |
| `/defense/` | 防禦成效:守住率、SLA、修補成效、自殘、不補基線對照 | `data/runs/*.json` | 資料 |
| `/attack/` | ★攻擊情報榜:模型×方法榜單 + 攻法時間軸 | `data/attack_intel.json` + runs | 資料 |
| `/process/` | 流程說明:flag 生命週期/攻防 §1.5(mermaid sequence) | 無 | 靜態 |
| `/portability/` | 可攜性:配方搬乾淨主機仍守得住的驗證 | `data/runs/*`(portability 場次) | 資料 |

- 頂部 nav 橫跨六頁;`/recipe/`、`/attack/` 為兩主角(對應輸出 A/B)。
- Content collections:`recipe`(md)、`runs`(JSON)、`attackIntel`(JSON)、`trajectory`(JSON)。
- 建站用 `frontend-design` skill,美術風格屆時定。

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
