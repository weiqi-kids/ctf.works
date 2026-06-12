# gameserver — ROLE G 計分主機

ForcAD 計分主機的設定與 checkers。建置 playbook 見 [CTF_SPEC.md §2.G](../CTF_SPEC.md)。

預計內容:
- `config.yml.example` — ForcAD 設定範本(teams / tasks 依 `../topology.yml` 填)
- `checkers/<service>/checker.py` — 各漏洞服務的 checker(Hackerdom 相容,`checker_type: pfr`)
- `checkers/requirements.txt`

不放 AI、不跑漏洞服務。
