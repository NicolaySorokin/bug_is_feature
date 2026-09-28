#!/bin/sh
# База Keycloak рядом с базой системы, в том же PostgreSQL.
#
# На новом томе скрипт запускается сам из /docker-entrypoint-initdb.d, на старом
# его запускают make up и release.sh. Повторный запуск ничего не меняет.
# Образ может выполнить скрипт через source, поэтому здесь нет set -e и exit.

keycloak_db=${KEYCLOAK_DB_NAME:-keycloak}

if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$keycloak_db'" | grep -q 1; then
    createdb --username "$POSTGRES_USER" --owner "$POSTGRES_USER" "$keycloak_db" \
        && echo "База $keycloak_db для Keycloak создана"
fi
