# syntax=docker/dockerfile:1
# Keycloak системы: заранее собранная конфигурация под PostgreSQL
# и тема страницы входа в стиле Ростелекома (themes/edu-crm).
#
# Настройки сборки (база, health) зашиты в образ, поэтому боевой запуск -
# `start --optimized` - не пересобирает Keycloak при каждом старте
# и поднимается быстрее. Реалм в образ не входит: выгрузка подключается
# файлом, а переносит её в работающий Keycloak scripts/keycloak_setup.py.

FROM quay.io/keycloak/keycloak:26.0 AS build

ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true

COPY --chown=keycloak:keycloak themes/ /opt/keycloak/themes/
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.0
COPY --from=build /opt/keycloak/ /opt/keycloak/

# Проверка готовности - порт управления 9000 (/health/ready). curl в образе
# нет, запрос уходит средствами bash; используется в healthcheck compose.
COPY --chmod=755 healthcheck.sh /opt/keycloak/bin/healthcheck.sh
