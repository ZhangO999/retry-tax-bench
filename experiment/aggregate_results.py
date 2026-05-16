from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path


GROUP_FIELDS = ("policy", "retry_model", "hotspot_probability", "mpl")
VALUE_FIELDS = (
    "committed_tps",
    "observed_tps",
    "attempted_tps",
    "error_rate_pct",
    "abort_rate_pct",
    "latency_mean_ms",
)


def as_float(row: dict, field: str) -> float:
    value = row.get(field, "")
    return float(value) if value != "" else math.nan


def ci95(values: list[float]) -> float:
    clean = [v for v in values if not math.isnan(v)]
    if len(clean) < 2:
        return 0.0
    return 1.96 * statistics.stdev(clean) / math.sqrt(len(clean))


def mean(values: list[float]) -> float:
    clean = [v for v in values if not math.isnan(v)]
    return statistics.mean(clean) if clean else math.nan


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate run_summaries.csv into means and 95% CIs.")
    parser.add_argument("--input", type=Path, default=Path("results/summary/run_summaries.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/summary/aggregate.csv"))
    args = parser.parse_args()

    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    with args.input.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = tuple(row[field] for field in GROUP_FIELDS)
            groups[key].append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [*GROUP_FIELDS, "n"]
    for field in VALUE_FIELDS:
        fieldnames.extend([f"{field}_mean", f"{field}_ci95"])

    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(groups, key=lambda item: (item[0], item[1], float(item[2]), int(item[3]))):
            rows = groups[key]
            out = {field: value for field, value in zip(GROUP_FIELDS, key)}
            out["n"] = len(rows)
            for field in VALUE_FIELDS:
                values = [as_float(row, field) for row in rows]
                out[f"{field}_mean"] = f"{mean(values):.6f}"
                out[f"{field}_ci95"] = f"{ci95(values):.6f}"
            writer.writerow(out)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
