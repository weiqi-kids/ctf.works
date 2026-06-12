# astro — FORGE ⚒ 攻防工坊 採用導向靜態網站

在 AI 攻擊下煉成的防禦配方展示站。靜態輸出（`output: 'static'`），部署 GitHub Pages。
網站**只讀** `../data`（mock 資料）、`../schemas`（資料形狀）、`../CONTRACTS.md`（資料契約），不改它們。

## 指令

```sh
npm install      # 安裝依賴（含 astro + 五個 d3 子模組）
npm run build    # 產靜態站到 ./dist/
npm run dev      # 開發伺服器；因 base=/ctf.works，首頁在 http://localhost:4321/ctf.works/
```

## 部署網域切換（一行）

`astro.config.mjs` 頂部把 `SITE` / `BASE` 抽成常數：

- 現在：`SITE='https://weiqi-kids.github.io'`、`BASE='/ctf.works'`
- 之後（自訂網域就緒）：`SITE='https://ctf.works'`、`BASE='/'` + 加 `public/CNAME`

## 六條路由

| 路由 | 內容 |
|---|---|
| `/` | 首頁：prompt 摘要 + 3 步套用 + 模型切換 + CTA + 工坊主迴圈（mermaid 拓樸） |
| `/recipe/` | 主角：依模型分軌、鍛造軌跡曲線（d3）、PROMPT/playbook + diff、取得/運行、playbook 攻法清單 |
| `/runs/` | 攻防歷史列表，依模型/版本/類型篩 |
| `/runs/[run_id]/` | 攻防回放（d3 完整播放器：棋盤 + sparkline + 播放控制 + 版本邊界 + 事件） |
| `/evidence/` | 信任證據：守住率、SLA over rounds、不補基線對照、可攜性 |
| `/attack/` | 攻擊情報（次要）：模型×方法榜單 + 攻法時間軸 |

## 視覺化分工

- **mermaid**（client-side，CDN ESM）：靜態結構圖（首頁工坊主迴圈拓樸）。
- **d3.js**（client island，只 import `d3-scale` / `d3-selection` / `d3-transition` / `d3-shape` / `d3-array`）：
  - `ReplayPlayer.astro` — 回放播放器（最重元件）
  - `TrajectoryCurve.astro` — 鍛造軌跡曲線（每點可跳回放）
  - `SlaChart.astro` — SLA over rounds

## 資料載入

`src/lib/data.ts` 用 `import.meta.glob`（相對路徑 `../../../data`）在 build 時固化 JSON 與 PROMPT/playbook（`?raw`）。
trajectory 各版「跳回放」連結**僅當 `data/runs/<run_id>.json` 存在時顯示**（靜態站不保證每場都匯出）。

## 美學

工業鍛造 / 終端機 brutalist：炭黑底 + 熔融餘燼橙（forge heat）+ 戰術綠/警示紅；
JetBrains Mono（鍛造金屬感）+ Sora（內文）。tokens 見 `src/styles/global.css`。
