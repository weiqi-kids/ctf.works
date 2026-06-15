<!-- 投稿攻防結果請照 CONTRIBUTING.md。一般 PR 把不適用的段落刪掉即可。 -->

## 這個 PR 做了什麼



## 攻防結果（若有投稿 data/runs）

- **run_id**：
- **來源（fingerprint.source）**：
- **防禦模型 / 配方版本**：
- **攻擊模型**：

## 檢查清單

- [ ] 本機跑過 `python tools/validate_data.py --strict`，**0 error**
- [ ] run_id 前 10 碼是合法日期、檔名與 run_id 一致
- [ ] 沒有改 `CONTRACTS.md` 或 `schemas/`（Phase 0 凍結契約）
- [ ] 若用了新模型／新服務，已一併更新 `astro/src/lib/data.ts` 對照（見 [CONTRIBUTING.md](../CONTRIBUTING.md) §6）
