from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


POLICIES = ["rc", "si", "ssi", "mixed_robust"]
RETRY_MODELS = ["bounded_1", "bounded_3", "unbounded"]
POLICY_LABELS = {
    "rc": "RC",
    "si": "SI",
    "ssi": "SSI",
    "mixed_robust": "Mixed-robust",
}
RETRY_LABELS = {
    "bounded_1": "N=1",
    "bounded_3": "N=3",
    "unbounded": "infinity",
}


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def as_float(row: dict[str, str], field: str) -> float:
    value = row.get(field, "")
    return float(value) if value != "" else math.nan


def mean(values: list[float]) -> float:
    clean = [value for value in values if not math.isnan(value)]
    return statistics.mean(clean) if clean else math.nan


def aggregate(rows: list[dict[str, str]]) -> dict[tuple[str, int, str, float], dict[str, float]]:
    groups: dict[tuple[str, int, str, float], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (
            row["policy"],
            int(row["mpl"]),
            row["retry_model"],
            round(float(row["hotspot_probability"]), 6),
        )
        groups[key].append(row)

    aggregated = {}
    for key, group_rows in groups.items():
        aggregated[key] = {
            "n": float(len(group_rows)),
            "committed_tps": mean([as_float(row, "committed_tps") for row in group_rows]),
            "error_rate_pct": mean([as_float(row, "error_rate_pct") for row in group_rows]),
            "abort_rate_pct": mean([as_float(row, "abort_rate_pct") for row in group_rows]),
            "errors": mean([as_float(row, "errors") for row in group_rows]),
        }
    return aggregated


def get_metric(
    aggregated: dict[tuple[str, int, str, float], dict[str, float]],
    policy: str,
    mpl: int,
    retry_model: str,
    hotspot_probability: float,
    metric: str,
) -> float:
    values = aggregated.get((policy, mpl, retry_model, round(hotspot_probability, 6)))
    return math.nan if values is None else values[metric]


def save_line_plot(
    output: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    x_values: list,
    series: dict[str, list[float]],
    x_labels: list[str] | None = None,
) -> None:
    plt.figure(figsize=(8, 4.8))
    for policy in POLICIES:
        y_values = series.get(policy, [])
        if not y_values or all(math.isnan(value) for value in y_values):
            continue
        plt.plot(x_values, y_values, marker="o", linewidth=2.0, label=POLICY_LABELS[policy])
    if x_labels is not None:
        plt.xticks(x_values, x_labels)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.25)
    if plt.gca().get_legend_handles_labels()[0]:
        plt.legend()
    plt.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=180)
    plt.close()
    print(f"wrote {output}")


def plot_tps_vs_hotspot(aggregated: dict, figures_dir: Path) -> None:
    hotspots = [0.1, 0.5, 0.9]
    series = {
        policy: [get_metric(aggregated, policy, 32, "unbounded", p, "committed_tps") for p in hotspots]
        for policy in POLICIES
    }
    save_line_plot(
        figures_dir / "01_tps_vs_hotspot_mpl32_unbounded.png",
        "TPS vs hotspot probability (MPL=32, unbounded retries)",
        "Hotspot probability",
        "Committed TPS",
        hotspots,
        series,
    )


def plot_error_vs_hotspot(aggregated: dict, figures_dir: Path) -> None:
    hotspots = [0.1, 0.5, 0.9]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for axis, retry_model in zip(axes, ["bounded_1", "bounded_3"]):
        for policy in POLICIES:
            y_values = [
                get_metric(aggregated, policy, 32, retry_model, p, "error_rate_pct")
                for p in hotspots
            ]
            if all(math.isnan(value) for value in y_values):
                continue
            axis.plot(hotspots, y_values, marker="o", linewidth=2.0, label=POLICY_LABELS[policy])
        axis.set_title(RETRY_LABELS[retry_model])
        axis.set_xlabel("Hotspot probability")
        axis.grid(True, alpha=0.25)
    axes[0].set_ylabel("Error rate (%)")
    if axes[1].get_legend_handles_labels()[0]:
        axes[1].legend()
    fig.suptitle("Error rate vs hotspot probability (MPL=32)")
    fig.tight_layout()
    output = figures_dir / "02_error_rate_vs_hotspot_mpl32_bounded_1_and_3.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)
    print(f"wrote {output}")


def plot_error_vs_retry_budget(aggregated: dict, figures_dir: Path) -> None:
    x_values = [1, 2, 3]
    series = {
        policy: [
            get_metric(aggregated, policy, 32, retry_model, 0.9, "error_rate_pct")
            for retry_model in RETRY_MODELS
        ]
        for policy in POLICIES
    }
    save_line_plot(
        figures_dir / "03_error_rate_vs_retry_budget_mpl32_p0p9.png",
        "Error rate vs retry budget (MPL=32, p=0.9)",
        "Retry budget",
        "Error rate (%)",
        x_values,
        series,
        [RETRY_LABELS[retry_model] for retry_model in RETRY_MODELS],
    )


def plot_tps_vs_mpl(aggregated: dict, figures_dir: Path) -> None:
    mpls = [1, 8, 32]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for axis, retry_model in zip(axes, ["bounded_1", "unbounded"]):
        for policy in POLICIES:
            y_values = [
                get_metric(aggregated, policy, mpl, retry_model, 0.9, "committed_tps")
                for mpl in mpls
            ]
            if all(math.isnan(value) for value in y_values):
                continue
            axis.plot(mpls, y_values, marker="o", linewidth=2.0, label=POLICY_LABELS[policy])
        axis.set_title(RETRY_LABELS[retry_model])
        axis.set_xlabel("MPL")
        axis.grid(True, alpha=0.25)
    axes[0].set_ylabel("Committed TPS")
    if axes[1].get_legend_handles_labels()[0]:
        axes[1].legend()
    fig.suptitle("TPS vs MPL (p=0.9)")
    fig.tight_layout()
    output = figures_dir / "04_tps_vs_mpl_p0p9_bounded_1_and_unbounded.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)
    print(f"wrote {output}")


def plot_abort_vs_hotspot(aggregated: dict, figures_dir: Path) -> None:
    hotspots = [0.1, 0.5, 0.9]
    series = {
        policy: [get_metric(aggregated, policy, 32, "unbounded", p, "abort_rate_pct") for p in hotspots]
        for policy in POLICIES
    }
    save_line_plot(
        figures_dir / "05_abort_rate_vs_hotspot_mpl32_unbounded.png",
        "Abort rate vs hotspot probability (MPL=32, unbounded retries)",
        "Hotspot probability",
        "Abort rate (%)",
        hotspots,
        series,
    )


def print_sanity_summary(rows: list[dict[str, str]], aggregated: dict, expected_rows: int) -> None:
    row_count = len(rows)
    print("\nSanity-check summary")
    print(f"- CSV row count: {row_count} (expected {expected_rows})")
    if row_count != expected_rows:
        print("  FLAG: row count does not match the requested pilot matrix.")

    unbounded_errors = sum(int(float(row["errors"])) for row in rows if row["retry_model"] == "unbounded")
    print(f"- Unbounded user-visible errors: {unbounded_errors}")
    if unbounded_errors != 0:
        print("  FLAG: unbounded retry should have zero user-visible errors.")

    high_hotspot_not_worse = []
    for policy in POLICIES:
        low_abort = get_metric(aggregated, policy, 32, "unbounded", 0.1, "abort_rate_pct")
        high_abort = get_metric(aggregated, policy, 32, "unbounded", 0.9, "abort_rate_pct")
        low_tps = get_metric(aggregated, policy, 32, "unbounded", 0.1, "committed_tps")
        high_tps = get_metric(aggregated, policy, 32, "unbounded", 0.9, "committed_tps")
        if any(math.isnan(value) for value in [low_abort, high_abort, low_tps, high_tps]):
            continue
        if not (high_abort > low_abort or high_tps < low_tps):
            high_hotspot_not_worse.append(policy)
    print("- p=0.9 vs p=0.1: high hotspot generally worse?", "yes" if not high_hotspot_not_worse else "mixed")
    if high_hotspot_not_worse:
        print(f"  FLAG: not clearly worse for {', '.join(high_hotspot_not_worse)}.")

    retry_flags = []
    for policy in POLICIES:
        n1 = get_metric(aggregated, policy, 32, "bounded_1", 0.9, "error_rate_pct")
        n3 = get_metric(aggregated, policy, 32, "bounded_3", 0.9, "error_rate_pct")
        inf = get_metric(aggregated, policy, 32, "unbounded", 0.9, "error_rate_pct")
        if any(math.isnan(value) for value in [n1, n3, inf]):
            continue
        if not (n1 >= n3 >= inf):
            retry_flags.append(policy)
    print("- N=1 vs N=3 vs infinity: error rate decreases with budget?", "yes" if not retry_flags else "mixed")
    if retry_flags:
        print(f"  FLAG: retry-budget ordering not monotonic for {', '.join(retry_flags)}.")

    mpl_identical = []
    for policy in POLICIES:
        mpl1 = get_metric(aggregated, policy, 1, "unbounded", 0.9, "committed_tps")
        mpl32 = get_metric(aggregated, policy, 32, "unbounded", 0.9, "committed_tps")
        if any(math.isnan(value) for value in [mpl1, mpl32]):
            continue
        if math.isclose(mpl1, mpl32, rel_tol=0.01, abs_tol=1.0):
            mpl_identical.append(policy)
    print("- MPL=1 vs MPL=32: throughput differs?", "yes" if not mpl_identical else "mixed")
    if mpl_identical:
        print(f"  FLAG: MPL did not materially affect {', '.join(mpl_identical)}.")

    signature = {
        policy: round(get_metric(aggregated, policy, 32, "bounded_1", 0.9, "committed_tps"), 2)
        for policy in POLICIES
    }
    print(f"- Policy TPS signature at MPL=32, p=0.9, N=1: {signature}")
    if len(set(signature.values())) <= 1:
        print("  FLAG: all policy lines are identical.")

    high_contention_errors = [
        get_metric(aggregated, policy, 32, "bounded_1", 0.9, "error_rate_pct")
        for policy in ["ssi", "mixed_robust"]
    ]
    high_contention_errors = [value for value in high_contention_errors if not math.isnan(value)]
    max_error = max(high_contention_errors) if high_contention_errors else math.nan
    print(f"- Max SSI/Mixed error rate at MPL=32, p=0.9, N=1: {max_error:.3f}%")
    if max_error == 0:
        print("  FLAG: all relevant high-contention error rates are zero.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate requested pilot figures and sanity checks.")
    parser.add_argument("--input", type=Path, default=Path("results/pilot_results.csv"))
    parser.add_argument("--figures-dir", type=Path, default=Path("figures/pilot"))
    parser.add_argument("--expected-rows", type=int, default=216)
    args = parser.parse_args()

    rows = load_rows(args.input)
    aggregated = aggregate(rows)
    plot_tps_vs_hotspot(aggregated, args.figures_dir)
    plot_error_vs_hotspot(aggregated, args.figures_dir)
    plot_error_vs_retry_budget(aggregated, args.figures_dir)
    plot_tps_vs_mpl(aggregated, args.figures_dir)
    plot_abort_vs_hotspot(aggregated, args.figures_dir)
    print_sanity_summary(rows, aggregated, args.expected_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
