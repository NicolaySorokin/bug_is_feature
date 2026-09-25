#!/usr/bin/env bash
# Сертификат Let's Encrypt для стенда. Запускается от root при каждом деплое.
#
#   sudo env DOMAIN=... LE_EMAIL=... bash certificate.sh issue
#       Первый выпуск, до запуска Nginx: certbot сам слушает 80-й порт
#       (--standalone). Если сертификат уже есть, ничего не делает.
#
#   sudo env DOMAIN=... bash certificate.sh webroot
#       Когда Nginx поднят: переводит продление на webroot. Проверочные
#       файлы certbot кладёт в CERTBOT_WEBROOT, Nginx отдаёт их по
#       /.well-known/acme-challenge/ (см. cicd/prod/nginx.conf), так что
#       продление идёт без остановки стенда. certbot reconfigure перед
#       сохранением делает пробное продление на тестовом сервере Let's Encrypt,
#       то есть заодно проверяет всю цепочку. Если уже webroot - ничего не делает.
#
# Продление - таймер certbot.timer, после него хук из bootstrap.sh
# перезагружает Nginx.
set -euo pipefail

DOMAIN=${DOMAIN:?не задан DOMAIN}
CERTBOT_WEBROOT=${CERTBOT_WEBROOT:-/var/www/certbot}
NGINX_CONTAINER=${NGINX_CONTAINER:-edu_crm_nginx}
LIVE=/etc/letsencrypt/live/$DOMAIN
RENEWAL=/etc/letsencrypt/renewal/$DOMAIN.conf

log() { printf '==> %s\n' "$*"; }
die() { printf 'Ошибка: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "нужен root"

authenticator() {
    sed -n 's/^authenticator *= *//p' "$RENEWAL" 2> /dev/null
}

issue() {
    if [ -f "$LIVE/fullchain.pem" ] && [ -f "$LIVE/privkey.pem" ]; then
        log "Сертификат уже есть: $(openssl x509 -in "$LIVE/fullchain.pem" -noout -enddate)"
        return 0
    fi
    : "${LE_EMAIL:?не задан LE_EMAIL}"

    # 80-й порт должен быть свободен. Nginx без сертификата не стартует,
    # но если каталог сертификатов пропал на живом стенде - останавливаем.
    if docker ps --format '{{.Names}}' 2> /dev/null | grep -qx "$NGINX_CONTAINER"; then
        log "Останавливаю $NGINX_CONTAINER, чтобы освободить 80-й порт"
        docker stop "$NGINX_CONTAINER" > /dev/null
    fi

    log "Выпускаю сертификат для $DOMAIN (certbot --standalone)"
    certbot certonly --standalone \
        --non-interactive --agree-tos --no-eff-email \
        --email "$LE_EMAIL" \
        --cert-name "$DOMAIN" -d "$DOMAIN"
    log "Готово: $(openssl x509 -in "$LIVE/fullchain.pem" -noout -enddate)"
}

webroot() {
    [ -f "$RENEWAL" ] || die "нет $RENEWAL - сначала certificate.sh issue"
    if [ "$(authenticator)" = webroot ]; then
        log "Продление уже через webroot ($CERTBOT_WEBROOT)"
        return 0
    fi
    docker ps --format '{{.Names}}' | grep -qx "$NGINX_CONTAINER" \
        || die "$NGINX_CONTAINER не запущен: webroot проверить нечем"

    log "Перевожу продление на webroot $CERTBOT_WEBROOT (с пробным продлением)"
    certbot reconfigure --non-interactive \
        --cert-name "$DOMAIN" \
        --webroot --webroot-path "$CERTBOT_WEBROOT"
    [ "$(authenticator)" = webroot ] || die "certbot не сохранил webroot в $RENEWAL"
    log "Продление через webroot настроено"
}

case "${1:-}" in
    issue) issue ;;
    webroot) webroot ;;
    *) die "использование: $0 issue|webroot" ;;
esac
