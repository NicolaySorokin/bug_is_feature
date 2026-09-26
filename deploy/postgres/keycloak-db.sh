#!/bin/sh
# База Keycloak рядом с базой системы, в том же PostgreSQL.
#
# Файл подключён в /docker-entrypoint-initdb.d, поэтому на новом томе
# база заводится сама. На томе, который создан раньше, этот же файл
# запускают `make up` и release.sh:
#   docker compose exec -T db sh /docker-entrypoint-initdb.d/keycloak-db.sh
# Повторный запуск ничего не меняет.
#
# Скрипт инициализации образ postgres может выполнить через source, поэтому
# здесь нет set -e/-u и exit: они изменили бы поведение самого entrypoint.

keycloak_db=${KEYCLOAK_DB_NAME:-keycloak}

if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$keycloak_db'" | grep -q 1; then
    createdb --username "$POSTGRES_USER" --owner "$POSTGRES_USER" "$keycloak_db" \
        && echo "База $keycloak_db для Keycloak создана"
fi
