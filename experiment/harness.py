from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import queue
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from multiprocessing import Barrier, Process, Queue
from pathlib import Path
from time import monotonic
from typing import Any

from smallbank import db
from smallbank.policies import TRANSACTIONS, load_policies
from smallbank.sampler import Sampler, SmallBankConfig, config_from_dict
from smallbank.transactions import TransactionOutcome, run_with_retry


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config" / "experiment_matrix.json"
DEFAULT_POLICIES = ROOT / "config" / "policies.json"
DEFAULT_SCHEMA = ROOT / "sql" / "schema.sql"


@dataclass
class WorkerStats:
    committed: int = 0
    errors: int = 0
    attempts: int = 0
    aborts: int = 0
    latency_sum: float = 0.0
    latency_min: float | None = None
    latency_max: float | None = None
    latency_samples: list[float] = field(default_factory=list)
    abort_reasons: dict[str, int] = field(default_factory=dict)
    by_transaction: dict[str, dict[str, int]] = field(default_factory=dict)
    by_isolation: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, outcome: TransactionOutcome, sample_limit: int) -> None:
        if outcome.committed:
            self.committed += 1
        else:
            self.errors += 1
        self.attempts += outcome.attempts
        self.aborts += outcome.aborts
        self.latency_sum += outcome.latency_seconds
        self.latency_min = outcome.latency_seconds if self.latency_min is None else min(self.latency_min, outcome.latency_seconds)
        self.latency_max = outcome.latency_seconds if self.latency_max is None else max(self.latency_max, outcome.latency_seconds)
        if len(self.latency_samples) < sample_limit:
            self.latency_samples.append(outcome.latency_seconds)
        for reason, count in outcome.abort_reasons.items():
            self.abort_reasons[reason] = self.abort_reasons.get(reason, 0) + count
        _record_group(self.by_transaction, outcome.name, outcome)
        _record_group(self.by_isolation, outcome.isolation, outcome)

    def to_dict(self) -> dict[str, Any]:
        return {
            "committed": self.committed,
            "errors": self.errors,
            "attempts": self.attempts,
            "aborts": self.aborts,
            "latency_sum": self.latency_sum,
            "latency_min": self.latency_min,
            "latency_max": self.latency_max,
            "latency_samples": self.latency_samples,
            "abort_reasons": self.abort_reasons,
            "by_transaction": self.by_transaction,
            "by_isolation": self.by_isolation,
        }


def _record_group(groups: dict[str, dict[str, int]], key: str, outcome: TransactionOutcome) -> None:
    if key not in groups:
        groups[key] = {"committed": 0, "errors": 0, "attempts": 0, "aborts": 0}
    group = groups[key]
    if outcome.committed:
        group["committed"] += 1
    else:
        group["errors"] += 1
    group["attempts"] += outcome.attempts
    group["aborts"] += outcome.aborts


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def retry_limit_from_model(model: str) -> int | None:
    if model == "unbounded":
        return None
    if model.startswith("bounded_"):
        return int(model.split("_", 1)[1])
    raise ValueError(f"Unknown retry model: {model}")


def worker_main(
    db_config: dict[str, Any],
    smallbank_config: dict[str, Any],
    policy: dict[str, str],
    retry_limit: int | None,
    warmup_seconds: float,
    measurement_seconds: float,
    seed: int,
    worker_id: int,
    barrier: Barrier,
    out_queue: Queue,
    sample_limit: int,
) -> None:
    conn = db.connect(db_config)
    try:
        sampler = Sampler(config_from_dict(smallbank_config), seed + worker_id)
        barrier.wait()
        warmup_until = monotonic() + warmup_seconds
        while monotonic() < warmup_until:
            run_with_retry(conn, sampler, policy, retry_limit)

        stats = WorkerStats()
        measure_until = monotonic() + measurement_seconds
        while monotonic() < measure_until:
            outcome = run_with_retry(conn, sampler, policy, retry_limit)
            stats.record(outcome, sample_limit)

        out_queue.put({"worker_id": worker_id, "ok": True, "stats": stats.to_dict()})
    except Exception as exc:
        out_queue.put({"worker_id": worker_id, "ok": False, "error": repr(exc)})
    finally:
        conn.close()


def merge_worker_stats(worker_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    merged = WorkerStats()
    latency_samples: list[float] = []
    for payload in worker_payloads:
        stats = payload["stats"]
        merged.committed += stats["committed"]
        merged.errors += stats["errors"]
        merged.attempts += stats["attempts"]
        merged.aborts += stats["aborts"]
        merged.latency_sum += stats["latency_sum"]
        if stats["latency_min"] is not None:
            merged.latency_min = stats["latency_min"] if merged.latency_min is None else min(merged.latency_min, stats["latency_min"])
        if stats["latency_max"] is not None:
            merged.latency_max = stats["latency_max"] if merged.latency_max is None else max(merged.latency_max, stats["latency_max"])
        latency_samples.extend(stats["latency_samples"])
        _merge_counter(merged.abort_reasons, stats["abort_reasons"])
        _merge_group(merged.by_transaction, stats["by_transaction"])
        _merge_group(merged.by_isolation, stats["by_isolation"])

    merged_dict = merged.to_dict()
    merged_dict["latency_samples"] = latency_samples
    return merged_dict


def _merge_counter(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + int(value)


def _merge_group(target: dict[str, dict[str, int]], source: dict[str, dict[str, int]]) -> None:
    for key, values in source.items():
        if key not in target:
            target[key] = {"committed": 0, "errors": 0, "attempts": 0, "aborts": 0}
        for metric, value in values.items():
            target[key][metric] = target[key].get(metric, 0) + int(value)


def latency_summary(samples: list[float], total_count: int, latency_sum: float) -> dict[str, float | int | None]:
    if total_count == 0:
        return {"count": 0, "mean_ms": None, "p50_ms": None, "p95_ms": None}
    sorted_samples = sorted(samples)
    return {
        "count": total_count,
        "mean_ms": 1000.0 * latency_sum / total_count,
        "p50_ms": 1000.0 * percentile(sorted_samples, 0.50) if sorted_samples else None,
        "p95_ms": 1000.0 * percentile(sorted_samples, 0.95) if sorted_samples else None,
    }


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires at least one value")
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = q * (len(sorted_values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    config = read_json(Path(args.config))
    policies = load_policies(Path(args.policies))
    policy = policies[args.policy]
    retry_limit = retry_limit_from_model(args.retry_model)
    smallbank_config = dict(config["smallbank"])
    if args.hotspot_probability is not None:
        smallbank_config["hotspot_probability"] = args.hotspot_probability
    db_config = dict(config["db"])
    seed = int(args.seed if args.seed is not None else config.get("seed", 3991))

    warmup_seconds = float(args.warmup_seconds if args.warmup_seconds is not None else config["timing"]["warmup_seconds"])
    measurement_seconds = float(args.measurement_seconds if args.measurement_seconds is not None else config["timing"]["measurement_seconds"])

    pre_snapshot = None
    if not args.no_reset_db:
        pre_snapshot = db.initialize_database(db_config, config_from_dict(smallbank_config), Path(args.schema))
    else:
        conn = db.connect(db_config)
        try:
            pre_snapshot = db.sanity_snapshot(conn)
        finally:
            conn.close()

    barrier = Barrier(args.mpl)
    out_queue: Queue = Queue()
    processes = []
    start = monotonic()
    for worker_id in range(args.mpl):
        process = Process(
            target=worker_main,
            args=(
                db_config,
                smallbank_config,
                policy,
                retry_limit,
                warmup_seconds,
                measurement_seconds,
                seed,
                worker_id,
                barrier,
                out_queue,
                args.latency_sample_limit,
            ),
        )
        process.start()
        processes.append(process)

    worker_payloads = []
    while any(process.is_alive() for process in processes):
        try:
            worker_payloads.append(out_queue.get(timeout=0.2))
        except queue.Empty:
            pass

    for process in processes:
        process.join()
    elapsed = monotonic() - start

    while True:
        try:
            worker_payloads.append(out_queue.get_nowait())
        except queue.Empty:
            break

    failures = [payload for payload in worker_payloads if not payload.get("ok")]
    if failures:
        raise RuntimeError(f"Worker failure(s): {failures}")
    if len(worker_payloads) != args.mpl:
        raise RuntimeError(f"Expected {args.mpl} worker results, got {len(worker_payloads)}")

    merged = merge_worker_stats(worker_payloads)
    total_observed = merged["committed"] + merged["errors"]
    post_conn = db.connect(db_config)
    try:
        post_snapshot = db.sanity_snapshot(post_conn)
    finally:
        post_conn.close()

    result = {
        "metadata": {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "host": platform.node(),
            "python": platform.python_version(),
            "policy": args.policy,
            "allocation": policy,
            "retry_model": args.retry_model,
            "retry_limit": retry_limit,
            "hotspot_probability": float(smallbank_config["hotspot_probability"]),
            "mpl": args.mpl,
            "repeat": args.repeat,
            "seed": seed,
            "warmup_seconds": warmup_seconds,
            "measurement_seconds": measurement_seconds,
            "elapsed_wall_seconds": elapsed,
        },
        "smallbank": smallbank_config,
        "pre_snapshot": pre_snapshot,
        "post_snapshot": post_snapshot,
        "metrics": {
            "committed": merged["committed"],
            "errors": merged["errors"],
            "attempts": merged["attempts"],
            "aborts": merged["aborts"],
            "committed_tps": merged["committed"] / measurement_seconds if measurement_seconds else 0.0,
            "observed_tps": total_observed / measurement_seconds if measurement_seconds else 0.0,
            "attempted_tps": merged["attempts"] / measurement_seconds if measurement_seconds else 0.0,
            "error_rate_pct": 100.0 * merged["errors"] / total_observed if total_observed else 0.0,
            "abort_rate_pct": 100.0 * merged["aborts"] / merged["attempts"] if merged["attempts"] else 0.0,
            "latency": latency_summary(merged["latency_samples"], total_observed, merged["latency_sum"]),
            "latency_min_ms": 1000.0 * merged["latency_min"] if merged["latency_min"] is not None else None,
            "latency_max_ms": 1000.0 * merged["latency_max"] if merged["latency_max"] is not None else None,
            "abort_reasons": merged["abort_reasons"],
            "by_transaction": merged["by_transaction"],
            "by_isolation": merged["by_isolation"],
        },
        "validation": validate_run(smallbank_config, pre_snapshot, post_snapshot),
    }
    write_outputs(result, config, args)
    return result


def validate_run(smallbank_config: dict[str, Any], pre_snapshot: dict[str, int], post_snapshot: dict[str, int]) -> dict[str, Any]:
    expected_count = int(smallbank_config["account_count"])
    checks = {
        "account_count_ok": post_snapshot["account_count"] == expected_count,
        "savings_count_ok": post_snapshot["savings_count"] == expected_count,
        "checking_count_ok": post_snapshot["checking_count"] == expected_count,
        "pre_total_funds": pre_snapshot["total_funds"],
        "post_total_funds": post_snapshot["total_funds"],
        "total_funds_delta": post_snapshot["total_funds"] - pre_snapshot["total_funds"],
    }
    checks["ok"] = checks["account_count_ok"] and checks["savings_count_ok"] and checks["checking_count_ok"]
    return checks


def write_outputs(result: dict[str, Any], config: dict[str, Any], args: argparse.Namespace) -> None:
    output = config["output"]
    raw_dir = Path(args.raw_dir or output["raw_dir"])
    summary_csv = Path(args.summary_csv or output["summary_csv"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    summary_csv.parent.mkdir(parents=True, exist_ok=True)

    meta = result["metadata"]
    filename = (
        f"{meta['timestamp_utc'].replace(':', '').replace('-', '')}_"
        f"{meta['policy']}_mpl{meta['mpl']}_{meta['retry_model']}_"
        f"p{format_probability(meta['hotspot_probability'])}_r{meta['repeat']}.json"
    )
    raw_path = raw_dir / filename
    result["metadata"]["raw_path"] = str(raw_path)
    raw_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    append_summary_csv(summary_csv, result)


def append_summary_csv(path: Path, result: dict[str, Any]) -> None:
    fieldnames = [
        "timestamp_utc",
        "policy",
        "retry_model",
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
        "committed_tps",
        "tps",
        "observed_tps",
        "attempted_tps",
        "error_rate_pct",
        "error_rate",
        "abort_rate_pct",
        "abort_rate",
        "latency_mean_ms",
        "mean_latency_ms",
        "latency_p50_ms",
        "latency_p95_ms",
        "p95_latency_ms",
        "validation_ok",
        "post_total_funds",
        "raw_path",
    ]
    meta = result["metadata"]
    metrics = result["metrics"]
    retry_budget = "inf" if meta["retry_model"] == "unbounded" else meta["retry_model"].replace("bounded_", "")
    hotspot_probability = f"{meta['hotspot_probability']:.6f}"
    committed_tps = f"{metrics['committed_tps']:.6f}"
    error_rate = f"{metrics['error_rate_pct']:.6f}"
    abort_rate = f"{metrics['abort_rate_pct']:.6f}"
    latency_mean = _fmt(metrics["latency"]["mean_ms"])
    latency_p95 = _fmt(metrics["latency"]["p95_ms"])
    row = {
        "timestamp_utc": meta["timestamp_utc"],
        "policy": meta["policy"],
        "retry_model": meta["retry_model"],
        "retry_budget": retry_budget,
        "hotspot_probability": hotspot_probability,
        "hotspot_p": hotspot_probability,
        "mpl": meta["mpl"],
        "repeat": meta["repeat"],
        "seed": meta["seed"],
        "warmup_seconds": meta["warmup_seconds"],
        "measurement_seconds": meta["measurement_seconds"],
        "committed": metrics["committed"],
        "errors": metrics["errors"],
        "attempts": metrics["attempts"],
        "aborts": metrics["aborts"],
        "committed_tps": committed_tps,
        "tps": committed_tps,
        "observed_tps": f"{metrics['observed_tps']:.6f}",
        "attempted_tps": f"{metrics['attempted_tps']:.6f}",
        "error_rate_pct": error_rate,
        "error_rate": error_rate,
        "abort_rate_pct": abort_rate,
        "abort_rate": abort_rate,
        "latency_mean_ms": latency_mean,
        "mean_latency_ms": latency_mean,
        "latency_p50_ms": _fmt(metrics["latency"]["p50_ms"]),
        "latency_p95_ms": latency_p95,
        "p95_latency_ms": latency_p95,
        "validation_ok": result["validation"]["ok"],
        "post_total_funds": result["post_snapshot"]["total_funds"],
        "raw_path": meta["raw_path"],
    }
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def format_probability(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one PostgreSQL SmallBank retry-tax experiment cell.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--policies", default=str(DEFAULT_POLICIES))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--policy", choices=["rc", "si", "ssi", "mixed_robust"], default="rc")
    parser.add_argument("--retry-model", default="bounded_3")
    parser.add_argument("--hotspot-probability", type=float)
    parser.add_argument("--mpl", type=int, default=1)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--warmup-seconds", type=float)
    parser.add_argument("--measurement-seconds", type=float)
    parser.add_argument("--raw-dir")
    parser.add_argument("--summary-csv")
    parser.add_argument("--latency-sample-limit", type=int, default=1000)
    parser.add_argument("--no-reset-db", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Shortcut for RC, MPL=1, bounded_3, 1s warmup, 2s measure.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.smoke:
        args.policy = "rc"
        args.retry_model = "bounded_1"
        args.hotspot_probability = 0.5
        args.mpl = 1
        args.repeat = 0
        args.warmup_seconds = 1.0
        args.measurement_seconds = 2.0
        args.raw_dir = args.raw_dir or "results/v7_smoke/raw"
        args.summary_csv = args.summary_csv or "results/v7_smoke/run_summaries.csv"
    result = run_once(args)
    metrics = result["metrics"]
    print(
        f"{result['metadata']['policy']} mpl={result['metadata']['mpl']} "
        f"p={result['metadata']['hotspot_probability']:.1f} "
        f"{result['metadata']['retry_model']}: "
        f"committed={metrics['committed']} errors={metrics['errors']} "
        f"tps={metrics['committed_tps']:.2f} abort_rate={metrics['abort_rate_pct']:.2f}%"
    )
    print(f"validation_ok={result['validation']['ok']} raw={result['metadata']['raw_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
