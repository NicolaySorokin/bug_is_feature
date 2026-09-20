"""Выгрузка схемы API в файл.

Запуск через make:  make openapi

Схема нужна клиентской части: по ней генерируются типы и клиент, и её
удобно смотреть в отрыве от поднятого стенда. Живая версия всегда доступна
по адресу /api/v1/openapi.json, файл в репозитории - её слепок.

CI сверяет слепок с кодом: если API изменился, а файл не обновили,
сборка падает - значит, фронтенд не узнал бы об изменении контракта.
"""

import json

from app.main import app


def main() -> None:
    schema = app.openapi()
    print(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
