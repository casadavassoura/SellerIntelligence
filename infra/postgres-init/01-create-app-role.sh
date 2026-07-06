#!/bin/sh
# Cria a role de runtime da aplicação (api/worker/testes) — nunca superusuário nem
# BYPASSRLS. O POSTGRES_USER inicial do Postgres é sempre superuser, e a Row-Level
# Security fail-closed (docs/09-multi-tenant-strategy.md §2) nunca se aplica a
# superusuários, mesmo com FORCE ROW LEVEL SECURITY — por isso as migrations (DDL/dono do
# schema) continuam usando POSTGRES_USER, mas api/worker/testes conectam com esta role.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE "${APP_DB_USER}" WITH LOGIN PASSWORD '${APP_DB_PASSWORD}' NOSUPERUSER NOBYPASSRLS;
    GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO "${APP_DB_USER}";
EOSQL
