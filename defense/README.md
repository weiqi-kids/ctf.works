# defense — ROLE D 防禦方(被鍛造的刀)

防禦配方 `defense-recipe/` 的開發與版本沉澱。建置 playbook 見 [CTF_SPEC.md §2.D](../CTF_SPEC.md),配方結構見 §1.8。

預計內容:
- `defense-recipe/PROMPT.md` — 守護 prompt(純防守)
- `defense-recipe/run.sh` — 固定運行流程(輪詢迴圈)
- `defense-recipe/self_verify/` — before/after exploit 檢查 + 合法功能測試 + 回滾
- `defense-recipe/playbook.md` — 累積的防禦知識

可複製性是硬指標:整個 `defense-recipe/` 搬到乾淨 vulnbox 跑 `run.sh` 仍守得住,才算配方成形。
