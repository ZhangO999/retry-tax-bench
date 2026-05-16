from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


POLICY_ORDER = ["rc", "si", "ssi", "mixed_robust"]
RETRY_ORDER = ["bounded_1", "bounded_3", "bounded_10", "unbounded"]
METRICS = {
    "committed_tps": "Committed TPS",
    "attempted_tps": "Attempted TPS",
    "error_rate_pct": "Error rate (%)",
    "abort_rate_pct": "Abort rate (%)",
}


def load_rows(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def probability_label(value: str | float) -> str:
    return f"{float(value):g}".replace(".", "p")


def plot_metric_by_mpl(
    rows: list[dict],
    retry_model: str,
    hotspot_probability: str,
    metric: str,
    output: Path,
) -> None:
    by_policy = defaultdict(list)
    for row in rows:
        if row["retry_model"] == retry_model and row["hotspot_probability"] == hotspot_probability:
            by_policy[row["policy"]].append(row)
    if not by_policy:
        return

    plt.figure(figsize=(8, 4.8))
    for policy in POLICY_ORDER:
        points = sorted(by_policy.get(policy, []), key=lambda row: int(row["mpl"]))
        if not points:
            continue
        x = [int(row["mpl"]) for row in points]
        y = [float(row[f"{metric}_mean"]) for row in points]
        yerr = [float(row[f"{metric}_ci95"]) for row in points]
        plt.errorbar(x, y, yerr=yerr, marker="o", linewidth=1.8, capsize=3, label=policy)
    plt.xlabel("MPL")
    plt.ylabel(METRICS[metric])
    plt.title(f"{METRICS[metric]} ({retry_model}, p={float(hotspot_probability):g})")
    plt.xticks(sorted({int(row["mpl"]) for row in rows}))
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=180)
    plt.close()
    print(f"wrote {output}")


def plot_retry_sweep(
    rows: list[dict],
    hotspot_probability: str,
    mpl: str,
    metric: str,
    output: Path,
) -> None:
    by_policy = defaultdict(list)
    for row in rows:
        if row["hotspot_probability"] == hotspot_probability and row["mpl"] == mpl:
            by_policy[row["policy"]].append(row)
    if not by_policy:
        return

    retry_index = {name: i for i, name in enumerate(RETRY_ORDER)}
    plt.figure(figsize=(8, 4.8))
    for policy in POLICY_ORDER:
        points = sorted(by_policy.get(policy, []), key=lambda row: retry_index.get(row["retry_model"], 999))
        if not points:
            continue
        x = [row["retry_model"].replace("bounded_", "N=") for row in points]
        y = [float(row[f"{metric}_mean"]) for row in points]
        yerr = [float(row[f"{metric}_ci95"]) for row in points]
        plt.errorbar(x, y, yerr=yerr, marker="o", linewidth=1.8, capsize=3, label=policy)
    plt.xlabel("Retry model")
    plt.ylabel(METRICS[metric])
    plt.title(f"{METRICS[metric]} retry sweep (p={float(hotspot_probability):g}, MPL={mpl})")
    plt.grid(True, axis="y", alpha=0.25)
    plt.legend()
    plt.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=180)
    plt.close()
    print(f"wrote {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate experiment figures from aggregate.csv.")
    parser.add_argument("--input", type=Path, default=Path("results/v7/summary/aggregate.csv"))
    parser.add_argument("--figures-dir", type=Path, default=Path("results/v7/figures"))
    args = parser.parse_args()

    rows = load_rows(args.input)
    hotspot_probabilities = sorted({row["hotspot_probability"] for row in rows}, key=float)
    retry_models = [retry for retry in RETRY_ORDER if retry in {row["retry_model"] for row in rows}]

    for retry_model in retry_models:
        for hotspot_probability in hotspot_probabilities:
            p_label = probability_label(hotspot_probability)
            for metric in METRICS:
                plot_metric_by_mpl(
                    rows,
                    retry_model,
                    hotspot_probability,
                    metric,
                    args.figures_dir / f"{metric}_{retry_model}_p{p_label}.png",
                )

    for hotspot_probability in hotspot_probabilities:
        p_label = probability_label(hotspot_probability)
        for mpl in ("8", "32", "64"):
            for metric in ("committed_tps", "error_rate_pct", "abort_rate_pct"):
                plot_retry_sweep(
                    rows,
                    hotspot_probability,
                    mpl,
                    metric,
                    args.figures_dir / f"retry_sweep_{metric}_p{p_label}_mpl{mpl}.png",
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
