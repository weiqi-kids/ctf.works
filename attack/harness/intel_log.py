#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""intel_log.py — 攻擊情報記錄(輸出 B)。

每次得手寫一筆到 JSONL,格式對齊 data 契約的 attack_intel 精神
(schemas/attack_intel.schema.json):每筆 = {model, service, method, round, flag}。

JSONL(每行一個 JSON 物件)是「事件流」格式:harness 每偷到一個 flag 就 append 一行,
之後由彙整工具把這些事件 roll-up 成 attack_intel.json 的
`methods[]`(model×service×method,記 first_round)與
`leaderboard[]`(model→flags_stolen)。

用法(CLI):
  python3 intel_log.py --model claude-opus-4-8 --service notes \\
      --method idor --round 3 --flag ABCD...= [--out path.jsonl]

用法(import):
  from intel_log import log_hit
  log_hit(model="...", service="notes", method="idor", round=3, flag="...")
"""

import argparse
import datetime as _dt
import json
import os
import sys

# 預設輸出:attack/intel/hits.jsonl(相對本檔位置,不汙染 services/)
_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INTEL_PATH = os.path.join(_HERE, "..", "intel", "hits.jsonl")


def log_hit(model, service, method, round, flag, out_path=None, ts=None):
    """寫入一筆得手情報到 JSONL,回傳寫入的 dict。

    參數對齊 attack_intel schema 的核心欄位:
      model / service / method / round / flag。
    額外帶 `ts`(ISO8601 UTC 時間戳)方便排攻法時間軸,非 schema 必填。
    """
    out_path = out_path or DEFAULT_INTEL_PATH
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    record = {
        "ts": ts or _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "model": model,
        "service": service,
        "method": method,
        "round": int(round),
        "flag": flag,
    }
    # append 一行,不覆蓋既有事件(事件流只增不改)
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_hits(path=None):
    """讀回所有得手事件(list of dict),檔不存在回空 list。"""
    path = os.path.abspath(path or DEFAULT_INTEL_PATH)
    if not os.path.exists(path):
        return []
    hits = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                hits.append(json.loads(line))
    return hits


def main():
    ap = argparse.ArgumentParser(description="記錄一筆攻擊得手情報")
    ap.add_argument("--model", required=True, help="攻擊方模型,如 claude-opus-4-8")
    ap.add_argument("--service", required=True, help="服務:notes/filelocker/vault")
    ap.add_argument("--method", required=True, help="攻法簡名,如 idor")
    ap.add_argument("--round", required=True, type=int, help="第幾 round 得手")
    ap.add_argument("--flag", required=True, help="偷到的 flag")
    ap.add_argument("--out", default=None, help="JSONL 輸出路徑(預設 attack/intel/hits.jsonl)")
    args = ap.parse_args()

    rec = log_hit(
        model=args.model, service=args.service, method=args.method,
        round=args.round, flag=args.flag, out_path=args.out,
    )
    print(f"[intel] 已記錄:{json.dumps(rec, ensure_ascii=False)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
