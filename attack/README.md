# attack — ROLE A 攻擊方(放野的磨刀石)

攻擊方 prompt 與 harness。對防禦主機三服務持續施壓、偷 flag 得分,逼出更強的防禦配方。
建置 playbook 見 [CTF_SPEC.md §2.A](../CTF_SPEC.md);exploit 路徑見 [CONTRACTS.md §2.*](../CONTRACTS.md)。

## 結構

```
attack/
├── prompts/attacker.md       攻擊方系統 prompt(放野精神 + 唯一紅線 + 情報記錄)
├── harness/
│   ├── submit_loop.py        機械重打:拉 attack_data → 跑 exploit → 提交 → 記情報
│   ├── intel_log.py          攻擊情報記錄(輸出 B):{model,service,method,round,flag} → JSONL
│   ├── fake_receiver.py      離線示範用假 flag 接收埠
│   ├── mock/                 離線 mock attack_data
│   └── README.md             怎麼跑 harness、離線測試、各參數
└── intel/hits.jsonl          得手事件流(JSONL,彙整成 data/attack_intel.json)
```

三支可動 exploit PoC 在 `../services/<svc>/exploit.py`(notes / filelocker / vault),
兼作 Phase 2 驗證工具;harness 直接 subprocess 呼叫它們。

## 怎麼運行

攻擊方 = **常駐 agent 找洞** + **harness 機械重打**,兩層分工:

1. **常駐 agent(LLM,腦)** — 載入 `prompts/attacker.md`。放野:用任何方法找出並利用防禦主機
   服務漏洞、偷 flag 得分。鼓勵嘗試新洞、串接、繞過防禦方剛打的補丁。找到新可動 exploit
   後沉澱成 `services/<svc>/exploit.py` 介面相容的腳本,交棒給 harness。

2. **harness(機械手臂)** — `harness/submit_loop.py` 每 round 自動:
   拉 attack_data(`/api/client/attack_data`,帶 token)→ 對防禦主機跑已知 exploit →
   抽 flag([A-Z0-9]{31}=)→ 提交到 flag 接收埠(帶 token)→ 記情報。
   參數與離線 mock 測試見 [`harness/README.md`](harness/README.md)。

離線一輪示範(實測可跑,見 harness/README.md):起 notes 服務 + 種一個 flag →
`submit_loop --mock ... --dry-run` → 呼叫 `services/notes/exploit.py` 偷到 flag →
`intel/hits.jsonl` 寫出一筆。

## 紅線(唯一,嚴禁跨越)

1. **不碰計分主機 / 基礎設施** —— 只攻擊防禦主機三服務,gameserver / 閘道 / checker 一律不動。
2. **不 DoS、不洪水打點** —— 合理節流(`--round-sleep`),目標是偷 flag 不是打垮服務。
3. **不打範圍外主機** —— 只在隔離網段、只對 topology.yml 的 defense 主機動手。

越線即失格。磨刀石的價值在持續、聰明、有節制的壓力。

## 攻擊情報記錄(輸出 B)

每次得手記一筆 `{model, service, method, round, flag}` 到 `intel/hits.jsonl`(JSONL 事件流),
由 harness 自動寫入(`intel_log.log_hit`),亦可手動 `python3 harness/intel_log.py --model ... `。
這些事件彙整成 `data/attack_intel.json`(schema:`schemas/attack_intel.schema.json`)的
模型×方法榜單與攻法時間軸。**用新方法得手要記新的 method 名**——這是情報的價值。
