"""Импорт каталогов из XLS и XLSX.

Порядок работы соответствует разделу 6.2 концепции: файл загружается,
показывается предпросмотр с сопоставлением колонок, данные проверяются
с выводом ошибок, и только потом выполняется импорт. Итог - сколько строк
создано, обновлено и отклонено.

Сопоставление колонок не зашито: система предлагает его по заголовкам
файла, а пользователь может поправить. Набор полей сводного каталога взят
из требования 1 ТЗ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.enums import ImplementationStatus, ImportType
from app.models.catalog import ItDirection, ItProduct, ItProgram, Vendor
from app.models.contract import Contract, ContractProduct, License
from app.models.university import University, UniversityContact
from app.models.user import User

MAX_PREVIEW_ROWS = 20
MAX_ROWS = 5000


@dataclass(frozen=True, slots=True)
class FieldSpec:
    key: str
    title: str
    aliases: tuple[str, ...] = ()
    required: bool = False

    @property
    def variants(self) -> tuple[str, ...]:
        return (self.title, *self.aliases)


@dataclass(frozen=True, slots=True)
class ImportSpec:
    import_type: ImportType
    title: str
    description: str
    fields: tuple[FieldSpec, ...]

    def field(self, key: str) -> FieldSpec | None:
        return next((item for item in self.fields if item.key == key), None)


# Сводный каталог из требования 1 ТЗ - те же десять колонок.
CATALOG_SPEC = ImportSpec(
    import_type=ImportType.CATALOG,
    title="Сводный каталог",
    description=(
        "Вузы, ИТ-продукты, договоры и лицензии одной таблицей - набор полей "
        "из требования 1 технического задания."
    ),
    fields=(
        FieldSpec("university_name", "Название ВУЗа", ("Вуз", "ВУЗ"), required=True),
        FieldSpec("vendor", "Вендор", ("Производитель",)),
        FieldSpec("product", "ПО", ("Продукт", "ИТ-продукт")),
        FieldSpec("contract_number", "Номер договора", ("Договор",), required=True),
        FieldSpec("license_signed_at", "Подписание лицензии", ("Дата подписания лицензии",)),
        FieldSpec("license_valid_to", "Срок действия лицензии (год)", ("Срок лицензии",)),
        FieldSpec("transfer_status", "Статус по передачи", ("Статус передачи", "Статус")),
        FieldSpec("manager_name", "ФИО Менеджера", ("Менеджер", "Ответственный")),
        FieldSpec("contact_name", "Ответственные от ВУЗа", ("Контактное лицо",)),
        FieldSpec("comment", "Комментарий", ("Примечание",)),
    ),
)

UNIVERSITY_SPEC = ImportSpec(
    import_type=ImportType.UNIVERSITIES,
    title="Вузы",
    description="Справочник вузов с городом и закреплённым менеджером.",
    fields=(
        FieldSpec("name", "Название ВУЗа", ("Вуз", "Наименование"), required=True),
        FieldSpec("short_name", "Сокращение", ("Краткое название",)),
        FieldSpec("city", "Город", ()),
        FieldSpec("website", "Сайт", ("Веб-сайт",)),
        FieldSpec("manager_name", "ФИО Менеджера", ("Менеджер",)),
    ),
)

PROGRAM_SPEC = ImportSpec(
    import_type=ImportType.PROGRAMS,
    title="ИТ-программы",
    description="Справочник программ обучения с ИТ-направлениями.",
    fields=(
        FieldSpec("name", "Название программы", ("Программа",), required=True),
        FieldSpec("direction", "ИТ-направление", ("Направление",)),
        FieldSpec("description", "Описание", ()),
    ),
)

PRODUCT_SPEC = ImportSpec(
    import_type=ImportType.PRODUCTS,
    title="ИТ-продукты",
    description="Справочник ИТ-продуктов с вендорами.",
    fields=(
        FieldSpec("name", "Название продукта", ("ПО", "Продукт"), required=True),
        FieldSpec("vendor", "Вендор", ("Производитель",)),
        FieldSpec("description", "Описание", ()),
    ),
)

SPECS: dict[ImportType, ImportSpec] = {
    spec.import_type: spec
    for spec in (CATALOG_SPEC, UNIVERSITY_SPEC, PROGRAM_SPEC, PRODUCT_SPEC)
}

TRANSFER_STATUSES: dict[str, ImplementationStatus] = {
    "не начато": ImplementationStatus.NOT_STARTED,
    "не начат": ImplementationStatus.NOT_STARTED,
    "нет": ImplementationStatus.NOT_STARTED,
    "в работе": ImplementationStatus.IN_PROGRESS,
    "в процессе": ImplementationStatus.IN_PROGRESS,
    "передаётся": ImplementationStatus.IN_PROGRESS,
    "передается": ImplementationStatus.IN_PROGRESS,
    "внедрено": ImplementationStatus.IMPLEMENTED,
    "передано": ImplementationStatus.IMPLEMENTED,
    "завершено": ImplementationStatus.IMPLEMENTED,
    "да": ImplementationStatus.IMPLEMENTED,
    "приостановлено": ImplementationStatus.SUSPENDED,
    "пауза": ImplementationStatus.SUSPENDED,
}


@dataclass(slots=True)
class RowError:
    row_number: int
    field_name: str | None
    message: str


@dataclass(slots=True)
class SheetData:
    headers: list[str]
    rows: list[list[Any]]


@dataclass(slots=True)
class ImportOutcome:
    created: int = 0
    updated: int = 0
    failed: int = 0
    errors: list[RowError] = field(default_factory=list)


# --- Чтение файла -------------------------------------------------------------


def _normalize(text: str) -> str:
    """Заголовок без регистра, лишних пробелов и знаков препинания."""
    return re.sub(r"[\s_.,:;()]+", " ", str(text)).strip().lower()


def read_sheet(path: Path) -> SheetData:
    """Читает первый лист книги. XLSX открывает openpyxl, XLS - xlrd."""
    if path.suffix.lower() == ".xls":
        return _read_xls(path)
    return _read_xlsx(path)


def _read_xlsx(path: Path) -> SheetData:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - причина уходит пользователю
        raise AppError(
            f"Не удалось прочитать файл: {exc}", code=ErrorCode.IMPORT_FAILED
        ) from exc

    try:
        sheet = workbook.worksheets[0]
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()
    return _split(rows)


def _read_xls(path: Path) -> SheetData:
    import xlrd

    try:
        book = xlrd.open_workbook(path)
    except Exception as exc:  # noqa: BLE001 - причина уходит пользователю
        raise AppError(
            f"Не удалось прочитать файл: {exc}", code=ErrorCode.IMPORT_FAILED
        ) from exc

    sheet = book.sheet_by_index(0)
    rows: list[list[Any]] = []
    for index in range(sheet.nrows):
        values: list[Any] = []
        for column in range(sheet.ncols):
            cell = sheet.cell(index, column)
            if cell.ctype == xlrd.XL_CELL_DATE:
                values.append(xlrd.xldate_as_datetime(cell.value, book.datemode))
            else:
                values.append(cell.value)
        rows.append(values)
    return _split(rows)


def _split(rows: list[list[Any]]) -> SheetData:
    """Первая непустая строка - заголовки, остальное - данные."""
    start = next(
        (index for index, row in enumerate(rows) if any(_text(cell) for cell in row)),
        None,
    )
    if start is None:
        raise AppError("Файл пустой", code=ErrorCode.IMPORT_FAILED)

    headers = [_text(cell) for cell in rows[start]]
    body = [row for row in rows[start + 1 :] if any(_text(cell) for cell in row)]
    if len(body) > MAX_ROWS:
        raise AppError(
            f"В файле больше {MAX_ROWS} строк, разделите его на части",
            code=ErrorCode.IMPORT_FAILED,
        )
    return SheetData(headers=headers, rows=body)


# --- Сопоставление колонок ----------------------------------------------------


def suggest_mapping(spec: ImportSpec, headers: list[str]) -> dict[str, str | None]:
    """Предлагает сопоставление «поле системы -> заголовок файла»."""
    normalized = {_normalize(header): header for header in headers if header}
    mapping: dict[str, str | None] = {}
    for item in spec.fields:
        match = None
        for variant in item.variants:
            match = normalized.get(_normalize(variant))
            if match:
                break
        mapping[item.key] = match
    return mapping


def check_mapping(
    spec: ImportSpec, mapping: dict[str, str | None], headers: list[str]
) -> None:
    known = {header for header in headers if header}
    for item in spec.fields:
        column = mapping.get(item.key)
        if item.required and not column:
            raise AppError(
                f"Не сопоставлена обязательная колонка «{item.title}»",
                code=ErrorCode.IMPORT_FAILED,
            )
        if column and column not in known:
            raise AppError(
                f"Колонки «{column}» нет в файле",
                code=ErrorCode.IMPORT_FAILED,
            )


def _row_reader(mapping: dict[str, str | None], headers: list[str]):
    """Возвращает функцию «строка, поле -> значение»."""
    index_by_header = {header: index for index, header in enumerate(headers) if header}
    index_by_key = {
        key: index_by_header[column]
        for key, column in mapping.items()
        if column and column in index_by_header
    }

    def value(row: list[Any], key: str) -> Any:
        index = index_by_key.get(key)
        if index is None or index >= len(row):
            return None
        return row[index]

    return value


# --- Разбор значений ----------------------------------------------------------


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def cell_text(value: Any) -> str:
    """Значение ячейки строкой: нужно предпросмотру при загрузке файла."""
    return _text(value)


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    for pattern in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"не похоже на дату: «{text}»")


def parse_license_valid_to(value: Any, signed_at: date | None) -> date | None:
    """«Срок действия лицензии (год)» приходит по-разному.

    Встречается и полная дата, и год окончания, и просто срок в годах -
    разбираем все три варианта, иначе колонку невозможно загрузить.
    """
    if value in (None, ""):
        return None
    if isinstance(value, datetime | date):
        return parse_date(value)

    text = _text(value)
    digits = re.sub(r"[^\d]", "", text)
    if digits and len(digits) == 4:  # год окончания
        return date(int(digits), 12, 31)
    if digits and int(digits) <= 20:  # срок в годах от даты подписания
        start = signed_at or date.today()
        years = int(digits)
        try:
            return start.replace(year=start.year + years)
        except ValueError:  # 29 февраля
            return start.replace(year=start.year + years, day=28)
    return parse_date(value)


def parse_transfer_status(value: Any) -> ImplementationStatus | None:
    if value in (None, ""):
        return None
    text = _normalize(_text(value))
    if not text:
        return None
    status = TRANSFER_STATUSES.get(text)
    if status is None:
        raise ValueError(f"неизвестный статус «{_text(value)}»")
    return status


# --- Импорт -------------------------------------------------------------------


async def _get_or_create_by_name(session: AsyncSession, model, name: str, **extra):
    """Справочники сопоставляются по названию без учёта регистра."""
    found = await session.scalar(
        select(model).where(func.lower(model.name) == name.lower()).limit(1)
    )
    if found is not None:
        return found, False
    created = model(name=name, **extra)
    session.add(created)
    await session.flush()
    return created, True


async def _find_user(session: AsyncSession, full_name: str) -> User | None:
    if not full_name:
        return None
    return await session.scalar(
        select(User).where(func.lower(User.full_name) == full_name.lower()).limit(1)
    )


async def _import_catalog(
    session: AsyncSession, sheet: SheetData, mapping: dict[str, str | None]
) -> ImportOutcome:
    outcome = ImportOutcome()
    value = _row_reader(mapping, sheet.headers)

    for offset, row in enumerate(sheet.rows, start=2):
        try:
            university_name = _text(value(row, "university_name"))
            contract_number = _text(value(row, "contract_number"))
            if not university_name or not contract_number:
                raise ValueError("не заполнены название вуза или номер договора")

            university, _ = await _get_or_create_by_name(session, University, university_name)

            manager_name = _text(value(row, "manager_name"))
            manager = await _find_user(session, manager_name)
            if manager_name and manager is None:
                outcome.errors.append(
                    RowError(
                        offset,
                        "ФИО Менеджера",
                        f"Предупреждение: сотрудник «{manager_name}» не найден, "
                        "договор загружен без ответственного",
                    )
                )

            contract = await session.scalar(
                select(Contract).where(
                    Contract.university_id == university.id,
                    Contract.number == contract_number,
                )
            )
            if contract is None:
                contract = Contract(
                    university_id=university.id,
                    number=contract_number,
                    manager_id=manager.id if manager else None,
                    comment=_text(value(row, "comment")) or None,
                )
                session.add(contract)
                await session.flush()
                outcome.created += 1
            else:
                if manager is not None:
                    contract.manager_id = manager.id
                comment = _text(value(row, "comment"))
                if comment:
                    contract.comment = comment
                outcome.updated += 1

            await _import_contact(session, university, _text(value(row, "contact_name")))
            await _import_product_and_license(session, contract, row, value)

        except ValueError as exc:
            outcome.failed += 1
            outcome.errors.append(RowError(offset, None, str(exc)))

    return outcome


async def _import_contact(
    session: AsyncSession, university: University, full_name: str
) -> None:
    if not full_name:
        return
    existing = await session.scalar(
        select(UniversityContact).where(
            UniversityContact.university_id == university.id,
            func.lower(UniversityContact.full_name) == full_name.lower(),
        )
    )
    if existing is None:
        session.add(
            UniversityContact(university_id=university.id, full_name=full_name)
        )
        await session.flush()


async def _import_product_and_license(
    session: AsyncSession, contract: Contract, row: list[Any], value
) -> None:
    product_name = _text(value(row, "product"))
    if not product_name:
        return

    vendor_name = _text(value(row, "vendor"))
    vendor = None
    if vendor_name:
        vendor, _ = await _get_or_create_by_name(session, Vendor, vendor_name)
    product, _ = await _get_or_create_by_name(
        session, ItProduct, product_name, vendor_id=vendor.id if vendor else None
    )
    if vendor is not None and product.vendor_id is None:
        product.vendor_id = vendor.id

    link = await session.scalar(
        select(ContractProduct).where(
            ContractProduct.contract_id == contract.id,
            ContractProduct.product_id == product.id,
        )
    )
    if link is None:
        link = ContractProduct(contract_id=contract.id, product_id=product.id)
        session.add(link)
        await session.flush()

    status = parse_transfer_status(value(row, "transfer_status"))
    if status is not None:
        link.transfer_status = status

    signed_at = parse_date(value(row, "license_signed_at"))
    valid_to = parse_license_valid_to(value(row, "license_valid_to"), signed_at)
    if signed_at is None and valid_to is None:
        return

    license_ = await session.scalar(
        select(License).where(License.contract_product_id == link.id).limit(1)
    )
    if license_ is None:
        session.add(
            License(
                contract_product_id=link.id, signed_at=signed_at, valid_to=valid_to
            )
        )
    else:
        license_.signed_at = signed_at or license_.signed_at
        license_.valid_to = valid_to or license_.valid_to
    await session.flush()


async def _import_universities(
    session: AsyncSession, sheet: SheetData, mapping: dict[str, str | None]
) -> ImportOutcome:
    outcome = ImportOutcome()
    value = _row_reader(mapping, sheet.headers)

    for offset, row in enumerate(sheet.rows, start=2):
        name = _text(value(row, "name"))
        if not name:
            outcome.failed += 1
            outcome.errors.append(RowError(offset, "Название ВУЗа", "не заполнено"))
            continue

        university, created = await _get_or_create_by_name(session, University, name)
        university.short_name = _text(value(row, "short_name")) or university.short_name
        university.city = _text(value(row, "city")) or university.city
        university.website = _text(value(row, "website")) or university.website

        manager = await _find_user(session, _text(value(row, "manager_name")))
        if manager is not None:
            university.manager_id = manager.id

        outcome.created += int(created)
        outcome.updated += int(not created)
    await session.flush()
    return outcome


async def _import_programs(
    session: AsyncSession, sheet: SheetData, mapping: dict[str, str | None]
) -> ImportOutcome:
    outcome = ImportOutcome()
    value = _row_reader(mapping, sheet.headers)

    for offset, row in enumerate(sheet.rows, start=2):
        name = _text(value(row, "name"))
        if not name:
            outcome.failed += 1
            outcome.errors.append(RowError(offset, "Название программы", "не заполнено"))
            continue

        direction = None
        direction_name = _text(value(row, "direction"))
        if direction_name:
            direction, _ = await _get_or_create_by_name(session, ItDirection, direction_name)

        program, created = await _get_or_create_by_name(session, ItProgram, name)
        program.description = _text(value(row, "description")) or program.description
        if direction is not None:
            program.direction_id = direction.id

        outcome.created += int(created)
        outcome.updated += int(not created)
    await session.flush()
    return outcome


async def _import_products(
    session: AsyncSession, sheet: SheetData, mapping: dict[str, str | None]
) -> ImportOutcome:
    outcome = ImportOutcome()
    value = _row_reader(mapping, sheet.headers)

    for offset, row in enumerate(sheet.rows, start=2):
        name = _text(value(row, "name"))
        if not name:
            outcome.failed += 1
            outcome.errors.append(RowError(offset, "Название продукта", "не заполнено"))
            continue

        vendor = None
        vendor_name = _text(value(row, "vendor"))
        if vendor_name:
            vendor, _ = await _get_or_create_by_name(session, Vendor, vendor_name)

        product, created = await _get_or_create_by_name(session, ItProduct, name)
        product.description = _text(value(row, "description")) or product.description
        if vendor is not None:
            product.vendor_id = vendor.id

        outcome.created += int(created)
        outcome.updated += int(not created)
    await session.flush()
    return outcome


IMPORTERS = {
    ImportType.CATALOG: _import_catalog,
    ImportType.UNIVERSITIES: _import_universities,
    ImportType.PROGRAMS: _import_programs,
    ImportType.PRODUCTS: _import_products,
}


def validate(
    spec: ImportSpec, sheet: SheetData, mapping: dict[str, str | None]
) -> list[RowError]:
    """Проверка без записи в базу: даты, статусы и обязательные поля."""
    check_mapping(spec, mapping, sheet.headers)
    value = _row_reader(mapping, sheet.headers)
    errors: list[RowError] = []

    for offset, row in enumerate(sheet.rows, start=2):
        for item in spec.fields:
            raw = value(row, item.key)
            if item.required and not _text(raw):
                errors.append(RowError(offset, item.title, "обязательное поле не заполнено"))
                continue
            try:
                if item.key in {"license_signed_at"}:
                    parse_date(raw)
                elif item.key == "license_valid_to":
                    parse_license_valid_to(raw, None)
                elif item.key == "transfer_status":
                    parse_transfer_status(raw)
            except ValueError as exc:
                errors.append(RowError(offset, item.title, str(exc)))
    return errors


async def run_import(
    session: AsyncSession,
    spec: ImportSpec,
    sheet: SheetData,
    mapping: dict[str, str | None],
) -> ImportOutcome:
    check_mapping(spec, mapping, sheet.headers)
    return await IMPORTERS[spec.import_type](session, sheet, mapping)


def build_template(spec: ImportSpec) -> bytes:
    """Пустой файл-образец с нужными заголовками."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = spec.title[:31]
    for index, item in enumerate(spec.fields, start=1):
        cell = sheet.cell(row=1, column=index, value=item.title)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="F0EFEC")
        sheet.column_dimensions[cell.column_letter].width = max(len(item.title) + 4, 16)
        if item.required:
            sheet.cell(row=2, column=index, value="обязательное поле").font = Font(
                italic=True, color="898781"
            )

    from io import BytesIO

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
