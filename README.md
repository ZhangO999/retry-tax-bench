# RetryTaxBench

This repository contains the Python benchmarking program used to simulate the
SmallBank workload under a similar setup as specified in Vandevoort, Fekete et al. 2025.
It enforces a parameter **N** (which we henceforth call the **retry budget**) 
and empirically measures its effects on the performance of the *REPMILA* allocation algorithm. 

📄 **[Read the full report (PDF)](report/RetryTaxBench.pdf)** —
*RetryTaxBench: Evaluating Isolation-Level Trade-offs under Bounded Retry on PostgreSQL.*

---

## Introduction

A database can run transactions at different isolation levels: settings
that trade correctness for speed. Mixed-isolation schemes such as
REPMILA (Vandevoort et al. 2025) give each kind of transaction the
weakest and therefore fastest level that still keeps the workload
as a whole serializable, and have been shown to beat uniformly
strong Serializable Snapshot Isolation (SSI) on benchmarks such as
SmallBank (Alomari et al., 2008). These results, however, assume that an
aborted transaction simply retries until it eventually commits. Real 
systems rarely allow this: a transaction with outside effects
(such as charging a card), or a user unwilling to wait, limits how 
many times it can be retried. 

We introduce RetryTaxBench, a Python-based PostgreSQL benchmarking
tool that adds a configurable cap on retries to the SmallBank setup
of Vandevoort et al., and use it to measure how this cap changes the
trade-off between speed and reliability across Read Committed, Snapshot
Isolation, SSI, and a mixed allocation. 


## What we found

Across **960 experiment configurations** (four isolation policies × four
concurrency levels × four retry budgets × three contention levels × five repeats):

- **The retry tax is large and persistent.** Under heavy contention, 33–44% of
  database attempts are aborted and retried, no matter how generous the retry
  budget — the wasted work doesn't go away, it just gets hidden.
- **Snapshot Isolation looks fast but fails more.** It aborts and produces
  user-visible errors more often than the stronger Serializable Snapshot
  Isolation (SSI).
- **The "mixed" strategy (REPMILA + bounded retries) matches, but does not beat, SSI under load** — once
  retries are bounded, the advantage reported in earlier work shrinks.

The two tables and charts below show the headline numbers under the heaviest load
tested (64 concurrent transactions, 90% of them hitting a contended hotspot), as
the retry budget `N` grows from 1 to unbounded. All figures are generated directly
from the shipped data with [`experiment/plot_results.py`](experiment/plot_results.py).

### 1. Error rate — the failures users actually see

The share of requests that **never commit**, even after exhausting the retry
budget. This is the cost a strict retry cap imposes:

| Policy | N=1 | N=3 | N=10 | Unbounded |
|--------|----:|----:|-----:|----------:|
| Read Committed (`rc`)      |  0.00 | 0.00 | 0.00 | 0.00 |
| Snapshot Isolation (`si`)  | 16.54 | 7.35 | 1.15 | 0.00 |
| Serializable (`ssi`)       | 10.22 | 3.81 | 0.27 | 0.00 |
| Mixed (`mixed_robust`)     | 11.22 | 3.99 | 0.31 | 0.00 |

<sub>Error rate (%) at MPL = 64, hotspot p = 0.9, means of 5 runs.</sub>

![Error rate vs retry budget](results/main/figures/retry_sweep_error_rate_pct_p0p9_mpl64.png)

More retries drive user-visible failures toward zero — which is exactly why
retry-until-commit studies see no problem. Snapshot Isolation needs the most
retries to get there.

### 2. Abort rate — the retry tax

The share of **attempts the database silently rolls back and re-runs**. Unlike the
error rate, this *doesn't* fall as the retry budget grows — it stays high or even
climbs, because more retries simply means more discarded attempts:

| Policy | N=1 | N=3 | N=10 | Unbounded |
|--------|----:|----:|-----:|----------:|
| Read Committed (`rc`)      |  0.00 |  0.00 |  0.00 |  0.00 |
| Snapshot Isolation (`si`)  | 36.11 | 41.09 | 43.74 | 43.79 |
| Serializable (`ssi`)       | 27.62 | 33.03 | 35.03 | 35.50 |
| Mixed (`mixed_robust`)     | 27.54 | 31.33 | 33.41 | 33.48 |

<sub>Abort rate (%) at MPL = 64, hotspot p = 0.9, means of 5 runs.</sub>

![Abort rate vs retry budget](results/main/figures/retry_sweep_abort_rate_pct_p0p9_mpl64.png)

At unbounded retries — the point where the error rate is zero and everything
"looks fine" — the database is still throwing away **33–44% of its attempts**.
That is the retry tax made visible.

> **Why is Read Committed always 0%?** PostgreSQL's Read Committed level never
> raises serialization errors; it permits the weaker behaviour instead of
> aborting. It pays no retry tax precisely because it offers the least protection
> — a reminder that "zero aborts" is not the same as "correct".

## Repository layout

```text
report/        the final write-up (PDF)
experiment/    the benchmark itself — harness, configs, SQL, analysis scripts
results/main/  the raw data and summary from the full 960-run experiment
scripts/       helpers to launch the full run (local) or scale it out on AWS
AWS_RUNBOOK.md optional guide for running the experiment across EC2 machines
```

---

## Quick start

### 1. Prerequisites

- **Python 3.10+**
- **PostgreSQL 14+** running locally (the study used 16.2)

On macOS the easiest setup is Homebrew:

```bash
brew install python postgresql@16
brew services start postgresql@16
```

### 2. Clone and install

```bash
git clone https://github.com/ZhangO999/retry-tax-bench.git
cd retry-tax-bench
python3 -m pip install -r experiment/requirements.txt
```

### 3. Create the database

The benchmark loads and resets its own tables, so it just needs an empty
database to live in:

```bash
createdb retrytaxbench
```

The connection settings live in
[`experiment/config/experiment_matrix.json`](experiment/config/experiment_matrix.json)
under `"db"`. By default it connects to a local database named `retrytaxbench` as
your operating-system user. Edit that block if your host, port, username, or
password differ.

### 4. Run a 30-second smoke test

This confirms everything is wired up correctly — it loads the schema, runs one tiny
measured cell, and prints a result:

```bash
python3 experiment/harness.py --smoke
```

If that prints a JSON summary without errors, you're ready to run the real thing.

---

## Running the full experiment

The full matrix is **960 runs** and takes several hours. One command handles the
whole thing — installing dependencies, running every cell, and validating,
aggregating, and plotting the results:

```bash
scripts/run_full_experiment.sh
```

It runs inside a `tmux` session under `caffeinate` (so it survives a closed
laptop lid and terminal disconnects) and is **fully resumable** — if it's
interrupted, just run the same command again and it skips the cells already
finished. Run `scripts/run_full_experiment.sh --help` for options.

If you prefer to run each step yourself manually, the equivalent steps are:

```bash
python3 experiment/run_matrix.py --resume        # run/continue the 960-cell matrix
python3 experiment/validate_results.py           # sanity-check the raw outputs
python3 experiment/aggregate_results.py          # compute means + 95% confidence intervals
python3 experiment/plot_results.py               # render PNG figures
```

Outputs land in:

```text
results/main/raw/*.json                  one file per run, with full metrics
results/main/summary/run_summaries.csv   one row per run (used for --resume)
results/main/summary/aggregate.csv       means and 95% confidence intervals
results/main/figures/*.png               generated charts
```

> The repository already ships the **completed data** from the study under
> `results/main/`, so you can explore the findings without running anything.

---

## Method Summary: 

The experiment is a grid. Each **cell** is one combination of these knobs, run
for a fixed measurement window:

| Knob | What it means | Values |
|------|---------------|--------|
| **Policy** | Which isolation level each transaction type uses | `rc`, `si`, `ssi`, `mixed_robust` |
| **Retry budget** | How many times a failed transaction may retry | `bounded_1`, `bounded_3`, `bounded_10`, `unbounded` |
| **MPL** | Concurrency — how many transactions run at once | 1, 8, 32, 64 |
| **Contention** | How often transactions fight over the same rows (a "hotspot") | p = 0.1, 0.5, 0.9 |
| **Repeats** | Independent runs per cell, for confidence intervals | 5 |

The four policies are:

- **`rc`** — Read Committed (PostgreSQL's weakest default level)
- **`si`** — Repeatable Read / Snapshot Isolation
- **`ssi`** — Serializable (Serializable Snapshot Isolation, the strongest)
- **`mixed_robust`** — a mixed allocation in the style of Vandevoort et al.:
  the `DepositChecking` program runs at Read Committed, the rest at SSI

The workload is **SmallBank**, a standard banking benchmark (five transaction
types over `Account`, `Savings`, and `Checking` tables). The benchmark and schema
deliberately stay close to the artifact of **Vandevoort et al. (2025)** so the
bounded-retry results are comparable to their retry-until-commit ones.

Core pieces:

- [`experiment/harness.py`](experiment/harness.py) — runs **one** cell: resets the
  database, fires concurrent workers under the chosen policy and retry budget, and
  records throughput, error rate, abort rate, and latency.
- [`experiment/run_matrix.py`](experiment/run_matrix.py) — orchestrates the **full
  grid**, with `--resume` to skip completed cells.
- [`experiment/config/`](experiment/config/) — the experiment matrix, database
  connection, and per-policy isolation allocations (plain JSON you can edit).
- [`experiment/smallbank/`](experiment/smallbank/) — the database loader, account
  sampler, the five SmallBank transactions, and the per-policy isolation logic.

The key metrics it records:

- **Committed TPS** — successful transactions per second
- **Error rate** — share of requests that never commit (the user-visible failures)
- **Abort rate** — share of *attempts* the database rolls back and retries
  (this is where the retry tax shows up)

See [`experiment/README.md`](experiment/README.md) for the full harness reference.

---

## Scaling out on AWS (optional)

To run the matrix faster, [`AWS_RUNBOOK.md`](AWS_RUNBOOK.md) describes sharding it
across several EC2 instances and merging the results. This is entirely optional —
the local runner above produces the same dataset.

---

## Acknowledgements

This project was supervised by Professor Alan Fekete of the Database Research Group at the University of Sydney. 
The benchmark extends the SmallBank setup of Vandevoort, Ketsman,
and Neven (2025). See the [full report](report/RetryTaxBench.pdf) for references
and methodology.
