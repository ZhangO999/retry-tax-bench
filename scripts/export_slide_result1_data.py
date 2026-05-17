from __future__ import annotations

from pathlib import Path

import pandas as pd


CSV_PATH = Path("results/v7/summary/run_summaries.csv")
OUT_DIR = Path("analysis/slide_results")
T_CRIT_95_DF4 = 2.776

POLICIES = ["rc", "si", "ssi", "mixed_robust"]
POLICY_LABELS = {
    "rc": "RC",
    "si": "SI",
    "ssi": "SSI",
    "mixed_robust": "Mixed-robust",
}
RETRY_ORDER = ["bounded_1", "bounded_3", "bounded_10", "unbounded"]
RETRY_LABELS = {
    "bounded_1": "1 retry",
    "bounded_3": "3 retries",
    "bounded_10": "10 retries",
    "unbounded": "Retry forever",
}


def markdown_table(df: pd.DataFrame) -> str:
    headers = ["Policy", *df.columns.tolist()]
    rows = []
    for index, row in df.iterrows():
        rows.append([index, *[f"{value:.2f}%" for value in row]])

    widths = [
        max(len(str(value)) for value in [header, *[row[i] for row in rows]])
        for i, header in enumerate(headers)
    ]
    header_line = "| " + " | ".join(str(header).ljust(widths[i]) for i, header in enumerate(headers)) + " |"
    sep_line = "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"
    row_lines = [
        "| " + " | ".join(str(value).ljust(widths[i]) for i, value in enumerate(row)) + " |"
        for row in rows
    ]
    return "\n".join([header_line, sep_line, *row_lines])


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(CSV_PATH)

    raw = df[(df["mpl"] == 64) & (df["hotspot_probability"].round(6) == 0.9)].copy()
    raw["policy_label"] = raw["policy"].map(POLICY_LABELS)
    raw["retry_label"] = raw["retry_model"].map(RETRY_LABELS)
    raw["source_csv"] = str(CSV_PATH)
    raw["policy"] = pd.Categorical(raw["policy"], POLICIES, ordered=True)
    raw["retry_model"] = pd.Categorical(raw["retry_model"], RETRY_ORDER, ordered=True)
    raw = raw.sort_values(["policy", "retry_model", "repeat"])

    raw_cols = [
        "source_csv",
        "timestamp_utc",
        "policy",
        "policy_label",
        "retry_model",
        "retry_label",
        "retry_budget",
        "hotspot_probability",
        "hotspot_p",
        "mpl",
        "repeat",
        "seed",
        "warmup_seconds",
        "measurement_seconds",
        "committed",
        "errors",
        "attempts",
        "aborts",
        "tps",
        "committed_tps",
        "error_rate_pct",
        "error_rate",
        "abort_rate_pct",
        "abort_rate",
        "mean_latency_ms",
        "p95_latency_ms",
        "validation_ok",
        "raw_path",
    ]
    raw[raw_cols].to_csv(OUT_DIR / "result1_failure_rate_raw_subset.csv", index=False)

    aggregate = (
        raw.groupby(["policy", "policy_label", "retry_model", "retry_label"], observed=True)
        .agg(
            n=("repeat", "count"),
            mean_failure_rate_pct=("error_rate_pct", "mean"),
            sd_failure_rate_pct=("error_rate_pct", "std"),
            total_errors=("errors", "sum"),
            total_committed=("committed", "sum"),
            mean_committed_tps=("tps", "mean"),
            sd_committed_tps=("tps", "std"),
            mean_abort_rate_pct=("abort_rate_pct", "mean"),
            sd_abort_rate_pct=("abort_rate_pct", "std"),
        )
        .reset_index()
    )
    aggregate["ci95_failure_rate_pct"] = (
        T_CRIT_95_DF4 * aggregate["sd_failure_rate_pct"].fillna(0) / (aggregate["n"] ** 0.5)
    )
    aggregate["ci95_committed_tps"] = (
        T_CRIT_95_DF4 * aggregate["sd_committed_tps"].fillna(0) / (aggregate["n"] ** 0.5)
    )
    aggregate["policy"] = pd.Categorical(aggregate["policy"], POLICIES, ordered=True)
    aggregate["retry_model"] = pd.Categorical(aggregate["retry_model"], RETRY_ORDER, ordered=True)
    aggregate = aggregate.sort_values(["policy", "retry_model"])
    aggregate.to_csv(OUT_DIR / "result1_failure_rate_aggregate.csv", index=False)

    slide_table = aggregate.pivot(
        index="policy_label", columns="retry_label", values="mean_failure_rate_pct"
    )
    slide_table = slide_table.reindex([POLICY_LABELS[policy] for policy in POLICIES])[
        [RETRY_LABELS[retry] for retry in RETRY_ORDER]
    ]
    slide_table.to_csv(OUT_DIR / "result1_failure_rate_slide_table.csv")

    readme = "\n".join(
        [
            "# Result 1: Failure Rate vs Retry Budget",
            "",
            "This folder contains the exact data used for `figures/slides/result1_failure_rate_only_mpl64_p09_95ci.png`.",
            "",
            "Filter used:",
            "",
            "```text",
            "mpl = 64",
            "hotspot_probability = 0.9",
            "all four policies",
            "all four retry budgets",
            "5 repeats per plotted point",
            "```",
            "",
            "Whiskers in the graph are 95% confidence intervals:",
            "",
            "```text",
            "CI95 = 2.776 * SD / sqrt(5)",
            "```",
            "",
            "Files:",
            "",
            "- `result1_failure_rate_raw_subset.csv`: exact raw CSV rows used for the graph.",
            "- `result1_failure_rate_aggregate.csv`: mean, SD, and 95% CI values used for plotting.",
            "- `result1_failure_rate_slide_table.csv`: compact table for slide/report use.",
            "",
            "Compact slide table:",
            "",
            markdown_table(slide_table),
            "",
            "Values are mean failed user request rates, in percent.",
            "",
        ]
    )
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")

    print((OUT_DIR / "result1_failure_rate_raw_subset.csv").resolve())
    print((OUT_DIR / "result1_failure_rate_aggregate.csv").resolve())
    print((OUT_DIR / "result1_failure_rate_slide_table.csv").resolve())
    print((OUT_DIR / "README.md").resolve())
    print()
    print(markdown_table(slide_table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
