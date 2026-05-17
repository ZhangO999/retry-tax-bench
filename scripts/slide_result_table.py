from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


POLICIES = ["si", "ssi", "mixed_robust"]
RETRY_MODELS = ["bounded_1", "bounded_3", "bounded_10", "unbounded"]
RETRY_LABELS = {
    "bounded_1": "N=1",
    "bounded_3": "N=3",
    "bounded_10": "N=10",
    "unbounded": "N=inf",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce the high-contention error-rate table used in the slides."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("results/v7/summary/run_summaries.csv"),
        help="Path to the v7 run_summaries.csv file.",
    )
    parser.add_argument("--mpl", type=int, default=64)
    parser.add_argument("--hotspot-probability", type=float, default=0.9)
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    filtered = df[
        (df["mpl"] == args.mpl)
        & (df["hotspot_probability"].round(6) == round(args.hotspot_probability, 6))
        & (df["policy"].isin(POLICIES))
    ].copy()

    expected_rows = len(POLICIES) * len(RETRY_MODELS) * 5
    print(f"source_csv={args.csv}")
    print(f"filter: mpl={args.mpl}, hotspot_probability={args.hotspot_probability}")
    print(f"filtered_rows={len(filtered)} expected_rows={expected_rows}")
    print()

    if len(filtered) != expected_rows:
        print("warning: filtered row count does not match the expected 3 policies x 4 retry models x 5 repeats")
        print()

    filtered["recomputed_error_rate_pct"] = (
        filtered["errors"] / (filtered["committed"] + filtered["errors"]) * 100
    )
    max_diff = (filtered["error_rate_pct"] - filtered["recomputed_error_rate_pct"]).abs().max()
    print(f"max_error_rate_formula_diff={max_diff:.12f}")
    print(f"unbounded_total_errors={int(filtered[filtered['retry_model'] == 'unbounded']['errors'].sum())}")
    print()

    raw_rows = filtered[
        ["policy", "retry_model", "repeat", "committed", "errors", "error_rate_pct"]
    ].copy()
    raw_rows["policy"] = pd.Categorical(raw_rows["policy"], POLICIES, ordered=True)
    raw_rows["retry_model"] = pd.Categorical(raw_rows["retry_model"], RETRY_MODELS, ordered=True)
    raw_rows = raw_rows.sort_values(["policy", "retry_model", "repeat"])
    print("Raw rows used:")
    print(raw_rows.to_string(index=False, formatters={"error_rate_pct": "{:.6f}".format}))
    print()

    aggregate = (
        filtered.groupby(["policy", "retry_model"], observed=True)
        .agg(
            mean_error_rate_pct=("error_rate_pct", "mean"),
            sd_error_rate_pct=("error_rate_pct", "std"),
            total_errors=("errors", "sum"),
            total_committed=("committed", "sum"),
            repeats=("repeat", "count"),
        )
        .reset_index()
    )
    aggregate["policy"] = pd.Categorical(aggregate["policy"], POLICIES, ordered=True)
    aggregate["retry_model"] = pd.Categorical(aggregate["retry_model"], RETRY_MODELS, ordered=True)
    aggregate = aggregate.sort_values(["policy", "retry_model"])

    print("Aggregated values:")
    print(
        aggregate.to_string(
            index=False,
            formatters={
                "mean_error_rate_pct": "{:.6f}".format,
                "sd_error_rate_pct": "{:.6f}".format,
            },
        )
    )
    print()

    slide_table = aggregate.pivot(
        index="policy", columns="retry_model", values="mean_error_rate_pct"
    ).reindex(POLICIES)[RETRY_MODELS]
    slide_table = slide_table.rename(columns=RETRY_LABELS)

    print("Slide table, rounded:")
    print(slide_table.to_string(formatters={column: "{:.2f}%".format for column in slide_table.columns}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
