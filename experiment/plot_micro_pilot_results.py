from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


POLICIES = ["rc", "si", "ssi", "mixed_robust"]
POLICY_LABELS = {
    "rc": "RC",
    "si": "SI",
    "ssi": "SSI",
    "mixed_robust": "Mixed-robust",
}
RETRY_ORDER = ["1", "3", "inf"]
RETRY_LABELS = {"1": "1", "3": "3", "inf": "infinity"}


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def value(row: dict[str, str], *names: str) -> str:
    for name in names:
        if name in row and row[name] != "":
            return row[name]
    raise KeyError(f"Missing any of columns: {names}")


def fvalue(row: dict[str, str], *names: str) -> float:
    return float(value(row, *names))


def normalized(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    for row in rows:
        retry_budget = row.get("retry_budget")
        if not retry_budget:
            retry_model = row["retry_model"]
            retry_budget = "inf" if retry_model == "unbounded" else retry_model.replace("bounded_", "")
        result.append(
            {
                **row,
                "retry_budget": retry_budget,
                "hotspot_p": value(row, "hotspot_p", "hotspot_probability"),
                "tps": value(row, "tps", "committed_tps"),
                "abort_rate": value(row, "abort_rate", "abort_rate_pct"),
                "error_rate": value(row, "error_rate", "error_rate_pct"),
            }
        )
    return result


def grouped(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], dict[str, str]]:
    return {
        (row["policy"], row["retry_budget"], f"{float(row['hotspot_p']):.6f}"): row
        for row in rows
    }


def metric(
    by_key: dict[tuple[str, str, str], dict[str, str]],
    policy: str,
    retry_budget: str,
    hotspot_p: float,
    field: str,
) -> float:
    row = by_key.get((policy, retry_budget, f"{hotspot_p:.6f}"))
    if row is None:
        return math.nan
    return fvalue(row, field)


def plot_lines(
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
        if not y_values or all(math.isnan(v) for v in y_values):
            continue
        plt.plot(x_values, y_values, marker="o", linewidth=2.0, label=POLICY_LABELS[policy])
    if x_labels:
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


def make_figures(rows: list[dict[str, str]], figures_dir: Path) -> None:
    by_key = grouped(rows)
    hotspots = [0.1, 0.5, 0.9]
    x_retry = [1, 3, 4]

    plot_lines(
        figures_dir / "tps_vs_hotspot_ninf_mpl32.png",
        "TPS vs hotspot probability (N=infinity, MPL=32)",
        "Hotspot probability",
        "TPS",
        hotspots,
        {
            policy: [metric(by_key, policy, "inf", p, "tps") for p in hotspots]
            for policy in POLICIES
        },
    )
    for retry_budget in ["1", "3"]:
        plot_lines(
            figures_dir / f"tps_vs_hotspot_n{retry_budget}_mpl32.png",
            f"TPS vs hotspot probability (N={retry_budget}, MPL=32)",
            "Hotspot probability",
            "TPS",
            hotspots,
            {
                policy: [metric(by_key, policy, retry_budget, p, "tps") for p in hotspots]
                for policy in POLICIES
            },
        )
        plot_lines(
            figures_dir / f"error_rate_vs_hotspot_n{retry_budget}_mpl32.png",
            f"Error rate vs hotspot probability (N={retry_budget}, MPL=32)",
            "Hotspot probability",
            "Error rate (%)",
            hotspots,
            {
                policy: [metric(by_key, policy, retry_budget, p, "error_rate") for p in hotspots]
                for policy in POLICIES
            },
        )
        plot_lines(
            figures_dir / f"abort_rate_vs_hotspot_n{retry_budget}_mpl32.png",
            f"Abort rate vs hotspot probability (N={retry_budget}, MPL=32)",
            "Hotspot probability",
            "Abort rate (%)",
            hotspots,
            {
                policy: [metric(by_key, policy, retry_budget, p, "abort_rate") for p in hotspots]
                for policy in POLICIES
            },
        )
    plot_lines(
        figures_dir / "error_rate_vs_retry_p09_mpl32.png",
        "Error rate vs retry budget (p=0.9, MPL=32)",
        "Retry budget",
        "Error rate (%)",
        x_retry,
        {
            policy: [metric(by_key, policy, retry, 0.9, "error_rate") for retry in RETRY_ORDER]
            for policy in POLICIES
        },
        [RETRY_LABELS[retry] for retry in RETRY_ORDER],
    )
    plot_lines(
        figures_dir / "abort_rate_vs_hotspot_ninf_mpl32.png",
        "Abort rate vs hotspot probability (N=infinity, MPL=32)",
        "Hotspot probability",
        "Abort rate (%)",
        hotspots,
        {
            policy: [metric(by_key, policy, "inf", p, "abort_rate") for p in hotspots]
            for policy in POLICIES
        },
    )


def almost_same(values: list[float], tolerance: float = 0.01) -> bool:
    clean = [v for v in values if not math.isnan(v)]
    if len(clean) < 2:
        return False
    return max(clean) - min(clean) <= tolerance * max(1.0, abs(sum(clean) / len(clean)))


def sanity_summary(rows: list[dict[str, str]], expected_rows: int) -> str:
    by_key = grouped(rows)
    lines = ["Sanity-check summary"]
    row_count = len(rows)
    lines.append(f"- CSV row count: {row_count} (expected {expected_rows})")
    if row_count != expected_rows:
        lines.append("  FLAG: row count does not match the micro-pilot matrix.")

    ninf_errors = sum(int(fvalue(row, "errors")) for row in rows if row["retry_budget"] == "inf")
    lines.append(f"- N=infinity user-visible errors: {ninf_errors}")
    if ninf_errors:
        lines.append("  FLAG: N=infinity has user-visible errors.")

    p_behavior_flags = []
    for policy in POLICIES:
        tps_values = [metric(by_key, policy, "inf", p, "tps") for p in [0.1, 0.5, 0.9]]
        abort_values = [metric(by_key, policy, "inf", p, "abort_rate") for p in [0.1, 0.5, 0.9]]
        if almost_same(tps_values) and almost_same(abort_values):
            p_behavior_flags.append(policy)
    lines.append(
        "- p=0.1/0.5/0.9 change TPS or abort behavior? "
        + ("yes" if not p_behavior_flags else "mixed")
    )
    if p_behavior_flags:
        lines.append(f"  FLAG: hotspot levels are almost identical for {', '.join(p_behavior_flags)}.")

    high_vs_low = []
    for policy in POLICIES:
        low_tps = metric(by_key, policy, "inf", 0.1, "tps")
        high_tps = metric(by_key, policy, "inf", 0.9, "tps")
        low_abort = metric(by_key, policy, "inf", 0.1, "abort_rate")
        high_abort = metric(by_key, policy, "inf", 0.9, "abort_rate")
        low_error = metric(by_key, policy, "1", 0.1, "error_rate")
        high_error = metric(by_key, policy, "1", 0.9, "error_rate")
        if not (high_tps < low_tps or high_abort > low_abort or high_error > low_error):
            high_vs_low.append(policy)
    lines.append(
        "- p=0.9 vs p=0.1 shows lower TPS and/or higher aborts/errors? "
        + ("yes" if not high_vs_low else "mixed")
    )
    if high_vs_low:
        lines.append(f"  FLAG: high hotspot not clearly worse for {', '.join(high_vs_low)}.")

    retry_flags = []
    for policy in POLICIES:
        n1 = metric(by_key, policy, "1", 0.9, "error_rate")
        n3 = metric(by_key, policy, "3", 0.9, "error_rate")
        ninf = metric(by_key, policy, "inf", 0.9, "error_rate")
        if not (n1 >= n3 >= ninf):
            retry_flags.append(policy)
    lines.append(
        "- N=1 vs N=3 vs N=infinity error rate decreases? "
        + ("yes" if not retry_flags else "mixed")
    )
    if retry_flags:
        lines.append(f"  FLAG: retry ordering not monotonic for {', '.join(retry_flags)}.")

    signatures = {
        policy: (
            round(metric(by_key, policy, "1", 0.9, "tps"), 2),
            round(metric(by_key, policy, "1", 0.9, "error_rate"), 3),
            round(metric(by_key, policy, "inf", 0.9, "abort_rate"), 3),
        )
        for policy in POLICIES
    }
    lines.append(f"- Policy signatures at p=0.9: {signatures}")
    if len(set(signatures.values())) <= 1:
        lines.append("  FLAG: RC, SI, SSI, and Mixed-robust are identical.")

    relevant_errors = [
        metric(by_key, policy, "1", 0.9, "error_rate")
        for policy in ["ssi", "mixed_robust"]
    ]
    max_relevant_error = max(v for v in relevant_errors if not math.isnan(v))
    lines.append(f"- Max SSI/Mixed error rate at p=0.9, N=1: {max_relevant_error:.3f}%")
    if max_relevant_error == 0:
        lines.append("  FLAG: all high-contention SSI/Mixed error rates are zero.")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate micro-pilot figures and sanity checks.")
    parser.add_argument("--input", type=Path, default=Path("results/micro_pilot_results.csv"))
    parser.add_argument("--figures-dir", type=Path, default=Path("figures/micro_pilot"))
    parser.add_argument("--expected-rows", type=int, default=36)
    args = parser.parse_args()

    rows = normalized(load_rows(args.input))
    make_figures(rows, args.figures_dir)
    print()
    print(sanity_summary(rows, args.expected_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
