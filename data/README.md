# data — 網站靜態資料(資料契約)

Astro 網站**只讀這個資料夾**,不直連計分主機。由匯出腳本離線產生(讀 ForcAD API/PostgreSQL + agent 日誌 → 產檔 → commit → rebuild)。契約定義見 [CTF_SPEC.md §3.2](../CTF_SPEC.md)。

```
data/
├── recipe/
│   ├── v1/PROMPT.md  v1/playbook.md ...   # 各版配方(成品 A)
│   └── trajectory.json                    # 鍛造軌跡:版本→成效→diff 摘要
├── runs/<run_id>.json                     # 每場:防禦成效 + 攻擊情報
└── attack_intel.json                      # 攻法清單 / 模型×方法 榜單(輸出 B)
```
