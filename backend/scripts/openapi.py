"""Выгрузка схемы API в docs/openapi.json: make openapi.

По файлу генерируются типы клиента, CI проверяет, что он не отстал от кода.
"""

import json

from app.main import app


def main() -> None:
    schema = app.openapi()
    print(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
