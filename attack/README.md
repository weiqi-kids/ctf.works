# attack — ROLE A 攻擊方(放野的磨刀石)

攻擊方 prompt 與 harness。建置 playbook 見 [CTF_SPEC.md §2.A](../CTF_SPEC.md)。

預計內容:
- `prompts/` — 攻擊方 prompt(放野:任何方法找洞偷 flag,唯一紅線是不碰計分主機、不 DoS)
- `harness/` — 把已知 exploit 每 round 機械重打的提交層(LLM 思考與機械提交分層)
- 攻擊情報記錄:每次得手記「模型 / 方法 / 服務 / round」→ 輸出 B
