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
API := $(DC) exec -T api
# Разовый контейнер из собранного образа: нужен, когда стенд не поднят.
RUN_API := $(DC) run --rm --no-deps -T api

.PHONY: help build up down restart logs seed migrate makemigration check test lint fmt \
        lock openapi shell psql keycloak reset dev-deps

help: ## Показать список команд
	@echo Среда задаётся переменной ENV: make up ENV=prod. По умолчанию dev.
	@echo build          - собрать образы и подготовить проект, без запуска
	@echo up             - запустить проект: контейнеры, миграции, демоданные
	@echo down           - остановить стенд
	@echo restart        - перезапустить API
	@echo logs           - логи API
	@echo seed           - загрузить демонстрационные данные
	@echo migrate        - применить миграции
	@echo makemigration  - новая миграция, вызов: make makemigration m=описание
	@echo check          - стиль, тесты и сверка моделей с миграциями
	@echo test           - тесты
	@echo lint           - проверка стиля
	@echo fmt            - автоисправление стиля
	@echo lock           - зафиксировать версии зависимостей в requirements.lock
	@echo openapi        - выгрузить схему API в docs/openapi.json
	@echo keycloak       - поднять Keycloak с готовым реалмом
	@echo shell          - оболочка в контейнере API
	@echo psql           - консоль PostgreSQL
	@echo reset          - снести стенд вместе с данными и собрать заново

build: ## Собрать образы и подготовить проект, без запуска
	$(DC) build
	# Образы PostgreSQL и Keycloak качаем заранее, чтобы make up ничего не ждал.
	# Дефис: нет сети - не повод останавливать сборку, up дотянет образы сам.
	-$(DC) pull --ignore-buildable --quiet
	@echo Образы собраны. Запуск - make up

# --wait ждёт healthcheck API, то есть окончания миграций: следом можно сразу лить данные.
# Контейнеры создаются, если их ещё нет; образы собираются, если их не собрали через make build.
up: ## Запустить проект: контейнеры, миграции, демоданные
	$(DC) up -d --wait
	$(MAKE) seed ENV=$(ENV)
	@echo Готово. Swagger UI: http://localhost:8000/docs

down: ## Остановить стенд
	$(DC) down

restart: ## Перезапустить API
	$(DC) restart api

logs: ## Логи API
	$(DC) logs -f api

seed: ## Загрузить демонстрационные данные
	$(API) python -m scripts.seed

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

keycloak: ## Поднять Keycloak с готовым реалмом
	docker compose $(COMPOSE_ENV) $(COMPOSE_FILES) --profile keycloak up -d --wait keycloak
	@echo Keycloak: http://localhost:8080 - admin/admin, реалм edu-crm.
	@echo Дальше выставьте AUTH_BACKEND=keycloak и выполните make restart

shell: ## Оболочка в контейнере API
	$(DC) exec api sh

psql: ## Консоль PostgreSQL
	$(DC) exec db psql -U edu_crm -d edu_crm

reset: ## Снести стенд вместе с данными и собрать заново
	$(DC) down -v
	$(MAKE) build ENV=$(ENV)
	$(MAKE) up ENV=$(ENV)
