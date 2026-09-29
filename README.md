# Система контроля взаимодействия ИТ Школы Ростелекома с вузами

Веб-система для сотрудников ИТ Школы Ростелекома, которые работают с вузами.
Центральный объект системы **взаимодействие с вузом**. У взаимодействия есть
вуз, ответственный менеджер, рабочий процесс по этапам, ИТ-программы и продукты,
контакты, файлы и история. Кроме того, в системе есть отчёты, статистика
обучения, обмен с LMS и сайтом и загрузка каталогов из Excel.

- Соответствие ТЗ по пунктам: [docs/project/requirements.md](docs/project/requirements.md)
- Библиотеки и версии: [docs/project/libraries.md](docs/project/libraries.md)
- Решения по бизнес-модели: [docs/project/business-model-decisions.md](docs/project/business-model-decisions.md)
- Архитектурные схемы и модель ArchiMate: [docs/architecture](docs/architecture)
- Сопроводительная документация: [PDF](docs/edu_crm_documentation.pdf)
- Руководства менеджера, руководителя, администратора и системного
  администратора встроены в систему, раздел «Руководства»

## Запуск

Нужны Docker и make.

```bash
make build   # собрать образы
make up      # контейнеры и миграции
```

Система откроется на http://localhost:3000, Swagger UI на http://localhost:8000/docs.

## Запуск без Docker

Нужны Python 3.12, Node.js 22 и PostgreSQL 16.

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # указать свой PostgreSQL
alembic upgrade head
uvicorn app.main:app --reload     # API на http://localhost:8000
```

Клиентская часть в соседнем терминале, откроется на http://localhost:5173:

```bash
cd frontend
npm ci
npm run dev
```

## Команды

Полный список показывает `make help`.

| Команда | Что делает |
| --- | --- |
| `make down` | остановить |
| `make logs` | логи API |
| `make reset` | удалить контейнеры вместе с данными и собрать заново |
| `make test` | тесты API |
| `make check` | стиль, тесты, сверка моделей с миграциями |

Тесты клиентской части: `npm test` в `frontend/`.

## Стек

| Компонент | Решение |
| --- | --- |
| Клиентская часть | React 18, TypeScript, Vite, дизайн-система Ростелекома Atomaro |
| API | Python 3.12, FastAPI |
| База данных | PostgreSQL 16, SQLAlchemy 2 (async), миграции Alembic |
| Вход | Keycloak 26 (OIDC, PKCE), в разработке заглушка |
