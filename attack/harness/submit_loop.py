#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""submit_loop.py — 攻擊方機械重打骨架(LLM 思考與機械提交分層)。

定位:這是「磨刀石」的機械手臂。LLM(攻擊方 agent)負責找洞、產出可動 exploit;
本 harness 只負責**每 round 自動重打已知 exploit 並提交 flag**,不做任何思考。

一輪流程(run_round):
  1. 拉 attack_data —— 從計分主機 GET /api/client/attack_data(帶 token),
     或離線時讀本地 mock JSON。每筆 = (team, service, round, attack_data)。
  2. 對防禦主機跑已知 exploit —— subprocess 呼叫 services/<svc>/exploit.py,
     把 attack_data 轉成各 exploit 的 CLI 參數,抓回偷到的內容。
  3. 抽 flag —— 用 flag_format regex([A-Z0-9]{31}=)從輸出抽出 flag。
  4. 提交 flag —— POST 到 flag 接收埠(帶 token);離線時走 dry-run 只記「將提交」。
  5. 記情報 —— 每次得手寫一筆到 intel JSONL(intel_log.log_hit)。

可設定:防禦主機 host、各服務 port、gameserver host/port、flag 接收埠、team token、
模型名、round 數、mock attack_data 路徑、dry-run。

注意:本 harness 只在 attack/ 內。它**呼叫** services/<svc>/exploit.py 但不修改 services/。
真實多 round + 真 LLM 攻擊留部署期;本輪做到結構正確 + 離線可跑一輪。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

import requests

# 讓 import intel_log 不依賴 cwd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import intel_log  # noqa: E402

# services/<svc>/exploit.py 的位置(repo 根 = attack/ 的上一層)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_SERVICES_DIR = os.path.join(_REPO_ROOT, "services")

# flag 格式(topology.yml / CONTRACTS):31 個大寫字母數字 + '='
FLAG_RE = re.compile(r"[A-Z0-9]{31}=")

# 各服務的種子攻法簡名(記入 intel 的 method 欄)
SEED_METHOD = {
    "notes": "idor",
    "filelocker": "path-traversal",
    "vault": "oob-read",
}


# ── 1. 拉 attack_data ────────────────────────────────────────────
def fetch_attack_data(cfg):
    """拉本 round 的 attack_data,回傳 list[dict]。

    每筆 dict 至少含:{service, attack_data, round, (victim_team?)}。
    - 離線(cfg.mock):讀 mock JSON 檔。
    - 線上:GET {gameserver}/api/client/attack_data,帶 token。
    """
    if cfg["mock_path"]:
        with open(cfg["mock_path"], "r", encoding="utf-8") as f:
            doc = json.load(f)
        # mock 結構:{"round": N, "targets": [{service, attack_data, victim_team?}, ...]}
        rnd = doc.get("round", cfg["round"])
        targets = []
        for t in doc.get("targets", []):
            targets.append({
                "service": t["service"],
                "attack_data": t["attack_data"],
                "round": t.get("round", rnd),
                "victim_team": t.get("victim_team", "mock-victim"),
            })
        return targets

    # 線上:向計分主機要 attack_data
    url = f"http://{cfg['gameserver_host']}:{cfg['gameserver_port']}/api/client/attack_data"
    headers = {"X-Team-Token": cfg["token"]} if cfg["token"] else {}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    raw = r.json()
    # ForcAD attack_data 形狀依部署而定;這裡保留一個寬鬆的解析點,
    # 部署期依實際回傳結構調整(留 TODO,誠實標註)。
    return _parse_forcad_attack_data(raw, cfg)


def _parse_forcad_attack_data(raw, cfg):
    """把 ForcAD /api/client/attack_data 的回傳攤平成 targets list。

    TODO(部署期):ForcAD 實際結構通常是
      {service_name: {team_id: [flag_id 或 public_data, ...], ...}, ...}
    這裡先做最常見的攤平;接真實 gameserver 時依當場 schema 校正。
    """
    targets = []
    if isinstance(raw, dict):
        for service, by_team in raw.items():
            if not isinstance(by_team, dict):
                continue
            for team, data_list in by_team.items():
                if not isinstance(data_list, list):
                    data_list = [data_list]
                for ad in data_list:
                    targets.append({
                        "service": service,
                        "attack_data": ad,
                        "round": cfg["round"],
                        "victim_team": str(team),
                    })
    return targets


# ── 2+3. 跑 exploit,抽 flag ──────────────────────────────────────
def run_exploit(service, attack_data, cfg):
    """subprocess 呼叫 services/<svc>/exploit.py,回傳 (stolen_text, argv)。

    把 attack_data 轉成各 exploit 的 CLI(見各 exploit.py 介面):
      notes:      exploit.py <host> <port> <note_id>
      filelocker: exploit.py <host> <victim_user> <victim_name> --port <port>
      vault:      exploit.py <host> <port> <victim_slot>
    """
    exploit_py = os.path.join(_SERVICES_DIR, service, "exploit.py")
    if not os.path.exists(exploit_py):
        raise FileNotFoundError(f"找不到 exploit:{exploit_py}")

    host = cfg["defense_host"]
    port = cfg["service_ports"][service]

    if service == "notes":
        note_id = attack_data if not isinstance(attack_data, dict) else attack_data.get("note_id")
        argv = [cfg["python"], exploit_py, host, str(port), str(note_id)]
    elif service == "filelocker":
        # attack_data = {"user","name"}
        if not isinstance(attack_data, dict):
            raise ValueError(f"filelocker attack_data 應為 dict,得到 {attack_data!r}")
        argv = [cfg["python"], exploit_py, host,
                str(attack_data["user"]), str(attack_data["name"]),
                "--port", str(port)]
    elif service == "vault":
        slot = attack_data if not isinstance(attack_data, dict) else attack_data.get("slot")
        argv = [cfg["python"], exploit_py, host, str(port), str(slot)]
    else:
        raise ValueError(f"未知服務:{service}")

    proc = subprocess.run(
        argv, capture_output=True, text=True, timeout=cfg["exploit_timeout"],
    )
    # 各 exploit 都把偷到的內容印到 stdout(notes/filelocker 也印,vault 純印 flag)
    return proc.stdout, argv, proc.returncode, proc.stderr


def extract_flag(text):
    """從 exploit 輸出抽出符合格式的 flag,抽不到回 None。"""
    m = FLAG_RE.search(text or "")
    return m.group(0) if m else None


# ── 4. 提交 flag ─────────────────────────────────────────────────
def submit_flag(flag, cfg):
    """提交一個 flag 到 flag 接收埠(帶 token)。

    - dry-run:不送,只回 ('DRY_RUN', flag),由呼叫端記「將提交」。
    - 線上:POST 到 {gameserver_host}:{flag_submit_port},body 一行一個 flag,
      帶 X-Team-Token。ForcAD 實際提交協定(HTTP/TCP)依部署為準。
    """
    if cfg["dry_run"]:
        return ("DRY_RUN", flag)
    url = f"http://{cfg['gameserver_host']}:{cfg['flag_submit_port']}/flags"
    headers = {"X-Team-Token": cfg["token"]} if cfg["token"] else {}
    r = requests.put(url, headers=headers, json=[flag], timeout=15)
    return (str(r.status_code), r.text)


# ── 一輪 ─────────────────────────────────────────────────────────
def run_round(cfg):
    """跑一輪:拉 attack_data → 逐 target 跑 exploit → 抽 flag → 提交 → 記情報。

    回傳本輪統計 dict。
    """
    print(f"\n=== round {cfg['round']} 開始 (model={cfg['model']}, "
          f"defense={cfg['defense_host']}, dry_run={cfg['dry_run']}) ===")
    targets = fetch_attack_data(cfg)
    print(f"[*] 取得 {len(targets)} 個攻擊目標")

    stats = {"targets": len(targets), "stolen": 0, "submitted": 0, "errors": 0}

    for t in targets:
        svc = t["service"]
        ad = t["attack_data"]
        rnd = t.get("round", cfg["round"])
        try:
            stdout, argv, rc, stderr = run_exploit(svc, ad, cfg)
        except Exception as e:
            print(f"[!] {svc} exploit 執行失敗:{e}")
            stats["errors"] += 1
            continue

        flag = extract_flag(stdout)
        if not flag:
            print(f"[!] {svc} 未抽到 flag(rc={rc})。stdout 末段:"
                  f"{(stdout or '').strip()[-120:]!r} stderr:{(stderr or '').strip()[-120:]!r}")
            stats["errors"] += 1
            continue

        stats["stolen"] += 1
        print(f"[+] {svc} 偷到 flag:{flag}")

        # 提交
        code, resp = submit_flag(flag, cfg)
        if code == "DRY_RUN":
            print(f"[~] (dry-run) 將提交 flag 到 "
                  f"{cfg['gameserver_host']}:{cfg['flag_submit_port']}:{flag}")
        else:
            print(f"[>] 提交結果 status={code} resp={resp.strip()[:120]!r}")
        stats["submitted"] += 1

        # 記情報
        intel_log.log_hit(
            model=cfg["model"], service=svc,
            method=SEED_METHOD.get(svc, "unknown"),
            round=rnd, flag=flag, out_path=cfg["intel_path"],
        )

    print(f"=== round {cfg['round']} 結束:{stats} ===")
    return stats


def build_cfg(args):
    """把 CLI 參數整理成 cfg dict。"""
    return {
        "model": args.model,
        "defense_host": args.defense_host,
        "service_ports": {
            "notes": args.notes_port,
            "filelocker": args.filelocker_port,
            "vault": args.vault_port,
        },
        "gameserver_host": args.gameserver_host,
        "gameserver_port": args.gameserver_port,
        "flag_submit_port": args.flag_submit_port,
        "token": args.token,
        "mock_path": args.mock,
        "round": args.round,
        "dry_run": args.dry_run,
        "intel_path": args.intel,
        "python": args.python or sys.executable,
        "exploit_timeout": args.exploit_timeout,
    }


def main():
    ap = argparse.ArgumentParser(description="攻擊方機械重打骨架")
    ap.add_argument("--model", default="claude-opus-4-8", help="攻擊方模型名(記入 intel)")
    # 防禦主機 + 服務埠
    ap.add_argument("--defense-host", default="127.0.0.1", help="防禦主機 IP")
    ap.add_argument("--notes-port", type=int, default=8080)
    ap.add_argument("--filelocker-port", type=int, default=9090)
    ap.add_argument("--vault-port", type=int, default=10000)
    # 計分主機 + 提交埠 + token
    ap.add_argument("--gameserver-host", default="10.80.0.2")
    ap.add_argument("--gameserver-port", type=int, default=8080)
    ap.add_argument("--flag-submit-port", type=int, default=31337)
    ap.add_argument("--token", default=os.environ.get("CTF_TEAM_TOKEN", ""),
                    help="team 提交 token(也可用環境變數 CTF_TEAM_TOKEN)")
    # 離線 / 控制
    ap.add_argument("--mock", default=None, help="離線:讀本地 mock attack_data JSON")
    ap.add_argument("--round", type=int, default=1, help="本輪 round 編號")
    ap.add_argument("--rounds", type=int, default=1, help="連跑幾輪")
    ap.add_argument("--round-sleep", type=float, default=0.0, help="每輪間隔秒(節流,避免洪水)")
    ap.add_argument("--dry-run", action="store_true",
                    help="不真的提交 flag,只記『將提交』(離線示範用)")
    ap.add_argument("--intel", default=None, help="intel JSONL 輸出路徑")
    ap.add_argument("--python", default=None, help="跑 exploit 用的 python(預設與本 harness 同)")
    ap.add_argument("--exploit-timeout", type=float, default=30.0, help="單支 exploit 逾時秒")
    args = ap.parse_args()

    cfg = build_cfg(args)
    total = {"targets": 0, "stolen": 0, "submitted": 0, "errors": 0}
    base_round = args.round
    for i in range(args.rounds):
        cfg["round"] = base_round + i
        st = run_round(cfg)
        for k in total:
            total[k] += st[k]
        if i < args.rounds - 1 and args.round_sleep > 0:
            time.sleep(args.round_sleep)  # 節流,守紅線「不洪水打點」

    print(f"\n[done] 共 {args.rounds} 輪累計:{total}")
    # 偷到 0 個 flag 視為失敗(離線示範會 >=1)
    return 0 if total["stolen"] > 0 or total["targets"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
