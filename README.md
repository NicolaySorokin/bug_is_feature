# Система контроля взаимодействия ИТ Школы Ростелекома с вузами

Каркас серверной части (ЛЦТ 2026, кейс Ростелекома): предметная модель,
рабочий процесс по договору и REST API поверх них.

## Запуск

Нужны только Docker и make.

```bash
make init
```

Команда поднимет PostgreSQL и API, применит миграции и загрузит
демонстрационные данные. Дальше:

- Swagger UI — http://localhost:8000/docs
- OpenAPI — http://localhost:8000/api/v1/openapi.json
- Проверка живости — http://localhost:8000/api/v1/health

Если стенд уже разворачивали, для повседневной работы хватает `make up`
и `make down`. Начать с чистого листа — `make reset`.

## Команды

`make help` покажет список целиком. Основное:

| Команда | Что делает |
| --- | --- |
| `make init` | первый запуск: стенд + миграции + демоданные |
| `make up` / `make down` | поднять / остановить стенд |
| `make logs` | логи API |
| `make check` | стиль, тесты и сверка моделей с миграциями |
| `make test` | тесты |
| `make fmt` | автоисправление стиля |
| `make migrate` | применить миграции |
| `make makemigration m="описание"` | создать миграцию по изменившимся моделям |
| `make psql` | консоль PostgreSQL |
| `make reset` | снести стенд вместе с данными и поднять заново |

## Что внутри

| Компонент | Решение |
| --- | --- |
| Серверная часть | Python 3.12 + FastAPI |
| База данных | PostgreSQL 16 + SQLAlchemy 2 (async) |
| Миграции | Alembic |
| Авторизация | заглушка на интерфейсе, переключается на Keycloak |
| Запуск | Docker Compose |

```
backend/
  app/
    api/v1/endpoints/   HTTP-слой: вузы, договоры, справочники, процесс
    core/               конфигурация и аутентификация
    db/                 подключение к PostgreSQL и декларативная база
    models/             таблицы SQLAlchemy
    schemas/            схемы запросов и ответов
    services/           бизнес-правила (пока — рабочий процесс)
    enums.py            статусы предметной области
  alembic/              миграции
  scripts/seed.py       демонстрационные данные
  tests/                тесты правил процесса
Makefile
docker-compose.yml
```

## Авторизация

`AUTH_BACKEND=dev` (по умолчанию) включает заглушку: токен не проверяется,
пользователь берётся из заголовков запроса.

```bash
curl http://localhost:8000/api/v1/me \
  -H "X-Dev-User: petrov" \
  -H "X-Dev-Roles: manager"
```

Без заголовков подставляется пользователь из `DEV_USER_*` со всеми ролями.
Роли: `manager` (Пользователь / KAM), `head` (Руководитель), `admin`
(Администратор).

`AUTH_BACKEND=keycloak` включает проверку Bearer-токена по JWKS реалма.
Обе схемы реализуют один интерфейс `AuthBackend`
([app/core/security.py](backend/app/core/security.py)), остальной код
про разницу не знает. Контейнер Keycloak поднимается отдельным профилем:

```bash
docker compose --profile keycloak up -d keycloak
```

## Рабочий процесс

Шаблон версионируется: этапы и переходы принадлежат версии
(`workflow_versions`), экземпляр процесса жёстко привязан к своей версии.
Поэтому правка шаблона не меняет уже запущенные процессы.

Состояния этапов (не начат, активен, завершён, пропущен, заблокирован)
нигде не хранятся — они вычисляются из истории переходов
(`workflow_events`) и текущего этапа экземпляра.

Демонстрационный шаблон из `scripts/seed.py`:

```
Контакт -> Встреча -> Документы -> Согласование -> Подписание
                                        `-> Доработка -> Согласование
```

Основные методы:

| Метод | Назначение |
| --- | --- |
| `GET /api/v1/contracts/{id}/workflow` | схема, состояния этапов, история, доступные переходы |
| `POST /api/v1/contracts/{id}/workflow` | запустить процесс по шаблону |
| `POST /api/v1/workflow/instances/{id}/transition` | перейти на разрешённый этап |
| `POST /api/v1/workflow/instances/{id}/skip` | пропустить необязательный этап с причиной |
| `POST /api/v1/workflow/instances/{id}/block` | заблокировать процесс |

## Запуск без Docker

Понадобится свой PostgreSQL.

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate       # Windows
pip install -r requirements-dev.txt
cp .env.example .env                                 # укажите свой PostgreSQL
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload
```

Тесты правил процесса базу не требуют: `pytest`.

## План работ

Что сделано — видно по коду, что осталось — в [TODO](TODO). Коротко:
клиентская часть, отчёты и выгрузки, импорт XLSX, интеграции с LMS и сайтом,
контроль проблемных процессов и визуальный редактор шаблонов. Модель и слои
под это подготовлены.
