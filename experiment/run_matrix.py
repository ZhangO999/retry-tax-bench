from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from itertools import product
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config" / "experiment_matrix.json"
HARNESS = ROOT / "harness.py"


def read_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


Run = tuple[str, int, str, float, int]


def planned_runs(config: dict, smoke: bool, mini: bool, pilot: bool, micro_pilot: bool) -> list[Run]:
    if smoke:
        return [
            ("rc", 1, "bounded_1", 0.5, 1),
            ("ssi", 2, "bounded_3", 0.5, 1),
            ("mixed_robust", 2, "unbounded", 0.5, 1),
        ]
    if mini:
        return list(
            product(
                config["matrix"]["policies"],
                [1, 32],
                ["bounded_1", "unbounded"],
                [0.1, 0.9],
                [1],
            )
        )
    if pilot:
        return list(
            product(
                ["rc", "si", "ssi", "mixed_robust"],
                [1, 8, 32],
                ["bounded_1", "bounded_3", "unbounded"],
                [0.1, 0.5, 0.9],
                [1, 2],
            )
        )
    if micro_pilot:
        return list(
            product(
                ["rc", "si", "ssi", "mixed_robust"],
                [32],
                ["bounded_1", "bounded_3", "unbounded"],
                [0.1, 0.5, 0.9],
                [1],
            )
        )
    matrix = config["matrix"]
    repeats = range(1, int(matrix["repeats"]) + 1)
    return list(
        product(
            matrix["policies"],
            matrix["mpl"],
            matrix["retry_models"],
            matrix["hotspot_probabilities"],
            repeats,
        )
    )


def build_command(args: argparse.Namespace, config: dict, run: Run) -> list[str]:
    policy, mpl, retry_model, hotspot_probability, repeat = run
    cmd = [
        sys.executable,
        str(HARNESS),
        "--config",
        str(args.config),
        "--policy",
        str(policy),
        "--mpl",
        str(mpl),
        "--retry-model",
        str(retry_model),
        "--hotspot-probability",
        str(hotspot_probability),
        "--repeat",
        str(repeat),
        "--seed",
        str(args.seed if args.seed is not None else config.get("seed", 3991) + repeat),
    ]
    if args.warmup_seconds is not None:
        cmd.extend(["--warmup-seconds", str(args.warmup_seconds)])
    if args.measurement_seconds is not None:
        cmd.extend(["--measurement-seconds", str(args.measurement_seconds)])
    if args.raw_dir:
        cmd.extend(["--raw-dir", args.raw_dir])
    if args.summary_csv:
        cmd.extend(["--summary-csv", args.summary_csv])
    return cmd


def completed_runs(summary_csv: Path) -> set[Run]:
    if not summary_csv.exists():
        return set()

    completed: set[Run] = set()
    with summary_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"policy", "mpl", "retry_model", "hotspot_probability", "repeat"}
        if not required.issubset(reader.fieldnames or set()):
            return set()
        for row in reader:
            completed.add(
                (
                    row["policy"],
                    int(row["mpl"]),
                    row["retry_model"],
                    round(float(row["hotspot_probability"]), 6),
                    int(row["repeat"]),
                )
            )
    return completed


def run_key(run: Run) -> Run:
    policy, mpl, retry_model, hotspot_probability, repeat = run
    return (policy, int(mpl), retry_model, round(float(hotspot_probability), 6), int(repeat))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SmallBank experiment matrix.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--warmup-seconds", type=float)
    parser.add_argument("--measurement-seconds", type=float)
    parser.add_argument("--raw-dir")
    parser.add_argument("--summary-csv")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Skip cells already present in the summary CSV.")
    parser.add_argument("--smoke", action="store_true", help="Run three short cells, not the full matrix.")
    parser.add_argument("--mini", action="store_true", help="Run a representative 32-cell v7 subset.")
    parser.add_argument("--pilot", action="store_true", help="Run the 216-cell figure-quality pilot matrix.")
    parser.add_argument("--micro-pilot", action="store_true", help="Run the 36-cell fast plotting/harness check.")
    args = parser.parse_args()
    if sum([args.smoke, args.mini, args.pilot, args.micro_pilot]) > 1:
        parser.error("--smoke, --mini, --pilot, and --micro-pilot are mutually exclusive")

    config = read_config(args.config)
    runs = planned_runs(config, args.smoke, args.mini, args.pilot, args.micro_pilot)
    output = config["output"]
    if args.pilot:
        args.raw_dir = args.raw_dir or "results/pilot/raw"
        args.summary_csv = args.summary_csv or "results/pilot_results.csv"
        args.warmup_seconds = args.warmup_seconds if args.warmup_seconds is not None else 5
        args.measurement_seconds = args.measurement_seconds if args.measurement_seconds is not None else 15
    if args.micro_pilot:
        args.raw_dir = args.raw_dir or "results/micro_pilot/raw"
        args.summary_csv = args.summary_csv or "results/micro_pilot_results.csv"
        args.warmup_seconds = args.warmup_seconds if args.warmup_seconds is not None else 2
        args.measurement_seconds = args.measurement_seconds if args.measurement_seconds is not None else 6
    summary_csv = Path(args.summary_csv or output["summary_csv"])
    completed = completed_runs(summary_csv) if args.resume else set()
    remaining = [run for run in runs if run_key(run) not in completed]
    print(f"planned_runs={len(runs)} completed={len(completed)} remaining={len(remaining)}", flush=True)
    for index, run in enumerate(remaining, start=1):
        cmd = build_command(args, config, run)
        print(f"[{index}/{len(remaining)}] {' '.join(cmd)}", flush=True)
        if not args.dry_run:
            subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
