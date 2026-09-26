#!/usr/bin/env bash
# Подготовка боевого сервера (Ubuntu 24.04) под стенд. Запускается при каждом
# деплое и идемпотентна: что уже стоит и настроено, не трогается, поэтому
# повторный запуск занимает секунды.
#
#   sudo env DEPLOY_USER=deployer bash cicd/prod/server/bootstrap.sh
#
# Что делает:
#   - Docker Engine и compose plugin из официального репозитория Docker;
#   - ротация логов контейнеров, чтобы логи не съели диск;
#   - пользователь деплоя в группе docker;
#   - certbot, его таймер продления и хук перезагрузки Nginx после продления;
#   - make (для make logs ENV=prod на сервере), каталог приложения,
#     каталог webroot для проверок Let's Encrypt;
#   - swap-файл: на 4 ГБ без него всплеск памяти заканчивается OOM killer;
#   - ежедневная резервная копия базы и файлов (таймер edu-crm-backup).
set -euo pipefail

DEPLOY_USER=${DEPLOY_USER:-${SUDO_USER:-}}
APP_DIR=${APP_DIR:-/opt/edu-crm}
CERTBOT_WEBROOT=${CERTBOT_WEBROOT:-/var/www/certbot}
NGINX_CONTAINER=${NGINX_CONTAINER:-edu_crm_nginx}
SWAP_SIZE_MB=${SWAP_SIZE_MB:-2048}

export DEBIAN_FRONTEND=noninteractive
# На свежей машине dpkg бывает занят unattended-upgrades: ждём, а не падаем.
APT=(apt-get -o DPkg::Lock::Timeout=600 -qq)

log() { printf '==> %s\n' "$*"; }
die() { printf 'Ошибка: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "нужен root: sudo bash $0"
[ -n "$DEPLOY_USER" ] || die "не задан DEPLOY_USER"
id "$DEPLOY_USER" > /dev/null 2>&1 || die "нет пользователя $DEPLOY_USER"

apt_fresh=
apt_install() {
    local pkg missing=()
    for pkg in "$@"; do
        dpkg-query -W -f='${Status}' "$pkg" 2> /dev/null | grep -q 'install ok installed' \
            || missing+=("$pkg")
    done
    [ ${#missing[@]} -gt 0 ] || return 0
    if [ -z "$apt_fresh" ]; then
        "${APT[@]}" update
        apt_fresh=1
    fi
    log "Устанавливаю: ${missing[*]}"
    "${APT[@]}" install -y --no-install-recommends "${missing[@]}"
}

apt_install ca-certificates curl make

# --- Docker: https://docs.docker.com/engine/install/ubuntu/ -----------------
if ! docker compose version > /dev/null 2>&1; then
    log "Docker из официального репозитория"
    # Пакеты из репозитория Ubuntu конфликтуют с пакетами Docker.
    for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
        if dpkg-query -W -f='${Status}' "$pkg" 2> /dev/null | grep -q 'install ok installed'; then
            "${APT[@]}" remove -y "$pkg"
        fi
    done

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    # shellcheck disable=SC1091
    codename=$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
    cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $codename
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF
    apt_fresh=
    apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# Логи контейнеров по умолчанию растут без ограничений, а диск - 18 ГБ.
# Файл пишем только если его нет: ручные настройки не перетираем.
if [ ! -f /etc/docker/daemon.json ]; then
    log "Ротация логов Docker: 3 файла по 20 МБ на контейнер"
    install -m 0755 -d /etc/docker
    cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "20m", "max-file": "3" }
}
EOF
    systemctl restart docker
fi
systemctl enable --quiet --now docker.service containerd.service

if ! id -nG "$DEPLOY_USER" | tr ' ' '\n' | grep -qx docker; then
    log "$DEPLOY_USER добавлен в группу docker"
    usermod -aG docker "$DEPLOY_USER"
fi

# --- certbot -----------------------------------------------------------------
apt_install certbot
# Пакет ставит таймер, который дважды в сутки вызывает certbot renew.
systemctl enable --quiet --now certbot.timer

hook=/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
hook_body="#!/bin/sh
# Установлено cicd/prod/server/bootstrap.sh. Выполняется certbot после
# успешного продления: Nginx в контейнере перечитывает сертификат без простоя.
if docker ps --format '{{.Names}}' | grep -qx '$NGINX_CONTAINER'; then
    docker exec '$NGINX_CONTAINER' nginx -s reload
fi"
if [ ! -f "$hook" ] || [ "$(cat "$hook")" != "$hook_body" ]; then
    log "Хук перезагрузки Nginx после продления: $hook"
    install -m 0755 -d "$(dirname "$hook")"
    printf '%s\n' "$hook_body" > "$hook"
    chmod 0755 "$hook"
fi

# --- каталоги ------------------------------------------------------------------
install -m 0755 -d "$CERTBOT_WEBROOT"
install -m 0750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" -d "$APP_DIR"
install -m 0750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" -d "$APP_DIR/releases"
install -m 0700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" -d "$APP_DIR/shared"
install -m 0700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" -d "$APP_DIR/backups"

# --- swap ------------------------------------------------------------------------
if [ -z "$(swapon --show --noheadings)" ]; then
    log "Swap-файл ${SWAP_SIZE_MB} МБ"
    if [ ! -f /swapfile ]; then
        fallocate -l "${SWAP_SIZE_MB}M" /swapfile
        chmod 600 /swapfile
        mkswap /swapfile > /dev/null
    fi
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
# Swap - страховка, а не рабочая память: без нужды в него не уходим.
if [ ! -f /etc/sysctl.d/60-edu-crm-swap.conf ]; then
    echo 'vm.swappiness = 10' > /etc/sysctl.d/60-edu-crm-swap.conf
    sysctl -q -p /etc/sysctl.d/60-edu-crm-swap.conf
fi

# --- резервные копии -------------------------------------------------------------
# Каждую ночь release.sh backup текущего релиза: база системы, база Keycloak,
# файлы вложений - в $APP_DIR/backups, хранятся 14 дней. Копии стоит
# забирать и за пределы сервера.
backup_service="[Unit]
Description=EDU CRM: резервная копия базы и файлов
After=docker.service
Requires=docker.service
ConditionPathExists=$APP_DIR/current

[Service]
Type=oneshot
User=$DEPLOY_USER
Environment=APP_DIR=$APP_DIR
ExecStart=/bin/bash $APP_DIR/current/cicd/prod/server/release.sh backup"
backup_timer="[Unit]
Description=EDU CRM: ежедневная резервная копия

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=20m
Persistent=true

[Install]
WantedBy=timers.target"
if [ "$(cat /etc/systemd/system/edu-crm-backup.service 2> /dev/null)" != "$backup_service" ] \
    || [ "$(cat /etc/systemd/system/edu-crm-backup.timer 2> /dev/null)" != "$backup_timer" ]; then
    log "Таймер резервного копирования: edu-crm-backup.timer, ежедневно в 03:30"
    printf '%s\n' "$backup_service" > /etc/systemd/system/edu-crm-backup.service
    printf '%s\n' "$backup_timer" > /etc/systemd/system/edu-crm-backup.timer
    systemctl daemon-reload
fi
systemctl enable --quiet --now edu-crm-backup.timer

log "Сервер готов: $(docker --version), $(docker compose version), $(certbot --version 2>&1)"
