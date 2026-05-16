# Retry Tax Bench

Standalone benchmark repo for the SmallBank bounded-retry experiment from the
SCDL3991 research project.

The main implementation lives in [experiment/README.md](experiment/README.md).

## Quick Start

```bash
python3 -m pip install -r experiment/requirements.txt
python3 experiment/harness.py --smoke
```

## Full v7 Run

The v7 matrix is 960 runs:

```text
4 policies x 4 MPL levels x 4 retry models x 3 hotspot probabilities x 5 repeats
```

Start it with resume enabled:

```bash
scripts/run_v7_full.sh
```

The script starts a `tmux` session, uses `caffeinate`, writes logs under
`logs/`, runs the matrix with `--resume`, then validates, aggregates, and plots
the outputs. If the run is interrupted, run the same command again.

For intentional closed-lid use, use clamshell mode:

```bash
scripts/run_v7_full.sh --clamshell
```

This checks that AC power is connected, but macOS still requires a real
clamshell setup: external display plus external keyboard/mouse/trackpad. Plain
`caffeinate` cannot reliably keep a MacBook awake after closing the lid by
itself.

Then validate, aggregate, and plot:

```bash
python3 experiment/validate_results.py results/v7/raw
python3 experiment/aggregate_results.py
python3 experiment/plot_results.py
```

## Figure-Quality Pilot

Before spending many hours on the full matrix, run the 216-cell pilot:

```bash
python3 experiment/run_matrix.py --pilot --resume
python3 experiment/validate_results.py results/pilot/raw
python3 experiment/plot_pilot_results.py --input results/pilot_results.csv --figures-dir figures/pilot
```

The pilot uses:

```text
4 policies x 3 MPL levels x 3 retry models x 3 hotspot probabilities x 2 repeats
```

with 5s warmup and 15s measurement by default. It writes run summaries to
`results/pilot_results.csv`, raw JSON files to `results/pilot/raw`, and the
requested pilot figures to `figures/pilot`.

## Micro-Pilot

For a minutes-scale harness and plotting check, run:

```bash
python3 experiment/run_matrix.py --micro-pilot
python3 experiment/validate_results.py results/micro_pilot/raw
python3 experiment/plot_micro_pilot_results.py --input results/micro_pilot_results.csv --figures-dir figures/micro_pilot
```

The micro-pilot is 36 runs:

```text
4 policies x MPL 32 x 3 retry models x 3 hotspot probabilities x 1 repeat
```

with 2s warmup and 6s measurement by default. It writes
`results/micro_pilot_results.csv`, raw JSON files to `results/micro_pilot/raw`,
and figures to `figures/micro_pilot`.

## Repository Layout

```text
experiment/     benchmark harness, config, SQL, analysis scripts
results/smoke/  smoke-test outputs generated during development
results/v7/     full v7 outputs, ignored by Git
```
