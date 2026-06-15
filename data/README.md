# data — 網站靜態資料（資料契約）

Astro 網站**只讀這個資料夾**，不直連計分主機。由匯出腳本離線產生（讀 ForcAD API／PostgreSQL ＋ agent 日誌 → 產檔 → commit → rebuild）。

**完整輸出規格見 [docs/DATA_CONTRACT.md](../docs/DATA_CONTRACT.md)** — 欄位定義、隱含契約、範例與驗證方式都在那裡。機器可驗的型別在 [`schemas/`](../schemas/)。

```
data/
├── recipe/
│   ├── <model>/<version>/PROMPT.md  playbook.md   # 各版配方（成品 A）
│   └── trajectory.json                            # 鍛造軌跡：版本→成效→diff 摘要
├── runs/<run_id>.json                             # 每場：防禦成效 ＋ 逐 round 時間軸
└── attack_intel.json                              # 全站攻法清單 ／ 模型榜（輸出 B）
```
