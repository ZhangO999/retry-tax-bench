from __future__ import annotations

import argparse
import json
from pathlib import Path


def iter_json_files(path: Path):
    if path.is_file():
        yield path
    else:
        yield from sorted(path.glob("*.json"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate raw harness result JSON files.")
    parser.add_argument("path", nargs="?", type=Path, default=Path("results/main/raw"))
    args = parser.parse_args()

    total = 0
    failures = []
    for path in iter_json_files(args.path):
        total += 1
        data = json.loads(path.read_text(encoding="utf-8"))
        metrics = data["metrics"]
        validation = data["validation"]
        if not validation["ok"]:
            failures.append((path, "validation_ok=false"))
        if metrics["committed"] + metrics["errors"] <= 0:
            failures.append((path, "no measured transactions"))
        if data["metadata"]["retry_model"] == "unbounded" and metrics["errors"] != 0:
            failures.append((path, "unbounded run has visible errors"))

    if failures:
        print(f"validated={total} failures={len(failures)}")
        for path, reason in failures:
            print(f"FAIL {path}: {reason}")
        return 1
    print(f"validated={total} failures=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
