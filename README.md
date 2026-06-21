# RetryTaxBench

**Measuring the hidden cost of retries in a database under load.**

RetryTaxBench is a benchmarking tool for PostgreSQL that answers a practical
question most database studies skip: *what happens when you can't keep retrying a
failed transaction forever?*

📄 **[Read the full report (PDF)](report/RetryTaxBench.pdf)** —
*RetryTaxBench: Evaluating Isolation-Level Trade-offs under Bounded Retry on PostgreSQL.*

---

## The idea in plain language

When two people touch the same data at the same time — say, two transfers from
the same bank account — a database has to decide how careful to be. That setting
is called an **isolation level**. Stronger levels are safer but slower; weaker
levels are faster but can corrupt data. A popular strategy is to mix them: give
each kind of transaction the weakest (fastest) level that still keeps the whole
workload correct.

The catch: these strategies are almost always tested by assuming a failed
transaction just *retries until it eventually succeeds*. Real systems can't do
that. A transaction that charges a credit card, or a user who won't wait, puts a
hard limit on retries.

This project adds that missing limit — a **retry budget** — and measures what it
costs. The headline finding is what we call the **retry tax**: even when every
request eventually succeeds, under heavy load the database quietly throws away and
re-runs **33–44% of its attempts**. That wasted work is invisible to studies that
assume unlimited retries, but it's very real for the people paying for the
servers.

## What we found

Across **960 experiment configurations** (four isolation policies × four
concurrency levels × four retry budgets × three contention levels × five repeats):

- **The retry tax is large and persistent.** Under heavy contention, 33–44% of
  database attempts are aborted and retried, no matter how generous the retry
  budget — the wasted work doesn't go away, it just gets hidden.
- **Snapshot Isolation looks fast but fails more.** It aborts and produces
  user-visible errors more often than the stronger Serializable Snapshot
  Isolation (SSI).
- **The "mixed" strategy matches, but doesn't beat, SSI under load** — once
  retries are bounded, the advantage reported in earlier work shrinks.

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

This proves everything is wired up correctly — it loads the schema, runs one tiny
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

Prefer to drive each step yourself? The manual equivalent is:

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

## How it works

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

The core pieces:

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

## Credit

Built by **Oliver Zhang** for SCDL3991 (University of Sydney), supervised by
Alan Fekete. The benchmark extends the SmallBank setup of Vandevoort, Ketsman,
and Neven (2025). See the [full report](report/RetryTaxBench.pdf) for references
and methodology.
