# Среда развёртывания: dev (по умолчанию), preprod, prod.
# Состав стенда общий, отличия лежат в cicd/<среда>/docker-compose.yml.
ENV ?= dev
ENV_FILE := cicd/$(ENV)/.env
COMPOSE_FILES := -f docker-compose.yml -f cicd/$(ENV)/docker-compose.yml
# Файл с секретами среды подключается, только если он создан.
COMPOSE_ENV := $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE),)
# На боевых средах авторизация настоящая, поэтому Keycloak поднимается всегда.
COMPOSE_PROFILES := $(if $(filter dev,$(ENV)),,--profile keycloak)

DC := docker compose $(COMPOSE_ENV) $(COMPOSE_FILES) $(COMPOSE_PROFILES)
# С Keycloak в любой среде: make keycloak и настройка реалма в разработке.
KC_DC := docker compose $(COMPOSE_ENV) $(COMPOSE_FILES) --profile keycloak
API := $(DC) exec -T api
# Разовый контейнер из собранного образа: нужен, когда стенд не поднят.
RUN_API := $(DC) run --rm --no-deps -T api

# Сколько взаимодействий добавить для нагрузочной проверки: make seed-load N=5000
N ?= 3000

.PHONY: help build up down restart logs seed seed-load loadtest migrate makemigration \
        check test lint fmt lock openapi shell psql keycloak keycloak-setup db-ready reset dev-deps

help: ## Показать список команд
	@echo Среда задаётся переменной ENV: make up ENV=prod. По умолчанию dev.
	@echo build          - собрать образы и подготовить проект, без запуска
	@echo up             - запустить проект: контейнеры, миграции, демоданные
	@echo down           - остановить стенд
	@echo restart        - перезапустить API
	@echo logs           - логи API
	@echo seed           - загрузить демонстрационные данные
	@echo seed-load      - добавить взаимодействия для нагрузки, вызов: make seed-load N=3000
	@echo loadtest       - нагрузочная проверка по ТЗ: 50 пользователей и 10 отчётов
	@echo migrate        - применить миграции
	@echo makemigration  - новая миграция, вызов: make makemigration m=описание
	@echo check          - стиль, тесты и сверка моделей с миграциями
	@echo test           - тесты
	@echo lint           - проверка стиля
	@echo fmt            - автоисправление стиля
	@echo lock           - зафиксировать версии зависимостей в requirements.lock
	@echo openapi        - выгрузить схему API в docs/openapi.json
	@echo keycloak       - поднять Keycloak с готовым реалмом
	@echo keycloak-setup - перенести настройку реалма в Keycloak, начальные пароли
	@echo shell          - оболочка в контейнере API
	@echo psql           - консоль PostgreSQL
	@echo reset          - снести стенд вместе с данными и собрать заново

build: ## Собрать образы и подготовить проект, без запуска
	$(DC) build
	# Образы PostgreSQL и Keycloak качаем заранее, чтобы make up ничего не ждал.
	# Дефис: нет сети - не повод останавливать сборку, up дотянет образы сам.
	-$(DC) pull --ignore-buildable --quiet
	@echo Образы собраны. Запуск - make up

# PostgreSQL поднят, база Keycloak на месте. На новом томе её заводит скрипт
# инициализации, на томе постарше - этот же скрипт здесь; повтор безопасен.
db-ready:
	$(DC) up -d --wait db
	$(DC) exec -T db sh /docker-entrypoint-initdb.d/keycloak-db.sh

# --wait ждёт healthcheck API, то есть окончания миграций: следом можно сразу лить данные.
# Контейнеры создаются, если их ещё нет; образы собираются, если их не собрали через make build.
# В preprod и prod следом реалм Keycloak приводится к выгрузке и ставятся пароли.
up: db-ready ## Запустить проект: контейнеры, миграции, демоданные
	$(DC) up -d --wait
	$(if $(filter dev,$(ENV)),,$(MAKE) keycloak-setup ENV=$(ENV))
	$(MAKE) seed ENV=$(ENV)
	@echo Готово. Система: http://localhost:3000, Swagger UI: http://localhost:8000/docs

down: ## Остановить стенд
	$(DC) down

restart: ## Перезапустить API
	$(DC) restart api

logs: ## Логи API
	$(DC) logs -f api

seed: ## Загрузить демонстрационные данные
	$(API) python -m scripts.seed

seed-load: ## Добавить взаимодействия для нагрузочной проверки: make seed-load N=3000
	$(API) python -m scripts.seed --load $(N)

# Параметры скрипта передаются через ARGS: make loadtest ARGS="--duration 120".
# Под Keycloak (preprod, prod) - см. cicd/README.md, «Нагрузочная проверка»:
# пароли берутся из переменной KEYCLOAK_USER_PASSWORDS в окружении make.
loadtest: ## Нагрузочная проверка по ТЗ: 50 пользователей и 10 отчётов
	$(DC) exec -T -e KEYCLOAK_USER_PASSWORDS api python -m scripts.loadtest $(ARGS)

migrate: ## Применить миграции
	$(API) alembic upgrade head

makemigration: ## Новая миграция: make makemigration m="описание"
	$(API) alembic revision --autogenerate -m "$(m)"

check: lint test ## Стиль, тесты и сверка моделей с миграциями
	$(API) alembic check

test: dev-deps ## Тесты
	$(API) pytest -q

lint: dev-deps ## Проверка стиля
	$(API) ruff check .
	$(API) ruff format --check .

fmt: dev-deps ## Автоисправление стиля
	$(API) ruff check --fix .
	$(API) ruff format .

dev-deps: # Образ собран по requirements.txt, инструменты разработки ставим по месту
	@$(API) pip install --quiet --disable-pip-version-check --root-user-action=ignore -r requirements-dev.txt

lock: ## Зафиксировать версии зависимостей в backend/requirements.lock
	# Разовый контейнер из собранного образа: в нём стоят только рабочие
	# зависимости, инструменты разработки в снимок не попадут.
	@$(RUN_API) python -m scripts.lock > backend/requirements.lock
	@echo Версии зафиксированы в backend/requirements.lock

openapi: ## Выгрузить схему API в docs/openapi.json
	@$(RUN_API) python -m scripts.openapi > docs/openapi.json
	@echo Схема сохранена в docs/openapi.json

keycloak: db-ready ## Поднять Keycloak с готовым реалмом
	$(KC_DC) up -d --wait keycloak
	$(MAKE) keycloak-setup ENV=$(ENV)
	@echo Keycloak: http://localhost:8080 - консоль admin/admin, реалм edu-crm.
	@echo Пароли пользователей, у которых их не было, напечатаны выше.
	@echo Дальше выставьте AUTH_BACKEND=keycloak и выполните make restart

# Настройка реалма из выгрузки в работающий Keycloak и начальные пароли тем,
# у кого их нет (см. backend/scripts/keycloak_setup.py). Параметры скрипта -
# через ARGS: make keycloak-setup ARGS=--reset-passwords.
keycloak-setup: ## Перенести настройку реалма в Keycloak, начальные пароли
	$(KC_DC) run --rm -T keycloak-setup python -m scripts.keycloak_setup $(ARGS)

shell: ## Оболочка в контейнере API
	$(DC) exec api sh

psql: ## Консоль PostgreSQL
	$(DC) exec db psql -U edu_crm -d edu_crm

reset: ## Снести стенд вместе с данными и собрать заново
	$(KC_DC) down -v
	$(MAKE) build ENV=$(ENV)
	$(MAKE) up ENV=$(ENV)
