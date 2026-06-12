# AI 攻防工坊 (ctf.works)

放一個自由發揮的 AI 攻擊方當磨刀石,持續捶打 AI 防禦方;防禦方在真實壓力下反覆優化,最終產出一份**可複製到任何主機、立即增強防禦的配方**。計分引擎用 [ForcAD](https://github.com/pomo-mondreganto/ForcAD)。

完整規劃見 [CTF_SPEC.md](CTF_SPEC.md)。

## Repo 結構

| 資料夾 | 內容 |
|---|---|
| `astro/` | 公開介紹網站,發佈到 GitHub Pages |
| `gameserver/` | ROLE G 計分主機:ForcAD 設定 + checkers |
| `defense/` | ROLE D 防禦方:defense-recipe(prompt + 運行流程 + 自我驗證 + playbook) |
| `attack/` | ROLE A 攻擊方:prompt + harness |
| `services/` | 漏洞服務(notes / filelocker / vault),進黃金映像,D/A 共用 |
| `data/` | 離線匯出的靜態資料,網站只讀這裡 |
| `topology.yml` | 跨主機共用拓樸:IP、埠號、flag 格式 |

每個角色資料夾自包含——整個資料夾搬到目標主機即可部署。

## 本機運行

**公開網站(astro)**
```bash
cd astro
npm install
npm run dev      # 開 http://localhost:4321/ctf.works/(埠被占會自動往後)
npm run build    # 產靜態站到 astro/dist(GitHub Pages 用)
```
網站只讀 `data/` 的靜態資料(目前是 mock,符合 `schemas/` 契約)。

**三個漏洞服務(整合測試)**
```bash
docker compose -f docker-compose.dev.yml up --build   # notes:8080 filelocker:9090 vault:10000
```

**資料契約驗證**
```bash
python3 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/validate_data.py               # data/ mock 對 schemas/ 驗證
```

跨元件介面凍結在 [`CONTRACTS.md`](CONTRACTS.md);設計與計畫見 `docs/superpowers/`。

> ⚠️ 本 repo 的漏洞服務是**故意埋洞**的教學/鍛造用途,只在隔離網段運行,切勿部署到公開環境。
