#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_PATH="$PROJECT_ROOT/scripts/run_v7_full.sh"
SESSION_NAME="retry-tax-v7"
USE_TMUX=1
INSIDE_TMUX=0
SKIP_INSTALL=0
SKIP_POSTPROCESS=0
CLAMSHELL_MODE=0

usage() {
  cat <<'EOF'
Usage:
  scripts/run_v7_full.sh [options]

Options:
  --no-tmux            Run in the current terminal instead of starting tmux.
  --session NAME       tmux session name. Default: retry-tax-v7.
  --skip-install       Do not run pip install for experiment/requirements.txt.
  --skip-postprocess   Do not validate, aggregate, or plot after the matrix run.
  --clamshell          Prepare for macOS closed-lid/clamshell use. Requires AC power
                       and still requires a real external display/input setup.
  -h, --help           Show this help.

What this script does:
  1. Starts a tmux session, unless already inside tmux or --no-tmux is used.
  2. Checks PostgreSQL is reachable.
  3. Installs Python requirements unless --skip-install is used.
  4. Runs the full v7 matrix with --resume under caffeinate.
  5. Validates, aggregates, and plots results if the matrix completes.

Recovery:
  Re-run this exact script after a crash/interruption. The matrix runner uses
  results/v7/summary/run_summaries.csv to skip completed cells.

Closed-lid note:
  caffeinate does not reliably override MacBook lid-close sleep by itself.
  Closed-lid running generally requires clamshell mode: power connected,
  external display connected, and external keyboard/mouse/trackpad available.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --inside-tmux)
      INSIDE_TMUX=1
      shift
      ;;
    --no-tmux)
      USE_TMUX=0
      shift
      ;;
    --session)
      SESSION_NAME="${2:?missing value for --session}"
      shift 2
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    --skip-postprocess)
      SKIP_POSTPROCESS=1
      shift
      ;;
    --clamshell)
      CLAMSHELL_MODE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

shell_quote() {
  printf "%q" "$1"
}

start_tmux_if_needed() {
  if [[ "$USE_TMUX" -ne 1 || "$INSIDE_TMUX" -eq 1 || -n "${TMUX:-}" ]]; then
    return
  fi

  if ! command -v tmux >/dev/null 2>&1; then
    echo "tmux is not installed. Install it with: brew install tmux"
    echo "Or run without tmux: scripts/run_v7_full.sh --no-tmux"
    exit 1
  fi

  if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "tmux session '$SESSION_NAME' already exists."
    echo "Attach with: tmux attach -t $SESSION_NAME"
    exit 0
  fi

  child_args=("$SCRIPT_PATH" "--inside-tmux" "--session" "$SESSION_NAME")
  if [[ "$SKIP_INSTALL" -eq 1 ]]; then
    child_args+=("--skip-install")
  fi
  if [[ "$SKIP_POSTPROCESS" -eq 1 ]]; then
    child_args+=("--skip-postprocess")
  fi
  if [[ "$CLAMSHELL_MODE" -eq 1 ]]; then
    child_args+=("--clamshell")
  fi

  quoted_project_root="$(shell_quote "$PROJECT_ROOT")"
  quoted_child_args=""
  for arg in "${child_args[@]}"; do
    quoted_child_args+="$(shell_quote "$arg") "
  done

  tmux new-session -d -s "$SESSION_NAME" "cd $quoted_project_root && $quoted_child_args"
  echo "Started full v7 experiment in tmux session '$SESSION_NAME'."
  echo "Attach:  tmux attach -t $SESSION_NAME"
  echo "Detach:  Ctrl-b then d"
  echo "Logs:    $PROJECT_ROOT/logs/"
  exit 0
}

setup_logging() {
  mkdir -p "$PROJECT_ROOT/logs"
  LOG_FILE="$PROJECT_ROOT/logs/v7_full_$(date '+%Y%m%d_%H%M%S').log"
  exec > >(tee -a "$LOG_FILE") 2>&1
}

on_exit() {
  status=$?
  if [[ "$status" -eq 0 ]]; then
    echo
    echo "[done] v7 runner completed successfully."
  else
    echo
    echo "[stopped] v7 runner exited with status $status."
    echo "Re-run scripts/run_v7_full.sh to resume completed-cell skipping."
  fi
}

preflight() {
  cd "$PROJECT_ROOT"
  echo "[info] project: $PROJECT_ROOT"
  echo "[info] started: $(date)"
  echo "[info] host: $(hostname)"
  echo "[info] tmux session: ${TMUX:-not inside tmux}"
  echo
  echo "[note] caffeinate prevents idle sleep while this command is running."
  if [[ "$CLAMSHELL_MODE" -eq 1 ]]; then
    echo "[note] --clamshell requested. This only works if macOS enters real clamshell mode."
    echo "[note] Required: AC power, external display, and external keyboard/mouse/trackpad."
  else
    echo "[note] Default safest setup: plugged in, lid open, Energy settings allowing long runs."
    echo "[note] To intentionally use closed-lid clamshell mode, restart with --clamshell."
  fi
  echo

  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found." >&2
    exit 1
  fi
  if ! command -v psql >/dev/null 2>&1; then
    echo "psql not found. PostgreSQL client tools are required." >&2
    exit 1
  fi
  if ! pg_isready; then
    echo "PostgreSQL is not ready. Start PostgreSQL, then re-run this script." >&2
    exit 1
  fi

  if [[ "$CLAMSHELL_MODE" -eq 1 ]]; then
    if ! pmset -g batt | grep -q "AC Power"; then
      echo "--clamshell requires AC power, but this Mac appears to be on battery." >&2
      echo "Plug in power, then re-run the script." >&2
      exit 1
    fi
    echo "[info] AC power detected for clamshell mode."
    echo "[warn] This script cannot force macOS to ignore the lid sensor."
    echo "[warn] Before closing the lid, confirm the external monitor stays active after attach."
  fi

  echo "[info] $(python3 --version)"
  echo "[info] $(psql --version)"
  if ! psql --version | grep -q "16\\.2"; then
    echo "[warn] research_plan_v7 targets PostgreSQL 16.2; this machine reports a different version."
    echo "[warn] You can still run, but document the PostgreSQL version as a limitation."
  fi
  echo

  if [[ "$SKIP_INSTALL" -ne 1 ]]; then
    echo "[step] installing/checking Python requirements"
    python3 -m pip install -r experiment/requirements.txt
    echo
  fi

  echo "[step] confirming full v7 matrix shape"
  python3 experiment/run_matrix.py --dry-run --resume | sed -n '1,5p'
  echo
}

run_matrix() {
  echo "[step] starting/resuming full v7 matrix"
  if command -v caffeinate >/dev/null 2>&1; then
    caffeinate -dimsu python3 experiment/run_matrix.py --resume
  else
    echo "[warn] caffeinate not found; running without macOS sleep prevention."
    python3 experiment/run_matrix.py --resume
  fi
  echo
}

postprocess() {
  if [[ "$SKIP_POSTPROCESS" -eq 1 ]]; then
    echo "[skip] postprocessing skipped by --skip-postprocess"
    return
  fi

  echo "[step] validating raw v7 outputs"
  python3 experiment/validate_results.py results/v7/raw
  echo

  echo "[step] aggregating v7 summaries"
  python3 experiment/aggregate_results.py
  echo

  echo "[step] plotting v7 figures"
  python3 experiment/plot_results.py
  echo

  echo "[info] outputs:"
  echo "  results/v7/raw/"
  echo "  results/v7/summary/run_summaries.csv"
  echo "  results/v7/summary/aggregate.csv"
  echo "  results/v7/figures/"
}

start_tmux_if_needed
setup_logging
trap on_exit EXIT
preflight
run_matrix
postprocess
