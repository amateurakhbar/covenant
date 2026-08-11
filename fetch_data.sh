#!/usr/bin/env bash
# Pull the scoring parquet from the GitHub release at build time.
# Rebuild it yourself instead with: python sweep.py --build <snapshot.csv>
set -euo pipefail
mkdir -p data
if [ ! -f data/companies.parquet ]; then
  echo "Downloading register snapshot (184 MB)..."
  curl -fsSL -o data/companies.parquet \
    https://github.com/akbar-33/covenant/releases/download/snapshot-2026-08-01/companies.parquet
fi
ls -lh data/companies.parquet
