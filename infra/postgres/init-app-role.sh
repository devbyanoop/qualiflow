#!/bin/bash
set -euo pipefail

# The official postgres image only runs files in /docker-entrypoint-initdb.d/
# the FIRST time a container starts against a given data volume -- never
# on a restart against existing data. If this doesn't seem to have run,
# check whether the qualiflow_pg_data volume already existed.
#
# Creates a non-superuser login role for the application itself.
# POSTGRES_USER (qualiflow) stays a superuser, reserved for migrations
# and test setup/verification -- the app never connects as it, so RLS
# policies genuinely apply when the app queries the database.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    CREATE ROLE qualiflow_app LOGIN PASSWORD '$QUALIFLOW_PG_APP_PASSWORD';
    GRANT CONNECT ON DATABASE $POSTGRES_DB TO qualiflow_app;
SQL
