from __future__ import annotations

import argparse
import csv
from pathlib import Path


KEY_COLUMNS = ("policy", "mpl", "retry_model", "hotspot_probability", "repeat")


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, list(reader)


def key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return tuple(row[column] for column in KEY_COLUMNS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge AWS shard CSV summaries.")
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Shard CSVs. Defaults to results/aws_v7/shards/*/run_summaries.csv.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/aws_v7/summary/run_summaries.csv"),
    )
    parser.add_argument("--expected-rows", type=int, default=960)
    args = parser.parse_args()

    inputs = args.inputs or sorted(Path("results/aws_v7/shards").glob("*/run_summaries.csv"))
    if not inputs:
        raise SystemExit("No shard summaries found.")

    all_rows: list[dict[str, str]] = []
    fieldnames: list[str] | None = None
    for path in inputs:
        current_fields, rows = read_rows(path)
        if fieldnames is None:
            fieldnames = current_fields
        elif current_fields != fieldnames:
            raise SystemExit(f"CSV header mismatch in {path}")
        print(f"{path}: {len(rows)} rows")
        all_rows.extend(rows)

    seen: set[tuple[str, str, str, str, str]] = set()
    duplicates: list[tuple[str, str, str, str, str]] = []
    unique_rows: list[dict[str, str]] = []
    for row in all_rows:
        row_key = key(row)
        if row_key in seen:
            duplicates.append(row_key)
            continue
        seen.add(row_key)
        unique_rows.append(row)

    unique_rows.sort(
        key=lambda row: (
            row["policy"],
            int(row["mpl"]),
            row["retry_model"],
            float(row["hotspot_probability"]),
            int(row["repeat"]),
        )
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(unique_rows)

    print(f"merged_rows={len(unique_rows)} output={args.output}")
    if duplicates:
        print(f"warning: dropped_duplicate_rows={len(duplicates)}")
    if len(unique_rows) != args.expected_rows:
        print(f"warning: expected_rows={args.expected_rows} actual_rows={len(unique_rows)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
