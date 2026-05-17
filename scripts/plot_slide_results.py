from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


CSV_PATH = Path("results/v7/summary/run_summaries.csv")
OUT_DIR = Path("figures/slides")
T_CRIT_95_DF4 = 2.776

POLICIES = ["rc", "si", "ssi", "mixed_robust"]
POLICY_LABELS = {
    "rc": "RC",
    "si": "SI",
    "ssi": "SSI",
    "mixed_robust": "Mixed-robust",
}
COLORS = {
    "rc": "#4d4d4d",
    "si": "#1f77b4",
    "ssi": "#d62728",
    "mixed_robust": "#2ca02c",
}
MARKERS = {
    "rc": "o",
    "si": "s",
    "ssi": "^",
    "mixed_robust": "D",
}
RETRY_ORDER = ["bounded_1", "bounded_3", "bounded_10", "unbounded"]
RETRY_LABELS = ["1 retry", "3 retries", "10 retries", "Retry forever"]
RETRY_X = list(range(len(RETRY_ORDER)))


def summarize(
    df: pd.DataFrame,
    group_cols: list[str],
    metric: str,
) -> pd.DataFrame:
    summary = (
        df.groupby(group_cols, observed=True)[metric]
        .agg(["mean", "std", "count"])
        .reset_index()
        .rename(columns={"std": "sd"})
    )
    summary["ci95"] = T_CRIT_95_DF4 * summary["sd"].fillna(0) / (summary["count"] ** 0.5)
    return summary


def style_axis(ax: plt.Axes) -> None:
    ax.grid(axis="y", color="#dddddd", linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=9)


def plot_retry_budget(df: pd.DataFrame) -> None:
    filtered = df[(df["mpl"] == 64) & (df["hotspot_probability"].round(6) == 0.9)].copy()
    tps = summarize(filtered, ["policy", "retry_model"], "tps")
    err = summarize(filtered, ["policy", "retry_model"], "error_rate_pct")

    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.8), dpi=220)
    fig.patch.set_facecolor("white")

    for ax, data, ylabel, title, ylim in [
        (axes[0], tps, "Committed TPS", "Successful transactions per second", None),
        (axes[1], err, "Failed user requests (%)", "Requests that ran out of retries", (-0.5, 19)),
    ]:
        for policy in POLICIES:
            values = data[data["policy"] == policy].set_index("retry_model").reindex(RETRY_ORDER)
            ax.errorbar(
                RETRY_X,
                values["mean"],
                yerr=values["ci95"].fillna(0),
                label=POLICY_LABELS[policy],
                color=COLORS[policy],
                marker=MARKERS[policy],
                linewidth=2.0,
                markersize=5.5,
                capsize=3.5,
            )
        ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_xticks(RETRY_X)
        ax.set_xticklabels(RETRY_LABELS, rotation=18, ha="right")
        if ylim is not None:
            ax.set_ylim(*ylim)
        style_axis(ax)

    axes[0].legend(frameon=False, loc="best", fontsize=9)
    fig.suptitle(
        "Retry budget effect under high contention",
        fontsize=18,
        fontweight="bold",
        x=0.03,
        ha="left",
    )
    fig.text(
        0.03,
        0.92,
        "SmallBank, MPL = 64, hotspot probability = 0.9; points are means, whiskers are 95% CIs over 5 repeats.",
        fontsize=10,
        color="#333333",
        ha="left",
    )
    fig.text(
        0.03,
        0.02,
        "Takeaway: allowing more retries sharply reduces failed requests; committed TPS alone should not be read without the failure rate.",
        fontsize=10,
        color="#333333",
        ha="left",
    )
    fig.tight_layout(rect=[0.02, 0.07, 0.98, 0.88])
    fig.savefig(OUT_DIR / "result1_retry_budget_mpl64_p09.png", bbox_inches="tight", facecolor="white")
    fig.savefig(OUT_DIR / "result1_retry_budget_mpl64_p09.pdf", bbox_inches="tight", facecolor="white")
    fig.savefig(OUT_DIR / "result1_retry_budget_mpl64_p09_95ci.png", bbox_inches="tight", facecolor="white")
    fig.savefig(OUT_DIR / "result1_retry_budget_mpl64_p09_95ci.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_mpl_effect(df: pd.DataFrame) -> None:
    filtered = df[
        (df["hotspot_probability"].round(6) == 0.9) & (df["retry_model"] == "bounded_3")
    ].copy()
    tps = summarize(filtered, ["policy", "mpl"], "tps")
    err = summarize(filtered, ["policy", "mpl"], "error_rate_pct")
    xs = [1, 8, 32, 64]

    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.8), dpi=220)
    fig.patch.set_facecolor("white")

    for ax, data, ylabel, title, ylim in [
        (axes[0], tps, "Committed TPS", "Successful transactions per second", None),
        (axes[1], err, "Failed user requests (%)", "Requests that ran out of retries", (-0.3, 8.5)),
    ]:
        for policy in POLICIES:
            values = data[data["policy"] == policy].set_index("mpl").reindex(xs)
            ax.errorbar(
                xs,
                values["mean"],
                yerr=values["ci95"].fillna(0),
                label=POLICY_LABELS[policy],
                color=COLORS[policy],
                marker=MARKERS[policy],
                linewidth=2.0,
                markersize=5.5,
                capsize=3.5,
            )
        ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
        ax.set_xlabel("MPL (concurrent clients)", fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_xticks(xs)
        ax.set_xticklabels(["1", "8", "32", "64"])
        if ylim is not None:
            ax.set_ylim(*ylim)
        style_axis(ax)

    axes[0].legend(frameon=False, loc="best", fontsize=9)
    fig.suptitle(
        "More concurrent users make bounded retry failures visible",
        fontsize=18,
        fontweight="bold",
        x=0.03,
        ha="left",
    )
    fig.text(
        0.03,
        0.92,
        "SmallBank, hotspot probability = 0.9, retry budget = 3; points are means, whiskers are 95% CIs over 5 repeats.",
        fontsize=10,
        color="#333333",
        ha="left",
    )
    fig.text(
        0.03,
        0.02,
        "Takeaway: with one client almost nothing fails; as more clients run at once, bounded retries start to run out.",
        fontsize=10,
        color="#333333",
        ha="left",
    )
    fig.tight_layout(rect=[0.02, 0.07, 0.98, 0.88])
    fig.savefig(OUT_DIR / "result2_mpl_effect_p09_n3.png", bbox_inches="tight", facecolor="white")
    fig.savefig(OUT_DIR / "result2_mpl_effect_p09_n3.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(CSV_PATH)
    plot_retry_budget(df)
    plot_mpl_effect(df)
    print((OUT_DIR / "result1_retry_budget_mpl64_p09.png").resolve())
    print((OUT_DIR / "result2_mpl_effect_p09_n3.png").resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
