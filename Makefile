DC := docker compose
API := $(DC) exec -T api

.DEFAULT_GOAL := help
.PHONY: help init up down restart build logs seed migrate makemigration check test lint fmt shell psql reset dev-deps

help: ## Показать список команд
	@echo init           - первый запуск: поднять стенд и загрузить демоданные
	@echo up             - поднять стенд, миграции применяются автоматически
	@echo down           - остановить стенд
	@echo restart        - перезапустить API
	@echo build          - пересобрать образ backend
	@echo logs           - логи API
	@echo seed           - загрузить демонстрационные данные
	@echo migrate        - применить миграции
	@echo makemigration  - новая миграция, вызов: make makemigration m=описание
	@echo check          - стиль, тесты и сверка моделей с миграциями
	@echo test           - тесты
	@echo lint           - проверка стиля
	@echo fmt            - автоисправление стиля
	@echo shell          - оболочка в контейнере API
	@echo psql           - консоль PostgreSQL
	@echo reset          - снести стенд вместе с данными и поднять заново

init: up seed ## Первый запуск: поднять стенд и загрузить демоданные
	@echo Готово. Swagger UI: http://localhost:8000/docs

# --wait ждёт healthcheck API, то есть окончания миграций: следом можно сразу лить данные
up: ## Поднять стенд (миграции применяются автоматически)
	$(DC) up -d --build --wait

down: ## Остановить стенд
	$(DC) down

restart: ## Перезапустить API
	$(DC) restart api

build: ## Пересобрать образ backend
	$(DC) build api

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

shell: ## Оболочка в контейнере API
	$(DC) exec api sh

psql: ## Консоль PostgreSQL
	$(DC) exec db psql -U edu_crm -d edu_crm

reset: ## Снести стенд вместе с данными и поднять заново
	$(DC) down -v
	$(MAKE) up
