"""Файлы для ручной проверки загрузок: импорт каталогов и вложения.

Запуск:
    python -m scripts.testdata ../testdata      # из каталога backend
    make testdata                               # то же в контейнере разработки

Кладёт в каталог:

    import/        таблицы для импорта каталогов (требование 1 ТЗ)
    attachments/   по файлу каждого формата вложений из ТЗ и один недопустимый

Что в каждом файле и чего ждать от загрузки - в testdata/README.md.
Для .xls нужен xlwt из requirements-dev.txt.
"""

import argparse
from collections.abc import Callable
from pathlib import Path

from scripts.demo import files, sheets

# файл -> (название листа, таблица, формат)
IMPORTS: dict[str, tuple[str, Callable[[], sheets.Sheet], str]] = {
    "01-catalog.xlsx": ("Сводный каталог", sheets.catalog, "xlsx"),
    "02-catalog.xls": ("Сводный каталог", sheets.catalog, "xls"),
    "03-catalog-other-headers.xlsx": ("Каталог", sheets.catalog_other_headers, "xlsx"),
    "04-catalog-errors.xlsx": ("Каталог с ошибками", sheets.catalog_errors, "xlsx"),
    "05-universities.xlsx": ("Вузы", sheets.universities, "xlsx"),
    "06-programs.xlsx": ("ИТ-программы", sheets.programs, "xlsx"),
    "07-products.xlsx": ("ИТ-продукты", sheets.products, "xlsx"),
}

_LINES = (
    "Вуз: Московский технический университет связи и информатики",
    "Договор: ДГ-2025-017",
    "Программы: Python-разработчик, Инженер по тестированию",
    "Ответственный ИТ Школы: Петров Пётр Алексеевич",
    "Представитель вуза: см. карточку вуза",
)

_TEACHERS = (
    ("ФИО", "Должность", "Курс пройден"),
    [
        ("Гусева Анна Петровна", "Доцент кафедры", "да"),
        ("Тарасов Олег Юрьевич", "Старший преподаватель", "да"),
        ("Власова Ирина Николаевна", "Ассистент", "нет"),
    ],
)
_CURRICULUM = (
    ("Модуль", "Часы", "Форма контроля"),
    [
        ("Основы и инструменты", 36, "Зачёт"),
        ("Практикум на учебном стенде", 72, "Проект"),
        ("Промышленные практики", 36, "Экзамен"),
    ],
)

# файл -> (формат, заголовок документа, таблица для xlsx/xls)
ATTACHMENTS: dict[str, tuple[str, str, files.Table | None]] = {
    "meeting-protocol.pdf": ("pdf", "Протокол встречи с вузом", None),
    "signed-contract-scan.jpeg": ("jpeg", "Скан подписанного договора", None),
    "stand-diagram.png": ("png", "Схема учебного стенда", None),
    "contract-draft.docx": ("docx", "Проект договора", None),
    "contract-university-edition.doc": ("doc", "Договор — редакция вуза", None),
    "teachers.xlsx": ("xlsx", "Список обученных преподавателей", _TEACHERS),
    "curriculum.xls": ("xls", "Учебный план", _CURRICULUM),
    "materials.zip": ("zip", "Методические материалы", None),
    "deploy-log.gz": ("gz", "Журнал развёртывания стенда", None),
    "methodology.rar": ("rar", "Методические материалы", None),
}


def write(target: Path) -> list[Path]:
    written: list[Path] = []

    folder = target / "import"
    folder.mkdir(parents=True, exist_ok=True)
    for name, (title, build, kind) in IMPORTS.items():
        headers, rows = build()
        writer = files.xlsx if kind == "xlsx" else files.xls
        path = folder / name
        path.write_bytes(writer(title, headers, rows))
        written.append(path)

    folder = target / "attachments"
    folder.mkdir(parents=True, exist_ok=True)
    for name, (kind, title, table) in ATTACHMENTS.items():
        path = folder / name
        path.write_bytes(files.document(kind, title, _LINES, table))
        written.append(path)

    # Недопустимый формат: загрузка должна отказать с кодом file_type_not_allowed.
    path = folder / "not-allowed.txt"
    path.write_text("Текстовые файлы во вложения не принимаются.\n", encoding="utf-8")
    written.append(path)
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Файлы для ручной проверки загрузок")
    parser.add_argument("target", type=Path, help="куда положить файлы")
    for path in write(parser.parse_args().target):
        print(path)
