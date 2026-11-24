#!/usr/bin/env bash
# Create the separate test database if missing (run as the postgres user inside WSL).
set -e
if ! psql -tAc "SELECT 1 FROM pg_database WHERE datname='hanrag_test'" | grep -q 1; then
  createdb -O hanrag hanrag_test
  echo "Created test database hanrag_test"
fi
psql -q -d hanrag_test -c "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null
