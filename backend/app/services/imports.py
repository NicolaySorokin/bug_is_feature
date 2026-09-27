"""Импорт каталогов из XLS и XLSX.

Порядок работы соответствует разделу 6.2 концепции: файл загружается,
показывается предпросмотр с сопоставлением колонок, данные проверяются
с выводом ошибок, и только потом выполняется импорт. Итог - сколько строк
создано, обновлено и отклонено.

Сопоставление колонок не зашито: система предлагает его по заголовкам
файла, а пользователь может поправить. Набор полей сводного каталога взят
из требования 1 ТЗ, каталог вендоров и анкета обучающегося LMS - из файлов,
переданных кейсодержателем.

Каждая строка загружается в своей точке сохранения (SAVEPOINT) и только
после проверки всех её значений: строка с ошибкой не оставляет после себя
наполовину заведённых вуза или взаимодействия, а остальные строки
загружаются.

Сводный каталог загружается через целевую модель (пункт 12 перечня
исправлений): строка - это взаимодействие с вузом и его договор; продукт
добавляется только вместе с ИТ-программой - из колонки «ИТ-программа»
или по справочному соответствию программ и продуктов. Строка, где
программу определить нельзя, отклоняется с понятной причиной.
Новый вуз из файла заводится «На проверке» - его подтверждает руководитель.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.enums import (
    ImportType,
    InteractionSource,
    InteractionStatus,
    ProductTransferStatus,
    Role,
    UniversityStatus,
)
from app.models.catalog import (
    ItDirection,
    ItProduct,
    ItProgram,
    ProgramProduct,
    Vendor,
    VendorContact,
)
from app.models.contract import Contract, License
from app.models.interaction import (
    InteractionContact,
    InteractionProduct,
    InteractionProgram,
    InteractionProgramProduct,
)
from app.models.learning import Learner
from app.models.university import University, UniversityContact
from app.models.user import User
from app.models.workflow import WorkflowInstance
from app.services import licenses as license_service
from app.services import workflow as workflow_service
from app.services.integrations.base import normalize_email, normalize_phone

MAX_PREVIEW_ROWS = 20
MAX_ROWS = 5000
# Роль, с которой контакт из каталога назначается ответственным по взаимодействию.
CONTRACT_CONTACT_ROLE = "Ответственный от вуза"


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
        "Вузы, взаимодействия с договорами, ИТ-продукты и лицензии одной таблицей - "
        "набор полей из требования 1 технического задания. Колонка «ИТ-программа» "
        "необязательна: без неё программа продукта берётся из справочного "
        "соответствия программ и продуктов."
    ),
    fields=(
        FieldSpec("university_name", "Название ВУЗа", ("Вуз", "ВУЗ"), required=True),
        FieldSpec("vendor", "Вендор", ("Производитель",)),
        FieldSpec("product", "ПО", ("Продукт", "ИТ-продукт")),
        FieldSpec("program", "ИТ-программа", ("Программа", "Курс")),
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
    description=(
        "Справочник вузов с городом и менеджером по умолчанию. Вуз узнаётся по ИНН, "
        "а без ИНН - по полному или краткому названию; новый вуз ждёт проверки."
    ),
    fields=(
        FieldSpec("name", "Название ВУЗа", ("Вуз", "Наименование"), required=True),
        FieldSpec("inn", "ИНН", ("ИНН вуза",)),
        FieldSpec("short_name", "Сокращение", ("Краткое название",)),
        FieldSpec("city", "Город", ()),
        FieldSpec("website", "Сайт", ("Веб-сайт",)),
        FieldSpec("manager_name", "ФИО Менеджера", ("Менеджер",)),
    ),
)

CONTACT_SPEC = ImportSpec(
    import_type=ImportType.CONTACTS,
    title="Ответственные от вузов",
    description=(
        "Контактные лица вузов: кто ведёт сотрудничество со стороны вуза. "
        "Вуз должен уже быть в справочнике."
    ),
    fields=(
        FieldSpec("university_name", "Название ВУЗа", ("Вуз", "ВУЗ"), required=True),
        FieldSpec("full_name", "ФИО", ("Ответственный", "Контактное лицо"), required=True),
        FieldSpec("position", "Должность", ()),
        FieldSpec("phone", "Телефон", ("Номер телефона",)),
        FieldSpec("email", "Почта", ("Email", "Электронная почта")),
    ),
)

PROGRAM_SPEC = ImportSpec(
    import_type=ImportType.PROGRAMS,
    title="ИТ-программы",
    description="Справочник программ обучения с ИТ-направлениями.",
    fields=(
        FieldSpec("name", "Название программы", ("Программа", "Курс"), required=True),
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
        FieldSpec("vendor", "Вендор", ("Производитель", "Компания")),
        FieldSpec("description", "Описание", ()),
    ),
)

# Формат каталога «Вендоры», переданного кейсодержателем.
VENDOR_SPEC = ImportSpec(
    import_type=ImportType.VENDORS,
    title="Вендоры",
    description=(
        "Компании-вендоры, их ИТ-продукты и ответственные со стороны вендора. "
        "В колонке «Продукт» можно перечислить несколько продуктов через запятую."
    ),
    fields=(
        FieldSpec("company", "Компания", ("Вендор", "Производитель"), required=True),
        FieldSpec("products", "Продукт", ("Продукты", "ПО", "ИТ-продукт")),
        FieldSpec("full_name", "ФИО", ("Контактное лицо", "Ответственный")),
        FieldSpec("phone", "Телефон", ("Номер телефона",)),
        FieldSpec("email", "Почта", ("Email", "Электронная почта")),
        FieldSpec("contact_channel", "Способ связи", ("Канал связи",)),
    ),
)

# Анкета обучающегося LMS (формат кейсодержателя). Из тридцати колонок
# анкеты берутся только эти: паспорт, СНИЛС, адрес и диплом не нужны для
# статистики и в систему не загружаются - принцип минимизации 152-ФЗ.
LEARNER_SPEC = ImportSpec(
    import_type=ImportType.LEARNERS,
    title="Обучающиеся (анкеты LMS)",
    description=(
        "Анкеты слушателей из LMS. Загружаются только ФИО, телефон, почта, пол, "
        "образование и регион - паспортные данные, СНИЛС, адрес и сведения "
        "о дипломе не сохраняются (минимизация персональных данных, 152-ФЗ)."
    ),
    fields=(
        FieldSpec("last_name", "Фамилия", (), required=True),
        FieldSpec("first_name", "Имя", (), required=True),
        FieldSpec("middle_name", "Отчество (при наличии)", ("Отчество",)),
        FieldSpec("phone", "Номер телефона", ("Телефон",)),
        FieldSpec("email", "Email", ("Почта", "Электронная почта")),
        FieldSpec("gender", "Пол", ()),
        FieldSpec("education", "Образование", ("Уровень образования",)),
        FieldSpec("region", "Регион регистрации", ("Регион",)),
    ),
)

SPECS: dict[ImportType, ImportSpec] = {
    spec.import_type: spec
    for spec in (
        CATALOG_SPEC,
        UNIVERSITY_SPEC,
        CONTACT_SPEC,
        PROGRAM_SPEC,
        PRODUCT_SPEC,
        VENDOR_SPEC,
        LEARNER_SPEC,
    )
}

TRANSFER_STATUSES: dict[str, ProductTransferStatus] = {
    "неначато": ProductTransferStatus.NOT_STARTED,
    "неначата": ProductTransferStatus.NOT_STARTED,
    "неначат": ProductTransferStatus.NOT_STARTED,
    "нет": ProductTransferStatus.NOT_STARTED,
    "вработе": ProductTransferStatus.IN_PROGRESS,
    "впроцессе": ProductTransferStatus.IN_PROGRESS,
    "выполняется": ProductTransferStatus.IN_PROGRESS,
    "передаётся": ProductTransferStatus.IN_PROGRESS,
    "передается": ProductTransferStatus.IN_PROGRESS,
    "внедрено": ProductTransferStatus.TRANSFERRED,
    "передано": ProductTransferStatus.TRANSFERRED,
    "передан": ProductTransferStatus.TRANSFERRED,
    "завершено": ProductTransferStatus.TRANSFERRED,
    "да": ProductTransferStatus.TRANSFERRED,
    "приостановлено": ProductTransferStatus.SUSPENDED,
    "приостановлена": ProductTransferStatus.SUSPENDED,
    "пауза": ProductTransferStatus.SUSPENDED,
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
    # Номер строки листа Excel для каждой строки данных: ошибки называют
    # ту строку, которую человек увидит в файле.
    row_numbers: list[int] = field(default_factory=list)

    def numbered(self) -> list[tuple[int, list[Any]]]:
        numbers = self.row_numbers or list(range(2, len(self.rows) + 2))
        return list(zip(numbers, self.rows, strict=False))


@dataclass(slots=True)
class ImportOutcome:
    created: int = 0
    updated: int = 0
    failed: int = 0
    errors: list[RowError] = field(default_factory=list)


# --- Чтение файла -------------------------------------------------------------


def _normalize(text: str) -> str:
    """Заголовок без регистра, пробелов и знаков препинания.

    «Отчество (при наличии)» и испорченное при выгрузке «Отчествопри наличии)»
    дают одно и то же, как и «Номер договора.» с «номер договора».
    """
    return re.sub(r"[^0-9a-zа-яё]+", "", str(text).lower())


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
    body: list[list[Any]] = []
    numbers: list[int] = []
    for index in range(start + 1, len(rows)):
        if any(_text(cell) for cell in rows[index]):
            body.append(rows[index])
            numbers.append(index + 1)
    if len(body) > MAX_ROWS:
        raise AppError(
            f"В файле больше {MAX_ROWS} строк, разделите его на части",
            code=ErrorCode.IMPORT_FAILED,
        )
    return SheetData(headers=headers, rows=body, row_numbers=numbers)


# --- Сопоставление колонок ----------------------------------------------------


def suggest_mapping(spec: ImportSpec, headers: list[str]) -> dict[str, str | None]:
    """Предлагает сопоставление «поле системы -> заголовок файла»."""
    normalized: dict[str, str] = {}
    for header in headers:
        if header:
            normalized.setdefault(_normalize(header), header)
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
    index_by_header: dict[str, int] = {}
    for index, header in enumerate(headers):
        if header:
            index_by_header.setdefault(header, index)
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
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
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


def parse_transfer_status(value: Any) -> ProductTransferStatus | None:
    if value in (None, ""):
        return None
    text = _normalize(_text(value))
    if not text:
        return None
    status = TRANSFER_STATUSES.get(text)
    if status is None:
        raise ValueError(f"неизвестный статус «{_text(value)}»")
    return status


def parse_gender(value: Any) -> str | None:
    text = _text(value).upper()[:1]
    if not text:
        return None
    gender = {"М": "М", "M": "М", "Ж": "Ж", "F": "Ж", "W": "Ж"}.get(text)
    if gender is None:
        raise ValueError(f"пол указывается буквой М или Ж, а не «{_text(value)}»")
    return gender


def parse_email(value: Any) -> str | None:
    if value in (None, ""):
        return None
    email = normalize_email(value)
    if email is None:
        raise ValueError(f"не похоже на адрес почты: «{_text(value)}»")
    return email


def split_products(value: Any) -> list[str]:
    """«RT.DataLake», «RT.Warehouse» -> два названия без кавычек-ёлочек."""
    parts = re.split(r"[,;\n]+", _text(value))
    names = [part.strip().strip("«»\"' ").strip() for part in parts]
    return [name for name in names if name]


# Проверка значения по ключу поля: бросает ValueError с понятным текстом.
def parse_inn(value: Any) -> str | None:
    """ИНН: 10 цифр у организации, 12 - у физического лица и ИП (как в форме вуза)."""
    text = _text(value)
    if not text:
        return None
    if not re.fullmatch(r"\d{10}|\d{12}", text):
        raise ValueError("ИНН - 10 или 12 цифр")
    return text


PARSERS: dict[str, Callable[[Any], object]] = {
    "inn": parse_inn,
    "license_signed_at": parse_date,
    "license_valid_to": lambda value: parse_license_valid_to(value, None),
    "transfer_status": parse_transfer_status,
    "gender": parse_gender,
    "email": parse_email,
}


def row_errors(spec: ImportSpec, row: list[Any], value, number: int) -> list[RowError]:  # noqa: ANN001
    errors: list[RowError] = []
    for item in spec.fields:
        raw = value(row, item.key)
        if item.required and not _text(raw):
            errors.append(RowError(number, item.title, "обязательное поле не заполнено"))
            continue
        parser = PARSERS.get(item.key)
        if parser is None:
            continue
        try:
            parser(raw)
        except ValueError as exc:
            errors.append(RowError(number, item.title, str(exc)))
    if spec.import_type is ImportType.LEARNERS and not (
        _text(value(row, "email")) or _text(value(row, "phone"))
    ):
        errors.append(
            RowError(
                number, None, "нужен телефон или почта: по ним анкета связывается с заявкой"
            )
        )
    return errors


# --- Поиск и заведение записей ----------------------------------------------------


async def _get_or_create_by_name(session: AsyncSession, model, name: str, **extra):  # noqa: ANN001
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


async def _find_university(
    session: AsyncSession, name: str, inn: str | None = None
) -> University | None:
    """Вуз по ИНН - стабильному ключу, а без него - по полному или краткому
    названию: в файлах пишут по-разному. Одноимённый вуз с другим ИНН - это
    другой вуз, он не подменяется."""
    if inn:
        found = await session.scalar(select(University).where(University.inn == inn))
        if found is not None:
            return found
    value = name.lower()
    statement = select(University).where(
        or_(
            func.lower(University.name) == value,
            func.lower(University.short_name) == value,
        )
    )
    if inn:
        statement = statement.where(University.inn.is_(None))
    return await session.scalar(statement.limit(1))


async def _find_user(session: AsyncSession, full_name: str) -> User | None:
    if not full_name:
        return None
    return await session.scalar(
        select(User).where(func.lower(User.full_name) == full_name.lower()).limit(1)
    )


RowImporter = Callable[
    [AsyncSession, list[Any], Callable[[list[Any], str], Any], int, list[RowError]],
    Awaitable[bool],
]


async def _catalog_row(session, row, value, number, warnings) -> bool:  # noqa: ANN001
    """Строка сводного каталога: взаимодействие с договором. True - заведено новое."""
    university_name = _text(value(row, "university_name"))
    contract_number = _text(value(row, "contract_number"))

    university = await _find_university(session, university_name)
    if university is None:
        # Вуз из файла - на проверку руководителю (единый путь создания вуза).
        university = University(
            name=university_name, status=UniversityStatus.PENDING, origin="import"
        )
        session.add(university)
        await session.flush()
        warnings.append(
            RowError(
                number,
                "Название ВУЗа",
                f"Предупреждение: вуз «{university_name}» заведён на проверку - "
                "его подтвердит руководитель",
            )
        )

    manager_name = _text(value(row, "manager_name"))
    manager = await _find_user(session, manager_name)
    if manager is not None and Role.MANAGER not in (manager.roles or []):
        warnings.append(
            RowError(
                number,
                "ФИО Менеджера",
                f"Предупреждение: у сотрудника «{manager_name}» нет роли «Менеджер», "
                "ответственный не назначен",
            )
        )
        manager = None
    elif manager_name and manager is None:
        warnings.append(
            RowError(
                number,
                "ФИО Менеджера",
                f"Предупреждение: сотрудник «{manager_name}» не найден, "
                "ответственный не изменён",
            )
        )

    contract = await session.scalar(
        select(Contract)
        .join(WorkflowInstance, WorkflowInstance.id == Contract.workflow_instance_id)
        .where(
            WorkflowInstance.university_id == university.id,
            Contract.number == contract_number,
        )
    )
    created = contract is None
    comment = _text(value(row, "comment"))
    if contract is None:
        template = await workflow_service.default_template(session)
        if template is None:
            raise ValueError("нет шаблона процесса с действующей версией - опубликуйте его")
        version = await workflow_service.active_version(session, template.id)
        instance = await workflow_service.create_interaction(
            session,
            university_id=university.id,
            version=version,
            user=None,
            manager_id=(manager.id if manager else university.manager_id),
            title=f"Договор {contract_number}",
            comment=comment or None,
            source=InteractionSource.IMPORT,
        )
        contract = Contract(workflow_instance_id=instance.id, number=contract_number)
        session.add(contract)
        await session.flush()
    else:
        instance = await session.get(WorkflowInstance, contract.workflow_instance_id)
        if manager is not None and instance.status != InteractionStatus.CANCELLED:
            instance.manager_id = manager.id
        if comment:
            instance.comment = comment

    await _import_contact(session, university, instance, _text(value(row, "contact_name")))
    await _import_product_and_license(session, instance, contract, row, value)
    return created


async def _import_contact(
    session: AsyncSession, university: University, instance: WorkflowInstance, full_name: str
) -> None:
    """Ответственный от вуза: контакт вуза, назначенный во взаимодействии."""
    if not full_name:
        return
    contact = await session.scalar(
        select(UniversityContact).where(
            UniversityContact.university_id == university.id,
            func.lower(UniversityContact.full_name) == full_name.lower(),
        )
    )
    if contact is None:
        contact = UniversityContact(university_id=university.id, full_name=full_name)
        session.add(contact)
        await session.flush()
    link = await session.get(InteractionContact, (instance.id, contact.id))
    if link is None:
        session.add(
            InteractionContact(
                workflow_instance_id=instance.id,
                contact_id=contact.id,
                role=CONTRACT_CONTACT_ROLE,
            )
        )
        await session.flush()


async def _program_links_for(
    session: AsyncSession, instance: WorkflowInstance, product: ItProduct, program_name: str
) -> list[tuple[InteractionProgram, bool]]:
    """Программы взаимодействия для продукта: (связь, это исключение).

    Колонка «ИТ-программа» задаёт программу явно; без неё - справочное
    соответствие программ и продуктов.
    """

    async def ensure_program(program: ItProgram) -> InteractionProgram:
        link = await session.scalar(
            select(InteractionProgram).where(
                InteractionProgram.workflow_instance_id == instance.id,
                InteractionProgram.program_id == program.id,
            )
        )
        if link is None:
            link = InteractionProgram(workflow_instance_id=instance.id, program_id=program.id)
            session.add(link)
            await session.flush()
        return link

    catalog = set(
        (
            await session.execute(
                select(ProgramProduct.program_id).where(
                    ProgramProduct.product_id == product.id
                )
            )
        ).scalars()
    )
    if program_name:
        program = await session.scalar(
            select(ItProgram)
            .where(func.lower(ItProgram.name) == program_name.lower())
            .limit(1)
        )
        if program is None:
            raise ValueError(
                f"программы «{program_name}» нет в справочнике - загрузите её раньше"
            )
        return [(await ensure_program(program), program.id not in catalog)]

    existing = list(
        (
            await session.execute(
                select(InteractionProgram).where(
                    InteractionProgram.workflow_instance_id == instance.id,
                    InteractionProgram.program_id.in_(catalog or {None}),
                )
            )
        ).scalars()
    )
    if existing:
        return [(link, False) for link in existing]
    if len(catalog) == 1:
        program = await session.get(ItProgram, next(iter(catalog)))
        return [(await ensure_program(program), False)]
    if not catalog:
        raise ValueError(
            f"продукт «{product.name}» не связан ни с одной ИТ-программой: заполните "
            "колонку «ИТ-программа» или свяжите продукт с программой в справочнике"
        )
    raise ValueError(
        f"продукт «{product.name}» используется в нескольких программах - укажите "
        "нужную в колонке «ИТ-программа»"
    )


async def _import_product_and_license(
    session: AsyncSession,
    instance: WorkflowInstance,
    contract: Contract,
    row: list[Any],
    value,
) -> None:  # noqa: ANN001
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

    program_name = _text(value(row, "program"))
    link = await session.scalar(
        select(InteractionProduct).where(
            InteractionProduct.workflow_instance_id == instance.id,
            InteractionProduct.product_id == product.id,
        )
    )
    linked = link is not None and bool(
        await session.scalar(
            select(func.count())
            .select_from(InteractionProgramProduct)
            .where(InteractionProgramProduct.interaction_product_id == link.id)
        )
    )
    # Продукт уже во взаимодействии и связан с программой - строка обновляет
    # его статус и лицензию, программу заново определять не нужно.
    program_links = (
        []
        if linked and not program_name
        else await _program_links_for(session, instance, product, program_name)
    )
    if link is None:
        link = InteractionProduct(workflow_instance_id=instance.id, product_id=product.id)
        session.add(link)
        await session.flush()
    for program_link, exception in program_links:
        if await session.get(InteractionProgramProduct, (program_link.id, link.id)) is None:
            session.add(
                InteractionProgramProduct(
                    interaction_program_id=program_link.id,
                    interaction_product_id=link.id,
                    is_exception=exception,
                    exception_comment=(
                        "Загружено из Excel: в справочнике программ и продуктов "
                        "такой связи нет"
                        if exception
                        else None
                    ),
                )
            )
    await session.flush()

    status = parse_transfer_status(value(row, "transfer_status"))
    if status is not None:
        link.transfer_status = status

    signed_at = parse_date(value(row, "license_signed_at"))
    valid_to = parse_license_valid_to(value(row, "license_valid_to"), signed_at)
    if signed_at is None and valid_to is None:
        return

    license_ = await session.scalar(
        select(License).where(License.interaction_product_id == link.id).limit(1)
    )
    if license_ is None:
        license_ = License(
            contract_id=contract.id,
            interaction_product_id=link.id,
            signed_at=signed_at,
            valid_to=valid_to,
        )
        session.add(license_)
    else:
        license_.signed_at = signed_at or license_.signed_at
        license_.valid_to = valid_to or license_.valid_to
    license_service.normalize_status(license_)
    await session.flush()


async def _university_row(session, row, value, number, warnings) -> bool:  # noqa: ANN001
    name = _text(value(row, "name"))
    inn = parse_inn(value(row, "inn"))
    university = await _find_university(session, name, inn)
    created = university is None
    if university is None:
        # Вуз из файла - на проверку руководителю (единый путь создания вуза).
        university = University(name=name, status=UniversityStatus.PENDING, origin="import")
        session.add(university)
    university.inn = inn or university.inn
    university.short_name = _text(value(row, "short_name")) or university.short_name
    university.city = _text(value(row, "city")) or university.city
    university.website = _text(value(row, "website")) or university.website

    manager_name = _text(value(row, "manager_name"))
    manager = await _find_user(session, manager_name)
    if manager is not None:
        university.manager_id = manager.id
    elif manager_name:
        warnings.append(
            RowError(
                number,
                "ФИО Менеджера",
                f"Предупреждение: сотрудник «{manager_name}» не найден, "
                "ответственный за вуз не изменён",
            )
        )
    await session.flush()
    return created


async def _contact_row(session, row, value, number, warnings) -> bool:  # noqa: ANN001
    university_name = _text(value(row, "university_name"))
    university = await _find_university(session, university_name)
    if university is None:
        raise ValueError(f"вуза «{university_name}» нет в справочнике - загрузите его раньше")
    full_name = _text(value(row, "full_name"))
    contact = await session.scalar(
        select(UniversityContact).where(
            UniversityContact.university_id == university.id,
            func.lower(UniversityContact.full_name) == full_name.lower(),
        )
    )
    created = contact is None
    if contact is None:
        contact = UniversityContact(university_id=university.id, full_name=full_name)
        session.add(contact)
    contact.position = _text(value(row, "position")) or contact.position
    contact.phone = _text(value(row, "phone")) or contact.phone
    contact.email = parse_email(value(row, "email")) or contact.email
    await session.flush()
    return created


async def _program_row(session, row, value, number, warnings) -> bool:  # noqa: ANN001
    direction = None
    direction_name = _text(value(row, "direction"))
    if direction_name:
        direction, _ = await _get_or_create_by_name(session, ItDirection, direction_name)

    program, created = await _get_or_create_by_name(
        session, ItProgram, _text(value(row, "name"))
    )
    program.description = _text(value(row, "description")) or program.description
    if direction is not None:
        program.direction_id = direction.id
    await session.flush()
    return created


async def _product_row(session, row, value, number, warnings) -> bool:  # noqa: ANN001
    vendor = None
    vendor_name = _text(value(row, "vendor"))
    if vendor_name:
        vendor, _ = await _get_or_create_by_name(session, Vendor, vendor_name)

    product, created = await _get_or_create_by_name(
        session, ItProduct, _text(value(row, "name"))
    )
    product.description = _text(value(row, "description")) or product.description
    if vendor is not None:
        product.vendor_id = vendor.id
    await session.flush()
    return created


async def _vendor_row(session, row, value, number, warnings) -> bool:  # noqa: ANN001
    """Строка каталога «Вендоры»: компания, её продукты и ответственный."""
    vendor, created = await _get_or_create_by_name(
        session, Vendor, _text(value(row, "company"))
    )

    contact = None
    full_name = _text(value(row, "full_name"))
    if full_name:
        contact = await session.scalar(
            select(VendorContact).where(
                VendorContact.vendor_id == vendor.id,
                func.lower(VendorContact.full_name) == full_name.lower(),
            )
        )
        if contact is None:
            contact = VendorContact(vendor_id=vendor.id, full_name=full_name)
            session.add(contact)
        contact.phone = _text(value(row, "phone")) or contact.phone
        contact.email = parse_email(value(row, "email")) or contact.email
        contact.contact_channel = (
            _text(value(row, "contact_channel")) or contact.contact_channel
        )
        await session.flush()

    for name in split_products(value(row, "products")):
        product, _ = await _get_or_create_by_name(
            session, ItProduct, name, vendor_id=vendor.id
        )
        product.vendor_id = vendor.id
        if contact is not None:
            product.contact_id = contact.id
    await session.flush()
    return created


async def _learner_row(session, row, value, number, warnings) -> bool:  # noqa: ANN001
    email = parse_email(value(row, "email"))
    phone = normalize_phone(value(row, "phone"))
    learner = None
    if email:
        learner = await session.scalar(select(Learner).where(Learner.email == email))
    if learner is None and phone:
        learner = await session.scalar(select(Learner).where(Learner.phone == phone).limit(1))
    created = learner is None
    if learner is None:
        learner = Learner()
        session.add(learner)
    learner.last_name = _text(value(row, "last_name"))
    learner.first_name = _text(value(row, "first_name"))
    learner.middle_name = _text(value(row, "middle_name")) or None
    learner.email = email or learner.email
    learner.phone = phone or learner.phone
    learner.gender = parse_gender(value(row, "gender")) or learner.gender
    learner.education = _text(value(row, "education")) or learner.education
    learner.region = _text(value(row, "region")) or learner.region
    await session.flush()
    return created


IMPORTERS: dict[ImportType, RowImporter] = {
    ImportType.CATALOG: _catalog_row,
    ImportType.UNIVERSITIES: _university_row,
    ImportType.CONTACTS: _contact_row,
    ImportType.PROGRAMS: _program_row,
    ImportType.PRODUCTS: _product_row,
    ImportType.VENDORS: _vendor_row,
    ImportType.LEARNERS: _learner_row,
}


def validate(
    spec: ImportSpec, sheet: SheetData, mapping: dict[str, str | None]
) -> list[RowError]:
    """Проверка без записи в базу: даты, статусы и обязательные поля."""
    check_mapping(spec, mapping, sheet.headers)
    value = _row_reader(mapping, sheet.headers)
    errors: list[RowError] = []
    for number, row in sheet.numbered():
        errors.extend(row_errors(spec, row, value, number))
    return errors


async def run_import(
    session: AsyncSession,
    spec: ImportSpec,
    sheet: SheetData,
    mapping: dict[str, str | None],
) -> ImportOutcome:
    """Загружает строки. Строка с ошибкой отклоняется целиком, остальные идут дальше."""
    check_mapping(spec, mapping, sheet.headers)
    value = _row_reader(mapping, sheet.headers)
    importer = IMPORTERS[spec.import_type]
    outcome = ImportOutcome()

    for number, row in sheet.numbered():
        problems = row_errors(spec, row, value, number)
        if problems:
            outcome.failed += 1
            outcome.errors.extend(problems)
            continue
        warnings: list[RowError] = []
        try:
            async with session.begin_nested():
                created = await importer(session, row, value, number, warnings)
        except ValueError as exc:
            outcome.failed += 1
            outcome.errors.append(RowError(number, None, str(exc)))
            continue
        except IntegrityError as exc:
            outcome.failed += 1
            outcome.errors.append(
                RowError(
                    number, None, f"строка противоречит уже загруженным данным: {exc.orig}"
                )
            )
            continue
        outcome.errors.extend(warnings)
        if created:
            outcome.created += 1
        else:
            outcome.updated += 1
    return outcome


def build_template(spec: ImportSpec) -> bytes:
    """Пустой файл-образец с нужными заголовками.

    Подсказки - примечаниями к заголовкам, а не строкой данных: строку
    с подсказками при заполнении забывают удалить, и она загружается.
    """
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.comments import Comment as CellComment
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = spec.title[:31]
    for index, item in enumerate(spec.fields, start=1):
        cell = sheet.cell(row=1, column=index, value=item.title)
        cell.font = Font(bold=True, color="B00020" if item.required else "0B0B0B")
        cell.fill = PatternFill("solid", fgColor="F0EFEC")
        note = "Обязательное поле." if item.required else "Необязательное поле."
        if item.aliases:
            note += " Узнаётся и по заголовкам: " + ", ".join(item.aliases) + "."
        cell.comment = CellComment(note, "EDU CRM")
        sheet.column_dimensions[cell.column_letter].width = max(len(item.title) + 4, 16)
    sheet.freeze_panes = "A2"

    info = workbook.create_sheet("Справка")
    info["A1"] = spec.title
    info["A1"].font = Font(bold=True, size=13)
    info["A2"] = spec.description
    info["A4"] = "Обязательные колонки выделены красным. Заполняйте данные со второй строки."
    info.column_dimensions["A"].width = 110

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
