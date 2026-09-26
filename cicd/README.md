# Среды развёртывания

Состав стенда один и тот же во всех средах и описан в корневом
`docker-compose.yml`. Здесь лежат только отличия: что монтируется, какие
порты открыты, как включается авторизация и что стоит на входе.

| Среда | Для чего | Отличия |
| --- | --- | --- |
| `dev` | разработка на своей машине | система на http://localhost:3000, код API монтируется в контейнер, сервер перезапускается сам, порты API, PostgreSQL и Keycloak открыты, авторизация — заглушка |
| `preprod` | проверка перед демонстрацией | как на бою, но по HTTP; PostgreSQL доступен только с самого сервера; авторизация через Keycloak |
| `prod` | демонстрационный стенд | HTTPS, наружу только Nginx, ограничения по памяти, перезапуск при падении, несколько рабочих процессов API |

## Как запускать

Среда выбирается переменной `ENV`, по умолчанию `dev`:

```bash
make up                 # разработка
make up ENV=preprod
make up ENV=prod
```

Любая другая команда Makefile работает так же: `make logs ENV=prod`,
`make psql ENV=preprod`, `make down ENV=prod`.

В средах `preprod` и `prod` Keycloak поднимается вместе со стендом —
отдельная команда `make keycloak` нужна только в разработке.

Во всех средах наружу смотрит Nginx из образа `edu-crm-web`: он раздаёт
собранную клиентскую часть и проксирует `/api`, `/docs`, `/redoc`,
а в `preprod` и `prod` ещё и Keycloak (`/realms`, `/resources`).
Конфигурация Nginx своя у каждой среды — `cicd/<среда>/nginx.conf`.

Адреса, куда Keycloak возвращает после входа, у клиента `edu-crm-web`
ставит настройка реалма (`make keycloak-setup`, её же запускает
`make up`) — это адреса интерфейса из `CORS_ORIGINS` среды. Для
`preprod` достаточно указать там адрес стенда. `preprod` работает
по HTTP, поэтому в его `.env` задано `KEYCLOAK_SSL_REQUIRED=none`.

## Секреты

Значения задаются файлом `.env` рядом с `docker-compose.yml` нужной среды:
`cicd/preprod/.env`, `cicd/prod/.env`. Рядом лежит `.env.example` —
скопируйте его и заполните. В репозиторий файлы `.env` не попадают.

```bash
cp cicd/prod/.env.example cicd/prod/.env
$EDITOR cicd/prod/.env
make up ENV=prod
```

Пароли `POSTGRES_PASSWORD` и `KEYCLOAK_ADMIN_PASSWORD` в боевой среде
обязательны: значения по умолчанию из корневого compose годятся только
для разработки. Так же обязательна `KEYCLOAK_USER_PASSWORDS` — пароли
пользователей реалма, пары `логин:пароль` через запятую, по паре на
каждого пользователя из `deploy/keycloak/realm-export.json`. Новые
пароли генерирует `python -m scripts.keycloak_setup --generate-passwords`
(см. README, раздел «Keycloak»). В репозитории паролей нет.

## Боевой стенд: автоматический деплой

Стенд https://edu-crm.nikitarodionov.ru обновляется сам. Пуш или слияние
pull request в `main` запускает **CI** (стиль, тесты, миграции, демоданные,
схема API, проверки и сборка клиентской части, сборка образов). Если CI
зелёный, следом запускается **Деплой**
(`.github/workflows/deploy.yml`) и выкладывает ровно тот коммит, который
проверил CI. Красный CI — деплоя нет, на сервере остаётся прежняя версия.

Ход и итог каждого деплоя — Actions → «Деплой» → запуск: на странице
запуска (Summary) таблица проверок, память контейнеров и список релизов.

### Что делает деплой

1. Собирает образы на раннере GitHub: API `edu-crm-api:<коммит>` и Nginx
   с клиентской частью `edu-crm-web:<коммит>`. Образ Keycloak
   `edu-crm-keycloak:<тег>` помечен по содержимому
   `deploy/keycloak/image` и собирается, только если такого ещё нет
   на сервере.
2. Проверяет секрет `PROD_ENV`: без паролей базы и Keycloak и без пароля
   для каждого пользователя реалма (`KEYCLOAK_USER_PASSWORDS`)
   не выкладывает. В журнал попадают только логины.
3. Подключается по SSH. Ключ хоста сверяется с `SSH_KNOWN_HOSTS`, чужой
   сервер не пройдёт.
4. Готовит сервер — `cicd/prod/server/bootstrap.sh`. Скрипт идемпотентный:
   что уже стоит, не трогает. Ставит Docker Engine и compose plugin из
   репозитория Docker, добавляет пользователя в группу `docker`, ставит
   certbot и `make`, заводит swap 2 ГБ, включает ротацию логов контейнеров
   (3 файла по 20 МБ), создаёт `/opt/edu-crm`, включает ежедневную
   резервную копию (таймер `edu-crm-backup.timer`).
5. Кладёт код коммита в новый каталог релиза, привозит образы с раннера
   (уже привезённые не передаются — сервер ничего не собирает и не ходит
   в реестры), записывает `PROD_ENV` в `/opt/edu-crm/shared/prod.env`.
6. Если сертификата ещё нет — выпускает его (`certificate.sh issue`).
7. Поднимает стенд — `release.sh activate`: переключает `current` на новый
   релиз, заводит базу Keycloak, если её ещё нет, `docker compose up --wait`
   ждёт healthcheck API (значит, миграции прошли) и Keycloak, настраивает
   реалм по выгрузке и ставит пароли из секрета (`keycloak-setup`),
   в пустую базу грузит демоданные, удаляет старые релизы.
   **Не поднялся — сам возвращает прежний релиз**, деплой краснеет.
8. Один раз переводит продление сертификата на webroot (`certificate.sh webroot`).
9. Проверяет стенд снаружи: `/api/v1/health` (и что в нём нет ничего,
   кроме статуса); что по адресу стенда открывается сама система, а не
   Swagger; что адрес страницы (`/contracts`) открывается напрямую;
   кэширование файлов интерфейса и заголовок Content-Security-Policy;
   что версия Nginx скрыта; сайт по HTTPS с проверкой сертификата,
   редирект с HTTP; Keycloak: реалм, страница входа в теме системы,
   запрет входа по паролю в обход страницы, закрытый реалм `master`;
   отдачу файлов для продления.

Деплои не идут параллельно: следующий ждёт окончания текущего.

### Секреты репозитория

| Секрет | Что в нём |
| --- | --- |
| `SSH_HOST` | адрес сервера |
| `SSH_USER` | пользователь деплоя (`deployer`, sudo без пароля) |
| `SSH_PRIVATE_KEY` | закрытый ключ этого пользователя |
| `SSH_KNOWN_HOSTS` | ключ хоста: `ssh-keyscan <SSH_HOST>`, адрес в строке тот же, что в `SSH_HOST` |
| `PROD_ENV` | содержимое `.env` боевой среды, образец — `cicd/prod/.env.example`; в том числе пароли пользователей `KEYCLOAK_USER_PASSWORDS` |

Секреты можно вставлять из Windows: `\r` деплой вычищает. Поменяли
`PROD_ENV` — изменения вступят в силу со следующим деплоем. Доступ к серверу
без деплоя проверяет workflow «Проверка сервера» (`server-check.yml`).

### Что лежит на сервере

```
/opt/edu-crm/
  releases/20260925-143000-ee2f121662d5/   код коммита; REVISION — коммит, ветка, запуск Actions
  current -> releases/...                   текущий релиз, compose работает отсюда
  shared/prod.env                           секрет PROD_ENV
  backups/                                  резервные копии, 14 дней
/etc/letsencrypt/                           сертификаты
/var/www/certbot/                           webroot для продления
```

Каждый релиз — код одного коммита; `cicd/prod/.env` релиза собирается
из `shared/prod.env` при активации, поэтому и старый релиз после отката
работает с актуальными секретами. Хранятся 5 последних релизов и их образы.
Данные — тома Docker `edu-crm_pgdata` (PostgreSQL) и `edu-crm_api_storage`
(файлы): релизы и откаты их не трогают.

Nginx пересоздаётся с каждым релизом — в его образе клиентская часть
этого коммита; это секунды. Keycloak пересоздаётся, только когда меняется
его образ (тема страницы входа, `deploy/keycloak/image`). Данные Keycloak —
пользователи, пароли, сессии, журнал входов — хранятся в базе `keycloak`
того же PostgreSQL (том `edu-crm_pgdata`) и пересоздание переживают.
Правки `realm-export.json` переносит в работающий реалм настройка реалма
при каждом деплое; вручную — `release.sh keycloak-setup`.

Релизы, выложенные до перевода Keycloak на PostgreSQL, запускают его
по-старому, с паролями из выгрузки. Откатываться на них не стоит.

### HTTPS

- **Первый сертификат** выпускается до запуска Nginx: `certbot --standalone`
  сам слушает 80-й порт. Письма Let's Encrypt приходят на sorokin.n.04@mail.ru.
- **Продление** — таймер `certbot.timer` дважды в сутки. Certbot кладёт
  проверочный файл в `/var/www/certbot`, Nginx отдаёт его по
  `/.well-known/acme-challenge/` — стенд не останавливается.
- **После продления** хук `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`
  делает `nginx -s reload`, и Nginx берёт новый сертификат.

Проверить продление вручную: `sudo certbot renew --dry-run`.

### Логи

```bash
ssh deployer@edu-crm.nikitarodionov.ru
cd /opt/edu-crm/current
cat REVISION                          # какой коммит сейчас выложен
make logs ENV=prod                    # логи API в реальном времени
docker logs -f --tail 100 edu_crm_nginx
docker logs --tail 100 edu_crm_keycloak
docker logs --tail 100 edu_crm_db
docker stats --no-stream              # память и процессор контейнеров
bash cicd/prod/server/release.sh compose ps
```

`make` на сервере работает как обычно (`make psql ENV=prod`,
`make shell ENV=prod`), если запускать из `/opt/edu-crm/current`.
Лог выпуска и продления сертификата — `/var/log/letsencrypt/letsencrypt.log`,
таймер — `systemctl list-timers certbot.timer`.

### Резервные копии

Каждую ночь (03:30 по времени сервера) таймер `edu-crm-backup.timer`
выполняет `release.sh backup`: в `/opt/edu-crm/backups` ложатся копия базы
системы (`*-edu_crm.dump`), базы Keycloak (`*-keycloak.dump`) и файлов
вложений (`*-storage.tgz`). Хранятся 14 дней. В копиях персональные
данные: каталог доступен только пользователю деплоя. Копии стоит
регулярно забирать за пределы сервера.

```bash
cd /opt/edu-crm/current
bash cicd/prod/server/release.sh backup     # копия сейчас
systemctl list-timers edu-crm-backup.timer   # когда следующая
```

Восстановление (подставьте дату копии):

```bash
cd /opt/edu-crm/current
R="bash cicd/prod/server/release.sh"
$R compose stop api keycloak nginx
$R compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
  < ../../backups/ДАТА-edu_crm.dump
$R compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d keycloak --clean --if-exists --no-owner' \
  < ../../backups/ДАТА-keycloak.dump
$R compose up -d --wait --no-build
$R compose exec -T api sh -c 'rm -rf /app/storage/* && tar xzf - -C /app/storage' \
  < ../../backups/ДАТА-storage.tgz
```

### Сброс к демоданным

Actions → «Деплой» → Run workflow, «Данные стенда» — «Сбросить
к демоданным». Деплой выкладывает коммит как обычно, затем
`release.sh reset-data --confirm`: снимает резервную копию, удаляет тома
базы и файлов и поднимает стенд заново — миграции, реалм из выгрузки,
пароли из секрета, чистые демоданные. Так стенд возвращают в исходное
состояние после ручных проверок. На сервере то же самое:

```bash
bash /opt/edu-crm/current/cicd/prod/server/release.sh reset-data --confirm
```

### Нагрузочная проверка

Пароли пользователей и вход в обход страницы Keycloak нужны только
на время замера:

```bash
cd /opt/edu-crm/current
R="bash cicd/prod/server/release.sh"
$R keycloak-setup --loadtest on       # включить клиент edu-crm-loadtest
set -a; . cicd/prod/.env; set +a      # KEYCLOAK_USER_PASSWORDS
make loadtest ENV=prod ARGS="--keycloak-url http://keycloak:8080"
$R keycloak-setup --loadtest off      # выключить
```

Не запускайте во время показа: нагрузка настоящая.

### Откат

**Быстро, на сервере** — секунды, ничего не собирается:

```bash
cd /opt/edu-crm/current
bash cicd/prod/server/release.sh list       # релизы, * — текущий
bash cicd/prod/server/release.sh rollback   # на предыдущий удачный
bash cicd/prod/server/release.sh rollback 20260925-143000-ee2f121662d5
```

**Через GitHub** — Actions → «Деплой» → Run workflow, в поле ref указать
коммит или тег. Образ соберётся заново, выкладка пойдёт как обычно.
Подходят коммиты, в которых уже есть этот деплой.

**Насовсем** — `git revert` плохого коммита в `main`: CI и деплой
выложат исправленную версию сами. Иначе следующий пуш снова выложит то,
от чего откатились.

Откат кода не откатывает миграции базы. Старый код обычно работает
с новой схемой (добавленные столбцы ему не мешают); если нет — до отката
выполнить `alembic downgrade <ревизия>` в контейнере API.

### Память

Сервер — 2 vCPU и 4 ГБ. Под нагрузкой из ТЗ (`make loadtest`:
50 пользователей и 10 отчётов одновременно) стенд занимает около 1,4 ГБ:

| Контейнер | Под нагрузкой | Лимит |
| --- | --- | --- |
| API, 4 процесса (`WEB_CONCURRENCY=4`) | ~550 МБ | 1 ГБ |
| Keycloak | ~560 МБ | 1 ГБ |
| PostgreSQL | ~220 МБ | 1 ГБ |
| Nginx | ~5 МБ | 128 МБ |

Swap 2 ГБ — страховка от OOM killer. Если деплой предупредит, что свободно
меньше 400 МБ, уменьшите `WEB_CONCURRENCY` в `PROD_ENV` до 2.

Выгрузки (PDF, XLSX, диаграммы) нагружают процессор. Каждый процесс API
собирает не больше `EXPORT_CONCURRENCY` файлов одновременно (по умолчанию 1)
с пониженным приоритетом, остальные ждут в очереди — так отчёты
не замедляют интерфейс. На 2 vCPU значение больше 1 не ставьте.

## Запуск prod вручную

Без GitHub стенд поднимается так же, как в разработке: заполнить
`cicd/prod/.env`, положить сертификат в `/etc/letsencrypt/live/<домен>/`
и выполнить `make build ENV=prod && make up ENV=prod`. Миграции применяются
при старте контейнера API, отдельная команда не нужна.
