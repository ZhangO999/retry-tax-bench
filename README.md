# Retry Tax Bench

This repository contains the code and local outputs for the SmallBank retry-budget experiment.
The project extends Vandevoort et al. (2025) by keeping the SmallBank setup close to their artifact while measuring user-visible failures when retries are bounded.

The current snapshot is on branch `v7-experiment` and includes the harness, configuration, schema, helper scripts, the completed local `results/v7/` run, and slide-oriented analysis artifacts.

## What this project is for

The experiment measures how PostgreSQL isolation policies behave when aborted transactions are not retried indefinitely. The main goal is to compare:

- `rc` — READ COMMITTED baseline
- `si` — REPEATABLE READ / snapshot isolation baseline
- `ssi` — SERIALIZABLE baseline
- `mixed_robust` — Vandevoort-style mixed allocation with DepositChecking at RC and the rest at SSI

The key new variable is retry budget:

- `bounded_1` — one retry after the first failed attempt
- `bounded_3` — up to three retries
- `bounded_10` — up to ten retries
- `unbounded` — retry until commit

A full v7 matrix is:

```text
4 policies x 4 MPL values x 4 retry models x 3 hotspot probabilities x 5 repeats = 960 runs
```

## What to look at

### Core experiment files

- `experiment/harness.py`
  - Runs a single experimental cell.
  - Resets the database, executes transactions under the chosen policy, retry model, MPL, and hotspot probability, then writes raw JSON + summary CSV output.

- `experiment/run_matrix.py`
  - Orchestrates a full batch of runs.
  - Supports `--resume`, `--smoke`, `--pilot`, and `--micro-pilot`.
  - Useful for running the matrix in stages and recovering from interruption.

- `experiment/config/experiment_matrix.json`
  - Defines the v7 matrix, timing parameters, DB connection, and output locations.
  - This is the single source of the experiment parameters used by the full run.

- `experiment/config/policies.json`
  - Defines the policy allocations for `rc`, `si`, `ssi`, and `mixed_robust`.
  - This file controls which SmallBank program runs at which PostgreSQL isolation level.

- `experiment/sql/schema.sql`
  - Defines the SmallBank schema.
  - This matches the Vandevoort artifact: `Account`, `Savings`, `Checking`.

- `experiment/smallbank/`
  - Contains helper modules for loading the database, sampling accounts, and executing the five SmallBank transactions.
  - It also contains the per-policy and per-program isolation logic.

### Analysis and validation

- `experiment/validate_results.py`
  - Validates raw JSON output files.
  - Checks whether the metadata, metrics, and run invariants are consistent.

- `experiment/aggregate_results.py`
  - Aggregates run summaries into mean values and 95% confidence intervals.

- `experiment/plot_results.py`
  - Generates PNG figures from the aggregated results.

- `scripts/run_v7_full.sh`
  - Recommended local runner for the full matrix.
  - Uses `tmux`, `caffeinate`, `--resume`, and post-processing so the run can survive terminal disconnects and resume after interruptions.

- `scripts/export_slide_result1_data.py`, `scripts/plot_slide_results.py`, `scripts/slide_result_table.py`
  - Generate the slide-specific CSV, TeX, PNG, and PDF artifacts under `analysis/slide_results/` and `figures/slides/`.

- `AWS_RUNBOOK.md` and `scripts/aws_*`
  - Optional parallel AWS fallback path.
  - Treat AWS outputs as a separate dataset from the local Mac run unless explicitly merged by research decision.

### Current outputs and progress

- `results/v7/raw/`
  - Raw JSON output files for all 960 local v7 cells.
  - This directory records per-cell metrics, abort/error counts, latency, and validation state.

- `results/v7/summary/run_summaries.csv`
  - The CSV summary of completed cells.
  - This is the file `experiment/run_matrix.py --resume` uses to skip already finished runs.

- `analysis/slide_results/`
  - Compact derived CSV and TeX tables used for presentation slides.

- `figures/slides/`
  - Slide-ready PNG/PDF figures generated from `results/v7/summary/run_summaries.csv`.

- `logs/`
  - Local runtime logs are intentionally ignored by git.
  - Keep them locally for debugging, but regenerate or share selectively if needed.

## Quick start for reviewers

To inspect the current snapshot without running anything:

1. Read `experiment/README.md` for the detailed harness layout.
2. Open `experiment/config/experiment_matrix.json` to see the actual experimental values.
3. Open `experiment/config/policies.json` to verify the isolation allocation.
4. Review `results/v7/summary/run_summaries.csv` for the completed local matrix and `figures/slides/` for presentation-ready outputs.

## Run the smoke test

To validate the harness quickly:

```bash
python3 -m pip install -r experiment/requirements.txt
python3 experiment/harness.py --smoke
```

## Resume or restart the full matrix

If client crashes or halts, to rerun or continue the experiment, use:

```bash
scripts/run_v7_full.sh
```

The runner reads `results/v7/summary/run_summaries.csv` through `experiment/run_matrix.py --resume` and skips any cells that are already completed. That makes the run robust to interruptions.

## Notes for this snapshot

- This branch is a research snapshot and contains the completed local 960-cell v7 run.
- The experiment harness and configuration are the main deliverables for review.
- Generated figures/tables are included only when they are useful for review or slides; transient logs and editor metadata are ignored.

## Repository layout

```text
experiment/      main benchmark code, configs, SQL, and plotting scripts
results/         raw outputs and summaries from runs
analysis/        derived CSV/TEX tables for slide analysis
figures/         generated pilot and slide figures
scripts/         helper scripts used to launch, shard, merge, and plot
```
