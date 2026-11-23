#!/bin/bash
# * Runs once, on the first start of an empty DB: adds pgvector and the read-only app user.
# ! Postgres only runs this when the volume is empty. To re-run it: docker compose down -v
# Also used by CI, where PGHOST/PGPASSWORD point psql at the service container.

psql -v ON_ERROR_STOP=1 \
    -v ro_password="$UNIRAG_RO_PASSWORD" \
    -v db_name="$POSTGRES_DB" \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;

CREATE ROLE unirag_ro LOGIN PASSWORD :'ro_password';
-- ! Every session of the app user is read-only, even if a write slips past the SQL guard.
ALTER ROLE unirag_ro SET default_transaction_read_only = on;

GRANT CONNECT ON DATABASE :"db_name" TO unirag_ro;
GRANT USAGE ON SCHEMA public TO unirag_ro;
-- * Tables are created later (Phase 1) by the admin, so grant SELECT on future tables now.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO unirag_ro;
SQL
