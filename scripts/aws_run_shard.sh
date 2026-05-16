#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: bash scripts/aws_run_shard.sh <shard_index> [shard_count]" >&2
  echo "Example for machine 0 of 8: bash scripts/aws_run_shard.sh 0 8" >&2
  exit 2
fi

SHARD_INDEX="$1"
SHARD_COUNT="${2:-8}"
SESSION="retry-tax-aws-${SHARD_INDEX}-of-${SHARD_COUNT}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_DIR="results/aws_v7/shards/${SHARD_INDEX}/raw"
SUMMARY_CSV="results/aws_v7/shards/${SHARD_INDEX}/run_summaries.csv"
LOG_FILE="logs/aws_shard_${SHARD_INDEX}_of_${SHARD_COUNT}.log"

mkdir -p "$REPO_DIR/logs" "$REPO_DIR/results/aws_v7/shards/${SHARD_INDEX}" "$REPO_DIR/results/aws_v7/summary"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session '$SESSION' already exists."
  echo "Attach: tmux attach -t $SESSION"
  exit 0
fi

COMMAND=$(cat <<EOF
cd "$REPO_DIR"
python3 experiment/run_matrix.py \
  --resume \
  --config experiment/config/aws_experiment_matrix.json \
  --shard-index "$SHARD_INDEX" \
  --shard-count "$SHARD_COUNT" \
  --raw-dir "$RAW_DIR" \
  --summary-csv "$SUMMARY_CSV" \
  2>&1 | tee -a "$LOG_FILE"
EOF
)

tmux new-session -d -s "$SESSION" "$COMMAND"

echo "Started AWS shard $SHARD_INDEX/$SHARD_COUNT in tmux session '$SESSION'."
echo "Attach:  tmux attach -t $SESSION"
echo "Detach:  Ctrl-b then d"
echo "Log:     $REPO_DIR/$LOG_FILE"
echo "Summary: $REPO_DIR/$SUMMARY_CSV"
