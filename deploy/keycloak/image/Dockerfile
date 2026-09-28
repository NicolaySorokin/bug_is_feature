# syntax=docker/dockerfile:1
# Keycloak системы: сборка под PostgreSQL и тема входа в стиле Ростелекома.
#
# Настройки сборки зашиты в образ, поэтому start --optimized не пересобирает
# Keycloak при старте. Реалм в образ не входит, его переносит keycloak_setup.py.

FROM quay.io/keycloak/keycloak:26.0 AS build

ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true

COPY --chown=keycloak:keycloak themes/ /opt/keycloak/themes/
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.0
COPY --from=build /opt/keycloak/ /opt/keycloak/

# Проверка готовности по /health/ready на порту 9000. curl в образе нет,
# запрос делает bash.
COPY --chmod=755 healthcheck.sh /opt/keycloak/bin/healthcheck.sh
