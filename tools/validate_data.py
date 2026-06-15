#!/usr/bin/env python3
"""驗證 data/ 是否符合契約。

預設：只驗 JSON Schema（schemas/）。
--strict：額外驗 docs/DATA_CONTRACT.md §6 的隱含契約（schema 驗不到、但前端依賴的）。

退出碼：有 ERROR → 1；只有 WARNING 或全過 → 0。
ERROR  = 違反會讓網站顯示壞掉的硬契約。
WARNING = 允許但提醒（例：trajectory 引用未出貨的 run_id，前端僅不顯示連結）。
"""
import json
import sys
import glob
import os
import re
import argparse
from datetime import datetime

from jsonschema import validate, ValidationError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 對齊前端 astro/src/lib/data.ts 的 SERVICES；加服務要同步改前端與此處。
SERVICES = {"notes", "filelocker", "vault"}
STATUS = {"OK", "MUMBLE", "CORRUPT", "DOWN"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
VBUMP_RE = re.compile(r"^v.+→v.+$")          # 例：v2→v3（全形箭頭 U+2192）
ORDERED_LI_RE = re.compile(r"^\s*\d+\.\s")   # markdown 有序清單（前端不支援）


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def rel(p):
    return os.path.relpath(p, ROOT)


# ── schema 驗證（預設模式） ───────────────────────────────────────────────────
def schema_validate(errors):
    run_schema = load(os.path.join(ROOT, "schemas/run.schema.json"))
    traj_schema = load(os.path.join(ROOT, "schemas/trajectory.schema.json"))
    intel_schema = load(os.path.join(ROOT, "schemas/attack_intel.schema.json"))
    pairs = [(p, run_schema) for p in sorted(glob.glob(os.path.join(ROOT, "data/runs/*.json")))]
    pairs.append((os.path.join(ROOT, "data/recipe/trajectory.json"), traj_schema))
    pairs.append((os.path.join(ROOT, "data/attack_intel.json"), intel_schema))
    for path, schema in pairs:
        try:
            validate(load(path), schema)
            print(f"OK   {rel(path)}")
        except (ValidationError, FileNotFoundError) as e:
            msg = e.message if isinstance(e, ValidationError) else str(e)
            errors.append(f"{rel(path)}: schema — {msg}")


# ── 隱含契約（--strict） ──────────────────────────────────────────────────────
def pct_ok(x):
    return isinstance(x, (int, float)) and 0.0 <= x <= 1.0


def pct_precision_ok(x):
    return round(float(x), 4) == float(x)


def strict_validate(errors, warns):
    run_files = sorted(glob.glob(os.path.join(ROOT, "data/runs/*.json")))
    run_ids_present = {os.path.basename(f)[:-5] for f in run_files}
    recipe_dirs = {
        (m.group(1), m.group(2))
        for p in glob.glob(os.path.join(ROOT, "data/recipe/*/*/PROMPT.md"))
        if (m := re.search(r"/recipe/([^/]+)/([^/]+)/PROMPT\.md$", p))
    }

    # 1～6, 11, 12：每個 run
    for path in run_files:
        d = load(path)
        rid = d.get("run_id", "")
        name = rel(path)

        # 1 run_id 日期 + 檔名一致
        if not DATE_RE.match(rid):
            errors.append(f"{name}: run_id 前 10 碼不是 YYYY-MM-DD（值 {rid!r}）")
        else:
            try:
                datetime.strptime(rid[:10], "%Y-%m-%d")
            except ValueError:
                errors.append(f"{name}: run_id 前 10 碼不是合法日期（值 {rid[:10]!r}）")
        if os.path.basename(path) != f"{rid}.json":
            errors.append(f"{name}: 檔名與 run_id 不符（應為 {rid}.json）")

        # 2 / 12 百分比範圍與精度
        for key in ("flags_held_pct", "sla_uptime_pct"):
            v = d.get("defense", {}).get(key)
            if v is not None:
                if not pct_ok(v):
                    errors.append(f"{name}: defense.{key}={v} 不在 0..1")
                elif not pct_precision_ok(v):
                    warns.append(f"{name}: defense.{key}={v} 精度超過 4 位（冪等建議四捨五入到 4 位）")

        # 3 / 4 / 6 board 與事件
        keysets = []
        teams_seen = set()
        for ts in d.get("timeseries", []):
            rnd = ts.get("round")
            board = ts.get("board", [])
            keys = set()
            has_defense = False
            for c in board:
                team, svc, st = c.get("team"), c.get("service"), c.get("status")
                teams_seen.add(team)
                keys.add((team, svc))
                if team == "defense":
                    has_defense = True
                if svc not in SERVICES:
                    errors.append(f"{name} round {rnd}: board service {svc!r} 不在固定服務集")
                if st not in STATUS:
                    errors.append(f"{name} round {rnd}: board status {st!r} 非法")
            if not has_defense:
                errors.append(f"{name} round {rnd}: board 缺 team=defense 的格子")
            keysets.append(frozenset(keys))
            for dev in ts.get("defense_events", []):
                vb = dev.get("version_bump")
                if vb is not None and not VBUMP_RE.match(vb):
                    errors.append(f"{name} round {rnd}: version_bump {vb!r} 格式應為 v舊→v新")
        # 5 victim ∈ board 出現過的 team
        for ts in d.get("timeseries", []):
            for av in ts.get("attack_events", []):
                vic = av.get("victim")
                if vic not in teams_seen:
                    errors.append(f"{name} round {ts.get('round')}: attack victim {vic!r} 不在 board team 中")
        # 3 board 完整快照：所有 keyframe 的格子集合要一致
        if len(set(keysets)) > 1:
            errors.append(f"{name}: timeseries 各 keyframe 的 board 格子集合不一致（完整快照要求每個 round 列齊相同格子）")

        # 11 defender.recipe 對應 recipe 目錄
        fp = d.get("fingerprint", {}).get("defender", {})
        if (fp.get("model"), fp.get("recipe")) not in recipe_dirs:
            warns.append(f"{name}: defender {fp.get('model')}/{fp.get('recipe')} 在 data/recipe/ 找不到對應配方目錄")

    # 10 跨檔 run_id 對應（warning：允許未出貨）
    traj = load(os.path.join(ROOT, "data/recipe/trajectory.json"))
    for model in traj.get("models", []):
        for v in model.get("versions", []):
            if not pct_ok(v.get("flags_held_pct")):
                errors.append(f"trajectory.json: {model.get('model')} {v.get('version')} flags_held_pct 不在 0..1")
            if v.get("run_id") not in run_ids_present:
                warns.append(f"trajectory.json: {v.get('version')} 的 run_id {v.get('run_id')!r} 無對應 run 檔（前端不顯示回放連結）")
    intel = load(os.path.join(ROOT, "data/attack_intel.json"))
    for meth in intel.get("methods", []):
        for r in meth.get("runs", []):
            if r not in run_ids_present:
                warns.append(f"attack_intel.json: method {meth.get('method')!r} 的 run {r!r} 無對應 run 檔")

    # 7 / 8 / 9 recipe markdown
    md_files = glob.glob(os.path.join(ROOT, "data/recipe/*/*/PROMPT.md")) + \
        glob.glob(os.path.join(ROOT, "data/recipe/*/*/playbook.md"))
    for path in sorted(md_files):
        name = rel(path)
        is_playbook = path.endswith("playbook.md")
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if ORDERED_LI_RE.match(line):
                    errors.append(f"{name}:{i}: 用了有序清單 `1.`（前端 markdown 不支援）")
                if "**" in line:
                    errors.append(f"{name}:{i}: 用了粗體 `**`（前端 markdown 不支援）")
                if is_playbook and line.startswith("## ") and "：" not in line:
                    errors.append(f"{name}:{i}: playbook 攻法標題要用全形冒號 `## <service>：<method>`")


def main():
    ap = argparse.ArgumentParser(description="驗證 data/ 是否符合契約")
    ap.add_argument("--strict", action="store_true", help="額外驗隱含契約（DATA_CONTRACT §6）")
    args = ap.parse_args()

    errors, warns = [], []
    schema_validate(errors)
    if args.strict:
        strict_validate(errors, warns)

    for w in warns:
        print(f"WARN {w}", file=sys.stderr)
    for e in errors:
        print(f"FAIL {e}", file=sys.stderr)

    if args.strict:
        print(f"--- strict：{len(errors)} error、{len(warns)} warning ---")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
