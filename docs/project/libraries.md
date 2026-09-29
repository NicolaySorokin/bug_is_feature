# Библиотеки и компоненты

Основные компоненты решения и прямые библиотеки (раздел 6, п. 2 ТЗ).
Точные версии Python-пакетов зафиксированы в
[`backend/requirements.lock`](../../backend/requirements.lock), клиентских
пакетов - в [`frontend/package-lock.json`](../../frontend/package-lock.json).
Этот обзор не заменяет перечень всех транзитивных зависимостей и проверку
лицензий конкретного собранного образа. GitHub Actions указан как сервис CI.

## Инфраструктура

| Компонент | Версия | Назначение | Лицензия |
| --- | --- | --- | --- |
| Docker Engine, Docker Compose v2 | 24+ | контейнеры и запуск стенда | Apache-2.0 |
| PostgreSQL | 16 (образ `postgres:16-alpine`) | база данных | PostgreSQL |
| Keycloak | 26.0 (образ `quay.io/keycloak/keycloak:26.0`) | вход (OIDC), роли, учётные записи | Apache-2.0 |
| Nginx | 1.27 (образ `nginx:1.27-alpine`) | единая точка входа: интерфейс, TLS, прокси к API и Keycloak | BSD-2-Clause |
| Python | 3.12 (образ `python:3.12-slim`) | серверная часть | PSF |
| Node.js | 22 (образ `node:22-alpine`, только сборка) | сборка клиентской части | MIT |
| DejaVu Fonts | пакет `fonts-dejavu-core` | кириллица в PDF и диаграммах | свободная (Bitstream Vera) |
| Let's Encrypt certbot | пакет ОС на сервере | сертификат HTTPS | Apache-2.0 |
| GitHub Actions | - | CI и деплой | - |

## Серверная часть (`backend/requirements.txt`)

| Библиотека | Версия | Назначение |
| --- | --- | --- |
| FastAPI | 0.141.1 | REST API, схема OpenAPI, Swagger UI и ReDoc |
| Starlette | 1.6.0 | основа FastAPI (зависимость) |
| Uvicorn (`uvicorn[standard]`: uvloop, httptools) | 0.53.0 | ASGI-сервер, несколько рабочих процессов |
| SQLAlchemy (asyncio) | 2.0.54 | модели и запросы к PostgreSQL |
| asyncpg | 0.30.0 | асинхронный драйвер PostgreSQL |
| greenlet | 3.5.6 | мост синхронного ядра SQLAlchemy и asyncio (зависимость) |
| Alembic | 1.20.0 | миграции схемы базы |
| Pydantic | 2.13.5 | схемы запросов и ответов, проверка данных |
| pydantic-settings | 2.15.0 | настройки из переменных окружения |
| python-multipart | 0.0.32 | загрузка файлов (вложения, Excel, JSON) |
| HTTPX | 0.28.1 | запросы к LMS, сайту и Admin API Keycloak |
| PyJWT (`[crypto]`, cryptography 50.0.1) | 2.14.0 | проверка токенов Keycloak по ключам реалма |
| openpyxl | 3.1.5 | чтение каталогов XLSX, выгрузка отчётов XLSX с диаграммами Excel |
| xlrd | 2.0.2 | чтение каталогов в формате Excel 97 (XLS) |
| xlwt | 1.3.0 | выгрузка отчётов в формате Excel 97 (XLS) |
| ReportLab | 4.5.1 | отчёты и диаграммы в PDF |
| Pillow | 12.3.0 | диаграммы в PNG |

Для разработки (`backend/requirements-dev.txt`): pytest 8, pytest-asyncio,
Ruff - тесты и стиль.

## Клиентская часть (`frontend/package.json`)

| Библиотека | Версия | Назначение | Лицензия |
| --- | --- | --- | --- |
| React, React DOM | 18.3.1 | интерфейс | MIT |
| @atomaro/ui-kit | 0.1.3 | дизайн-система Ростелекома Atomaro: кнопки, поля, вкладки, бейджи, уведомления | ISC |
| styled-components | 6.5.3 | стили компонентов Atomaro (зависимость набора) | MIT |
| React Router | 6.30.6 | страницы и адреса без перезагрузки | MIT |
| TanStack Query | 5.103.2 | запросы к API, кэш на клиенте, фоновое обновление | MIT |
| keycloak-js | 26.2.4 | вход через Keycloak (Authorization Code + PKCE) | Apache-2.0 |
| lucide-react | 0.468.0 | иконки | ISC |
| @fontsource/manrope | 5.3.0 | шрифт Manrope дизайн-системы (раздаётся со стенда) | OFL-1.1 |

Для разработки: TypeScript 5.9, Vite 6 (сборка), Vitest 3 (тесты),
ESLint 9 с typescript-eslint и eslint-plugin-react-hooks, Prettier 3,
openapi-typescript 7 (типы API из `docs/openapi.json`).

Диаграммы в интерфейсе нарисованы на SVG и CSS без сторонних библиотек
графиков; файлы диаграмм PNG и PDF строит сервер (Pillow, ReportLab).
