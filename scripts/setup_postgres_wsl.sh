#!/usr/bin/env bash
# Installs PostgreSQL 16 + pgvector inside WSL (Ubuntu 24.04) and creates the hanrag DB.
# Run inside WSL:  bash /mnt/d/projects/hanrag/scripts/setup_postgres_wsl.sh
set -euo pipefail

sudo apt-get update
sudo apt-get install -y postgresql-16 postgresql-16-pgvector

# Keep Postgres small for an 8 GB laptop
PGCONF=/etc/postgresql/16/main/postgresql.conf
sudo sed -i "s/^#\?shared_buffers.*/shared_buffers = 128MB/" "$PGCONF"
sudo sed -i "s/^#\?max_connections.*/max_connections = 20/" "$PGCONF"
sudo sed -i "s/^#\?listen_addresses.*/listen_addresses = 'localhost'/" "$PGCONF"

sudo service postgresql restart

# Dev-only credentials (match DATABASE_URL in .env). Change for any deployment.
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hanrag') THEN
    CREATE ROLE hanrag LOGIN PASSWORD 'hanrag_dev';
  END IF;
END $$;
SQL

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='hanrag'" | grep -q 1 \
  || sudo -u postgres createdb -O hanrag hanrag

sudo -u postgres psql -d hanrag -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "Done. Test from Windows: psql or the Step 1 healthcheck script."
psql "postgresql://hanrag:hanrag_dev@localhost:5432/hanrag" -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
