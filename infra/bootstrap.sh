#!/bin/sh
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
  -v migration_password="$MIGRATION_DB_PASSWORD" -v app_password="$APP_DB_PASSWORD" \
  -f /bootstrap/bootstrap.sql
