#!/usr/bin/env python3
"""驗證 data/ mock 是否符合 schemas/。失敗 exit 1。"""
import json, sys, glob, os
from jsonschema import validate, ValidationError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    run_schema = load(os.path.join(ROOT, "schemas/run.schema.json"))
    traj_schema = load(os.path.join(ROOT, "schemas/trajectory.schema.json"))
    intel_schema = load(os.path.join(ROOT, "schemas/attack_intel.schema.json"))
    errors = []
    pairs = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data/runs/*.json"))):
        pairs.append((p, run_schema))
    pairs.append((os.path.join(ROOT, "data/recipe/trajectory.json"), traj_schema))
    pairs.append((os.path.join(ROOT, "data/attack_intel.json"), intel_schema))
    for path, schema in pairs:
        try:
            validate(load(path), schema)
            print(f"OK   {os.path.relpath(path, ROOT)}")
        except (ValidationError, FileNotFoundError) as e:
            msg = e.message if isinstance(e, ValidationError) else str(e)
            errors.append(f"FAIL {os.path.relpath(path, ROOT)}: {msg}")
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
