#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[step] installing OS packages"
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  git \
  htop \
  libpq-dev \
  postgresql \
  postgresql-client \
  python3 \
  python3-pip \
  python3-venv \
  rsync \
  tmux \
  unzip

echo "[step] starting PostgreSQL"
sudo systemctl enable --now postgresql

echo "[step] creating benchmark database/user"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='retry_tax'" | grep -q 1; then
  sudo -u postgres psql -c "CREATE ROLE retry_tax LOGIN PASSWORD 'retry_tax';"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='retry_tax'" | grep -q 1; then
  sudo -u postgres createdb -O retry_tax retry_tax
fi

echo "[step] installing Python dependencies"
python3 -m pip install --user -r "$REPO_DIR/experiment/requirements.txt"

echo "[step] verifying database login"
PGPASSWORD=retry_tax psql -h localhost -U retry_tax -d retry_tax -c "SELECT version();"

echo "[done] AWS instance is ready."
echo "Next: bash scripts/aws_run_shard.sh <shard_index> <shard_count>"
