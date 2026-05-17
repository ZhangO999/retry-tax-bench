# Retry Tax SmallBank Experiment

This directory contains the executable experiment harness for measuring bounded
retry behavior on PostgreSQL SmallBank.

The harness is intentionally separate from the older `research_files/dbbench`
scripts. dbbench is useful background, but this experiment needs two features
that are easier to make explicit in Python:

- per-transaction isolation allocation for `mixed_robust`
- bounded retry, where `bounded_10` means one initial attempt plus ten retries

## Layout

```text
experiment/
  config/experiment_matrix.json    full v7 960-run matrix and DB config
  config/policies.json             RC, SI, SSI, mixed_robust allocations
  sql/schema.sql                   PostgreSQL schema
  smallbank/                       loader, sampler, policies, transactions
  harness.py                       one experimental cell
  run_matrix.py                    smoke/full matrix orchestration
  aggregate_results.py             mean and 95% CI summary
  plot_results.py                  PNG figures
  validate_results.py              raw result sanity checks
```

## Install

From the repository root:

```bash
python3 -m pip install -r experiment/requirements.txt
```

The default DB config expects local PostgreSQL with user/database `oliverzhang`.
Edit `experiment/config/experiment_matrix.json` if your local database differs.

## SmallBank Alignment

The schema and no-promotion transaction programs are aligned with the
Vandevoort artifact:

- tables: `Account`, `Savings`, `Checking`
- columns: `name`, `CustomerID`, `Balance`
- programs: `Balance`, `DepositChecking`, `TransactSavings`, `Amalgamate`, `WriteCheck`

One deliberate compromise remains: the artifact initializes account balances
randomly, while this harness uses deterministic configured initial balances.
That keeps every run reset to the same starting state for the retry-budget
matrix.

## Smoke Tests

Run a single tiny cell:

```bash
python3 experiment/harness.py --smoke
```

Run a three-cell smoke matrix:

```bash
python3 experiment/run_matrix.py --smoke --warmup-seconds 1 --measurement-seconds 2 \
  --raw-dir results/v7_smoke/raw \
  --summary-csv results/v7_smoke/run_summaries.csv
python3 experiment/validate_results.py results/v7_smoke/raw
```

These commands reset and reload the SmallBank database before each measured
cell. The smoke outputs live under `results/v7_smoke/`.

## Full Experiment

The full matrix is:

```text
4 policies x 4 MPL levels x 4 retry models x 3 hotspot probabilities x 5 repeats = 960 runs
```

Run it from the repository root:

```bash
scripts/run_v7_full.sh
```

This wrapper starts a `tmux` session when available, runs the matrix with
`--resume` under `caffeinate`, then validates, aggregates, and plots if the
matrix exits cleanly. Re-running the same script resumes from
`results/v7/summary/run_summaries.csv`.

The equivalent manual commands are:

```bash
python3 experiment/run_matrix.py --resume
python3 experiment/validate_results.py results/v7/raw
python3 experiment/aggregate_results.py
python3 experiment/plot_results.py
```

Expected outputs:

```text
results/v7/raw/*.json
results/v7/summary/run_summaries.csv
results/v7/summary/aggregate.csv
results/v7/figures/*.png
```

## Metrics

- `committed_tps`: committed transactions per measurement second
- `observed_tps`: committed plus user-visible failed transactions per second
- `attempted_tps`: total transaction attempts per measurement second
- `error_rate_pct`: visible failures divided by committed plus visible failures
- `abort_rate_pct`: aborted attempts divided by total attempts

Latency percentiles are computed from a capped per-worker sample to keep memory
bounded during high-throughput runs. TPS and error/abort rates use exact counts.

## Notes

The validation script checks row counts and result consistency. It records
pre/post fund totals, but it does not treat total-fund changes as anomalies:
DepositChecking, TransactSavings, and WriteCheck intentionally alter balances.
