#!/usr/bin/env bash
# Релизы стенда на сервере. Запускается от пользователя деплоя, sudo не нужен.
#
#   release.sh activate <релиз>    сделать релиз текущим и поднять стенд,
#                                  если не поднялся, вернуть прежний
#   release.sh rollback [<релиз>]  откат на предыдущий или указанный релиз
#   release.sh list                релизы, текущий отмечен звёздочкой
#   release.sh compose <команда>   docker compose текущего релиза
#   release.sh keycloak-setup      настройка реалма и начальные пароли
#   release.sh backup              резервная копия базы, базы Keycloak и файлов
#   release.sh keycloak-tag <каталог>
#                                  тег образа Keycloak для кода в каталоге
#
# В /opt/edu-crm лежат releases/, ссылка current на текущий релиз,
# shared/prod.env с секретами и backups/. Данные хранятся в томах Docker
# и между релизами не меняются.
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/edu-crm}
KEEP_RELEASES=${KEEP_RELEASES:-5}
BACKUP_DIR=${BACKUP_DIR:-$APP_DIR/backups}
KEEP_BACKUP_DAYS=${KEEP_BACKUP_DAYS:-14}
IMAGE_REPOS="edu-crm-api edu-crm-web edu-crm-keycloak"
NGINX_CONTAINER=edu_crm_nginx

log() { printf '==> %s\n' "$*"; }
die() { printf 'Ошибка: %s\n' "$*" >&2; exit 1; }

releases() { find "$APP_DIR/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort; }
current_release() {
    if [ -L "$APP_DIR/current" ]; then basename "$(readlink "$APP_DIR/current")"; fi
}
# Имя релиза: <дата>-<время>-<коммит>, тег образов API и Nginx равен коммиту.
image_tag() { printf '%s\n' "${1##*-}"; }

# Тег образа Keycloak считается по содержимому deploy/keycloak/image, поэтому без
# изменений образ не собирается заново. Так же тег считает деплой.
keycloak_tag() {
    local dir=$1/deploy/keycloak/image
    [ -d "$dir" ] || return 0
    (cd "$dir" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum \
        | sha256sum | cut -c1-12)
}

# Тег образа repo в релизе rel.
release_image_tag() {
    case $1 in
        edu-crm-keycloak) keycloak_tag "$APP_DIR/releases/$2" ;;
        *) image_tag "$2" ;;
    esac
}

compose() {
    local dir="$APP_DIR/current"
    docker compose --project-directory "$dir" \
        --env-file "$dir/cicd/prod/.env" \
        -f "$dir/docker-compose.yml" -f "$dir/cicd/prod/docker-compose.yml" \
        --profile keycloak "$@"
}

# .env релиза собирается при каждой активации, поэтому откат идёт с актуальными
# секретами.
write_env() {
    local dir=$1 env=$1/cicd/prod/.env
    [ -f "$APP_DIR/shared/prod.env" ] || { echo "Нет $APP_DIR/shared/prod.env" >&2; return 1; }
    (
        umask 077
        {
            cat "$APP_DIR/shared/prod.env"
            printf '\n# Добавлено release.sh при активации релиза.\n'
            printf 'API_IMAGE_TAG=%s\n' "$(image_tag "$(basename "$dir")")"
            printf 'WEB_IMAGE_TAG=%s\n' "$(image_tag "$(basename "$dir")")"
            printf 'KEYCLOAK_IMAGE_TAG=%s\n' "$(keycloak_tag "$dir")"
            printf 'NGINX_CONF_SHA=%s\n' "$(sha256sum "$dir/cicd/prod/nginx.conf" | cut -c1-16)"
        } > "$env.tmp"
        mv -f "$env.tmp" "$env"
    )
}

switch_to() {
    local rel=$1
    write_env "$APP_DIR/releases/$rel" || return 1
    # Атомарная замена ссылки: current всегда указывает на целый релиз.
    ln -sfn "releases/$rel" "$APP_DIR/current.new" || return 1
    mv -Tf "$APP_DIR/current.new" "$APP_DIR/current"
}

# Есть ли в текущем релизе строка $1 в compose: старые релизы не знают базы
# keycloak и сервиса keycloak-setup.
release_has() {
    grep -qs -- "$1" "$APP_DIR/current/docker-compose.yml" "$APP_DIR/current/cicd/prod/docker-compose.yml"
}

up() {
    log "Поднимаю стенд: релиз $(current_release)"
    # База Keycloak живёт в том же PostgreSQL. На новом томе её заводит скрипт
    # инициализации, на старом этот же скрипт здесь.
    if release_has keycloak-db.sh; then
        compose up -d --wait --no-build db || return 1
        compose exec -T db sh /docker-entrypoint-initdb.d/keycloak-db.sh || return 1
    fi
    # --wait ждёт healthcheck API (то есть и окончания миграций) и Keycloak.
    compose up -d --wait --wait-timeout "${WAIT_TIMEOUT:-300}" --no-build --remove-orphans || return 1
    # Nginx узнаёт адреса api и keycloak при запуске, поэтому после пересоздания
    # контейнеров перечитываем конфигурацию.
    docker exec "$NGINX_CONTAINER" nginx -s reload || return 1
    if release_has keycloak-setup; then keycloak_setup; fi
}

# Реалм Keycloak по выгрузке релиза, пароли из секрета PROD_ENV.
keycloak_setup() {
    log "Настройка реалма Keycloak"
    compose run --rm -T keycloak-setup python -m scripts.keycloak_setup "$@"
}

show_failure() {
    compose ps -a || true
    compose logs --no-color --tail 60 api nginx || true
}

cleanup() {
    local cur rel all used tag
    cur=$(current_release)
    mapfile -t all < <(releases)
    for ((i = 0; i < ${#all[@]} - KEEP_RELEASES; i++)); do
        rel=${all[i]}
        [ "$rel" = "$cur" ] && continue
        log "Удаляю старый релиз $rel"
        rm -rf "${APP_DIR:?}/releases/$rel"
    done

    # Образы, на которые ссылается хоть один оставшийся релиз, не трогаем.
    used=" $(releases | while read -r rel; do
        for repo in $IMAGE_REPOS; do
            printf '%s:%s ' "$repo" "$(release_image_tag "$repo" "$rel")"
        done
    done) "
    for repo in $IMAGE_REPOS; do
        while read -r tag; do
            [ -n "$tag" ] || continue
            case "$used" in
                *" $repo:$tag "*) ;;
                *)
                    log "Удаляю образ $repo:$tag"
                    docker image rm "$repo:$tag" > /dev/null || true
                    ;;
            esac
        done < <(docker image ls "$repo" --format '{{.Tag}}')
    done
    docker image prune -f > /dev/null
}

activate() {
    local target=${1:?укажите релиз: release.sh list} prev
    [ -d "$APP_DIR/releases/$target" ] || die "нет релиза $target"
    for repo in $IMAGE_REPOS; do
        # Релизы до появления клиентской части образа edu-crm-web не знают.
        grep -qs "$repo" "$APP_DIR/releases/$target/docker-compose.yml" \
            "$APP_DIR/releases/$target/cicd/prod/docker-compose.yml" || continue
        docker image inspect "$repo:$(release_image_tag "$repo" "$target")" > /dev/null 2>&1 \
            || die "нет образа $repo:$(release_image_tag "$repo" "$target")"
    done
    prev=$(current_release)

    if switch_to "$target" && up; then
        rm -f "$APP_DIR/releases/$target/FAILED"
        # Демоданные грузятся только в пустую базу, повторный запуск безопасен.
        compose exec -T api python -m scripts.seed || die "демоданные не загрузились"
        cleanup
        log "Текущий релиз: $target"
        return 0
    fi

    show_failure
    touch "$APP_DIR/releases/$target/FAILED"
    if [ -n "$prev" ] && [ "$prev" != "$target" ] && [ -d "$APP_DIR/releases/$prev" ]; then
        log "Релиз $target не поднялся, возвращаю $prev"
        if switch_to "$prev" && up; then
            die "релиз $target не поднялся, стенд работает на прежнем $prev"
        fi
        show_failure
        die "не поднялся ни $target, ни прежний $prev"
    fi
    die "релиз $target не поднялся"
}

rollback() {
    local target=${1:-} cur rel
    cur=$(current_release)
    if [ -z "$target" ]; then
        # Ближайший более старый релиз, который поднимался успешно.
        while read -r rel; do
            if [[ "$rel" < "$cur" ]] && [ ! -f "$APP_DIR/releases/$rel/FAILED" ]; then
                target=$rel
            fi
        done < <(releases)
        [ -n "$target" ] || die "нет релиза старше текущего $cur"
    fi
    log "Откат: $cur -> $target"
    activate "$target"
}

# Резервная копия базы системы, базы Keycloak и файлов вложений. В ней
# персональные данные, доступ только у пользователя деплоя. Копии старше
# KEEP_BACKUP_DAYS дней удаляются.
backup() {
    local stamp dir
    stamp=$(date +%Y%m%d-%H%M%S)
    dir=$BACKUP_DIR
    install -m 700 -d "$dir"
    (
        umask 077
        log "Копия базы системы: $dir/$stamp-edu_crm.dump"
        # Переменные раскрывает оболочка внутри контейнера базы.
        # shellcheck disable=SC2016
        compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' \
            > "$dir/$stamp-edu_crm.dump.tmp"
        if release_has keycloak-db.sh; then
            log "Копия базы Keycloak: $dir/$stamp-keycloak.dump"
            # shellcheck disable=SC2016
            compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc keycloak' \
                > "$dir/$stamp-keycloak.dump.tmp"
        fi
        log "Копия файлов вложений: $dir/$stamp-storage.tgz"
        compose exec -T api tar czf - -C /app/storage . > "$dir/$stamp-storage.tgz.tmp"
        for file in "$dir/$stamp"-*.tmp; do mv -f "$file" "${file%.tmp}"; done
    ) || { rm -f "$dir/$stamp"-*.tmp; die "резервная копия не снята"; }

    find "$dir" -maxdepth 1 -type f \( -name '*.dump' -o -name '*.tgz' \) \
        -mtime "+$KEEP_BACKUP_DAYS" -print -delete | sed 's/^/==> Удалена старая копия /'
    log "Копия готова: $(du -ch "$dir/$stamp"-* | tail -1 | cut -f1)"
}

list() {
    local cur rel mark note
    cur=$(current_release)
    while read -r rel; do
        mark=' '
        note=''
        [ "$rel" = "$cur" ] && mark='*'
        [ -f "$APP_DIR/releases/$rel/FAILED" ] && note=' (не поднялся)'
        printf '%s %s%s\n' "$mark" "$rel" "$note"
    done < <(releases | sort -r)
}

cmd=${1:-}
shift || true
case "$cmd" in
    activate) activate "$@" ;;
    rollback) rollback "$@" ;;
    list) list ;;
    compose) compose "$@" ;;
    keycloak-setup) keycloak_setup "$@" ;;
    backup) backup ;;
    keycloak-tag) keycloak_tag "${1:?укажите каталог с кодом}" ;;
    *) die "использование: $0 activate <релиз> | rollback [<релиз>] | list | compose <команда> | keycloak-setup | backup" ;;
esac
