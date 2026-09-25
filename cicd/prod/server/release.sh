#!/usr/bin/env bash
# Релизы стенда на сервере. Запускается от пользователя деплоя (он в группе
# docker), sudo не нужен.
#
#   release.sh activate <релиз>    сделать релиз текущим и поднять стенд;
#                                  не поднялся - вернуть прежний релиз
#   release.sh rollback [<релиз>]  откат на предыдущий (или указанный) релиз
#   release.sh list                релизы, текущий отмечен звёздочкой
#   release.sh compose <команда>   docker compose текущего релиза:
#                                  compose ps, compose logs -f api ...
#
# Каталог приложения (APP_DIR, по умолчанию /opt/edu-crm):
#   releases/<дата>-<время>-<коммит>/  код коммита и файл REVISION
#   current -> releases/...            текущий релиз, compose работает отсюда
#   shared/prod.env                    секреты из PROD_ENV; при активации
#                                      из него собирается cicd/prod/.env релиза
#
# Образы релиза - edu-crm-api:<коммит> (API) и edu-crm-web:<коммит>
# (Nginx с клиентской частью), их привозит деплой.
# Данные (PostgreSQL, файлы) лежат в томах Docker и между релизами не меняются.
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/edu-crm}
KEEP_RELEASES=${KEEP_RELEASES:-5}
IMAGE_REPOS="edu-crm-api edu-crm-web"
NGINX_CONTAINER=edu_crm_nginx

log() { printf '==> %s\n' "$*"; }
die() { printf 'Ошибка: %s\n' "$*" >&2; exit 1; }

releases() { find "$APP_DIR/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort; }
current_release() {
    if [ -L "$APP_DIR/current" ]; then basename "$(readlink "$APP_DIR/current")"; fi
}
# Имя релиза - <дата>-<время>-<коммит>, тег образа - коммит.
image_tag() { printf '%s\n' "${1##*-}"; }

compose() {
    local dir="$APP_DIR/current"
    docker compose --project-directory "$dir" \
        --env-file "$dir/cicd/prod/.env" \
        -f "$dir/docker-compose.yml" -f "$dir/cicd/prod/docker-compose.yml" \
        --profile keycloak "$@"
}

# .env релиза: секреты среды плюс то, что относится к самому релизу.
# Собирается при каждой активации, поэтому откат на старый код идёт
# с актуальными секретами.
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
            printf 'NGINX_CONF_SHA=%s\n' "$(sha256sum "$dir/cicd/prod/nginx.conf" | cut -c1-16)"
            printf 'KEYCLOAK_REALM_SHA=%s\n' \
                "$(sha256sum "$dir/deploy/keycloak/realm-export.json" | cut -c1-16)"
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

up() {
    log "Поднимаю стенд: релиз $(current_release)"
    # --wait ждёт healthcheck API, то есть и окончания миграций.
    compose up -d --wait --wait-timeout "${WAIT_TIMEOUT:-300}" --no-build --remove-orphans || return 1
    # Nginx узнаёт адреса api и keycloak при запуске. Пересозданный
    # контейнер получает новый адрес - перечитываем конфигурацию.
    docker exec "$NGINX_CONTAINER" nginx -s reload
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

    used=" $(releases | while read -r rel; do image_tag "$rel"; done | tr '\n' ' ') "
    for repo in $IMAGE_REPOS; do
        while read -r tag; do
            [ -n "$tag" ] || continue
            case "$used" in
                *" $tag "*) ;;
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
        docker image inspect "$repo:$(image_tag "$target")" > /dev/null 2>&1 \
            || die "нет образа $repo:$(image_tag "$target")"
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
    *) die "использование: $0 activate <релиз> | rollback [<релиз>] | list | compose <команда>" ;;
esac
