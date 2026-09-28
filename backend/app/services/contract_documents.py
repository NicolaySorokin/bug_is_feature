"""Договор по типовому шаблону.

Шаблон задаёт руководитель: текст с полями {{поле}}. Поля заполняются
из договора, карточки вуза и взаимодействия, пустые остаются пропуском.
Документ собирается в DOCX без внешних библиотек: это ZIP с XML внутри.
"""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from xml.sax.saxutils import escape

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError
from app.models.catalog import ItProduct, ItProgram
from app.models.contract import Contract, ContractTemplate
from app.models.interaction import InteractionContact, InteractionProduct, InteractionProgram
from app.models.workflow import WorkflowInstance
from app.services import audit


@dataclass(frozen=True, slots=True)
class TemplateField:
    key: str
    label: str
    group: str


# Поля шаблона. Имена русские: руководитель пишет их в тексте договора.
FIELDS: tuple[TemplateField, ...] = (
    TemplateField("номер_договора", "Номер договора", "Договор"),
    TemplateField("предмет_договора", "Предмет договора", "Договор"),
    TemplateField("дата", "Дата формирования документа", "Договор"),
    TemplateField("дата_подписания", "Дата подписания", "Договор"),
    TemplateField("срок_с", "Действует с", "Договор"),
    TemplateField("срок_по", "Действует по", "Договор"),
    TemplateField("вуз", "Полное название вуза", "Вуз"),
    TemplateField("вуз_кратко", "Краткое название вуза", "Вуз"),
    TemplateField("инн_вуза", "ИНН вуза", "Вуз"),
    TemplateField("город_вуза", "Город вуза", "Вуз"),
    TemplateField("реквизиты_вуза", "Реквизиты вуза (адрес, КПП, ОГРН, банк)", "Вуз"),
    TemplateField("подписант_вуза", "ФИО подписанта", "Подписант от вуза"),
    TemplateField("подписант_вуза_инициалы", "Подписант: И. О. Фамилия", "Подписант от вуза"),
    TemplateField("должность_подписанта", "Должность подписанта", "Подписант от вуза"),
    TemplateField(
        "основание_подписанта", "Основание полномочий подписанта", "Подписант от вуза"
    ),
    TemplateField("контакт_вуза", "Ответственный от вуза (ФИО, должность)", "Взаимодействие"),
    TemplateField("контакт_вуза_почта", "Почта ответственного от вуза", "Взаимодействие"),
    TemplateField("контакт_вуза_телефон", "Телефон ответственного от вуза", "Взаимодействие"),
    TemplateField("менеджер", "Ответственный менеджер ИТ Школы", "Взаимодействие"),
    TemplateField("менеджер_почта", "Почта менеджера", "Взаимодействие"),
    TemplateField("программы", "ИТ-программы (списком)", "Взаимодействие"),
    TemplateField("продукты", "ИТ-продукты (списком)", "Взаимодействие"),
)
FIELD_BY_KEY = {field.key: field for field in FIELDS}

PLACEHOLDER = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")
BLANK = "________________"

DEFAULT_NAME = "Договор о сотрудничестве (типовой)"
DEFAULT_BODY = """\
# ДОГОВОР О СОТРУДНИЧЕСТВЕ № {{номер_договора}}

г. {{город_вуза}}, {{дата}}

Публичное акционерное общество «Ростелеком» (ИТ Школа Ростелекома, далее — \
«Компания») и {{вуз}} (далее — «Вуз»), вместе именуемые «Стороны», заключили \
настоящий договор о нижеследующем.

Подписант от Вуза: {{должность_подписанта}} {{подписант_вуза}}, действует \
на основании {{основание_подписанта}}.

## 1. Предмет договора

1.1. Предмет договора: {{предмет_договора}}.

1.2. Компания передаёт Вузу методические материалы и практические задания, \
Вуз включает их в учебный процесс по ИТ-программам:
{{программы}}

1.3. Для обучения Компания предоставляет Вузу доступ к ИТ-продуктам:
{{продукты}}

## 2. Обязанности Сторон

2.1. Компания передаёт учебные материалы и лицензии на ИТ-продукты, проводит \
обучение преподавателей Вуза и сопровождает внедрение ИТ-продуктов в учебный \
процесс.

2.2. Вуз включает материалы в учебные программы, назначает преподавателей \
и сообщает Компании о количестве обучающихся и потоков.

## 3. Срок действия

3.1. Договор вступает в силу {{срок_с}} и действует по {{срок_по}} включительно.

## 4. Контактные лица

От Компании: {{менеджер}}, {{менеджер_почта}}.

От Вуза: {{контакт_вуза}}, {{контакт_вуза_почта}}, {{контакт_вуза_телефон}}.

## 5. Реквизиты и подписи Сторон

Вуз: {{вуз}}
ИНН {{инн_вуза}}
{{реквизиты_вуза}}


{{должность_подписанта}}
_______________ {{подписант_вуза_инициалы}}


Компания: ПАО «Ростелеком»
Реквизиты: ________________________________


_______________ / _______________ /
"""

_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

# Блокировка, чтобы шаблон по умолчанию завёлся один раз при одновременных запросах.
_DEFAULT_LOCK = 7_412_001


def long_date(value: date | None) -> str | None:
    """Дата так, как её пишут в договоре: «11» сентября 2026 г."""
    if value is None:
        return None
    return f"«{value.day:02d}» {_MONTHS[value.month - 1]} {value.year} г."


def initials(full_name: str | None) -> str | None:
    """«Иванов Иван Иванович» в «И. И. Иванов» для строки подписи."""
    parts = (full_name or "").split()
    if len(parts) < 2:
        return full_name or None
    last, *rest = parts
    return " ".join(f"{part[0]}." for part in rest) + f" {last}"


def _lower_first(value: str) -> str:
    return value[:1].lower() + value[1:]


def unknown_fields(body: str) -> list[str]:
    """Поля в тексте, которых система не знает: скорее всего, опечатка."""
    found: list[str] = []
    for key in PLACEHOLDER.findall(body):
        if key not in FIELD_BY_KEY and key not in found:
            found.append(key)
    return found


def render(body: str, values: dict[str, str | None]) -> tuple[str, list[TemplateField]]:
    """Подставляет значения. Возвращает текст и поля, которым значения не нашлось."""
    missing: list[TemplateField] = []

    def substitute(match: re.Match[str]) -> str:
        field = FIELD_BY_KEY.get(match.group(1))
        if field is None:
            return match.group(0)
        value = (values.get(field.key) or "").strip()
        if not value:
            if field not in missing:
                missing.append(field)
            return BLANK
        return value

    return PLACEHOLDER.sub(substitute, body), missing


async def ensure_default(session: AsyncSession) -> None:
    """Заводит типовой шаблон, если шаблонов ещё нет.

    Автором такого шаблона в журнале будет система.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _DEFAULT_LOCK})
    count = await session.scalar(select(func.count()).select_from(ContractTemplate))
    if not count:
        token = audit.current_actor_id.set(None)
        try:
            session.add(ContractTemplate(name=DEFAULT_NAME, body=DEFAULT_BODY))
            await session.flush()
        finally:
            audit.current_actor_id.reset(token)


async def collect_values(
    session: AsyncSession, interaction_id: uuid.UUID, today: date | None = None
) -> dict[str, str | None]:
    """Значения полей шаблона по взаимодействию, его вузу и договору."""
    instance = await session.scalar(
        select(WorkflowInstance)
        .where(WorkflowInstance.id == interaction_id)
        .options(
            selectinload(WorkflowInstance.university),
            selectinload(WorkflowInstance.manager),
            selectinload(WorkflowInstance.contacts).selectinload(InteractionContact.contact),
            selectinload(WorkflowInstance.programs)
            .selectinload(InteractionProgram.program)
            .selectinload(ItProgram.direction),
            selectinload(WorkflowInstance.products)
            .selectinload(InteractionProduct.product)
            .selectinload(ItProduct.vendor),
        )
        .execution_options(populate_existing=True)
    )
    if instance is None:
        raise NotFoundError("Взаимодействие не найдено")
    contract = await session.scalar(
        select(Contract).where(Contract.workflow_instance_id == instance.id)
    )
    university = instance.university
    # Ответственный от вуза: основной контакт, а если его нет, первый по алфавиту.
    links = sorted(
        (link for link in instance.contacts if link.contact is not None),
        key=lambda link: (not link.is_primary, link.contact.full_name),
    )
    contact = links[0].contact if links else None
    programs = sorted(
        (link.program for link in instance.programs if link.program is not None),
        key=lambda program: program.name,
    )
    products = sorted(
        (link.product for link in instance.products if link.product is not None),
        key=lambda product: product.name,
    )
    manager = instance.manager

    return {
        "номер_договора": contract.number if contract else None,
        "предмет_договора": (contract.title if contract else None) or instance.title,
        "дата": long_date(today or datetime.now(UTC).date()),
        "дата_подписания": long_date(contract.signed_at) if contract else None,
        "срок_с": long_date(contract.valid_from) if contract else None,
        "срок_по": long_date(contract.valid_to) if contract else None,
        "вуз": university.name if university else None,
        "вуз_кратко": university.display_name if university else None,
        "инн_вуза": university.inn if university else None,
        "город_вуза": university.city if university else None,
        "реквизиты_вуза": university.requisites if university else None,
        "подписант_вуза": contract.signatory_name if contract else None,
        "подписант_вуза_инициалы": initials(contract.signatory_name) if contract else None,
        "должность_подписанта": contract.signatory_position if contract else None,
        "основание_подписанта": contract.signatory_basis if contract else None,
        "контакт_вуза": (
            ", ".join(
                part
                for part in (contact.full_name, _lower_first(contact.position or ""))
                if part
            )
            if contact
            else None
        ),
        "контакт_вуза_почта": contact.email if contact else None,
        "контакт_вуза_телефон": contact.phone if contact else None,
        "менеджер": manager.full_name if manager else None,
        "менеджер_почта": manager.email if manager else None,
        "программы": "\n".join(
            f"- {program.name}"
            + (f" (направление «{program.direction.name}»)" if program.direction else "")
            for program in programs
        )
        or None,
        "продукты": "\n".join(
            f"- {product.name}" + (f" ({product.vendor.name})" if product.vendor else "")
            for product in products
        )
        or None,
    }


def document_filename(values: dict[str, str | None]) -> str:
    """Имя файла по номеру договора, без номера по вузу."""
    number = values.get("номер_договора")
    base = (
        f"Проект договора {number}"
        if number
        else f"Проект договора - {values.get('вуз_кратко') or 'вуз'}"
    )
    return re.sub(r'[\\/:*?"<>|]+', "-", base).strip() + ".docx"


@dataclass(slots=True)
class PreparedDocument:
    template: ContractTemplate
    text: str
    missing: list[TemplateField]
    filename: str


async def prepare(
    session: AsyncSession, interaction_id: uuid.UUID, template_id: uuid.UUID
) -> PreparedDocument:
    template = await session.get(ContractTemplate, template_id)
    if template is None:
        raise NotFoundError("Шаблон договора не найден")
    if not template.is_active:
        raise ConflictError("Шаблон выключен - выберите действующий")
    values = await collect_values(session, interaction_id)
    rendered, missing = render(template.body, values)
    return PreparedDocument(template, rendered, missing, document_filename(values))


# DOCX

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

_CONTENT_TYPES = (
    f"{_XML}"
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/docProps/core.xml" '
    'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    "</Types>"
)
_PACKAGE_RELS = (
    f'{_XML}<Relationships xmlns="{_REL_NS}">'
    f'<Relationship Id="rId1" Type="{_OFFICE_REL}/officeDocument" '
    'Target="word/document.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/'
    'relationships/metadata/core-properties" Target="docProps/core.xml"/>'
    "</Relationships>"
)
_DOCUMENT_RELS = (
    f'{_XML}<Relationships xmlns="{_REL_NS}">'
    f'<Relationship Id="rId1" Type="{_OFFICE_REL}/styles" Target="styles.xml"/>'
    "</Relationships>"
)
# Шрифт и интервалы, принятые для договоров: Times New Roman 12 пт.
_STYLES = (
    f'{_XML}<w:styles xmlns:w="{_W_NS}"><w:docDefaults><w:rPrDefault><w:rPr>'
    '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
    'w:eastAsia="Times New Roman" w:cs="Times New Roman"/>'
    '<w:sz w:val="24"/><w:szCs w:val="24"/><w:lang w:val="ru-RU"/>'
    "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>"
    '<w:spacing w:after="120" w:line="264" w:lineRule="auto"/>'
    "</w:pPr></w:pPrDefault></w:docDefaults>"
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
    '<w:name w:val="Normal"/><w:qFormat/></w:style>'
    "</w:styles>"
)
# Лист A4, поля: слева 3 см, справа 1,5 см, сверху и снизу 2 см.
_SECTION = (
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="1134" w:right="850" w:bottom="1134" w:left="1701" '
    'w:header="709" w:footer="709" w:gutter="0"/></w:sectPr>'
)


def _run(value: str, *, bold: bool = False, size: int | None = None) -> str:
    props = ("<w:b/>" if bold else "") + (
        f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>' if size else ""
    )
    return (
        f"<w:r>{f'<w:rPr>{props}</w:rPr>' if props else ''}"
        f'<w:t xml:space="preserve">{escape(value)}</w:t></w:r>'
    )


def _paragraph(line: str) -> str:
    """Строка шаблона в абзац: «# » заголовок по центру, «## » заголовок раздела,
    «- » пункт списка.
    """
    stripped = line.strip()
    if stripped.startswith("# "):
        return (
            '<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="120" w:after="240"/>'
            f"</w:pPr>{_run(stripped[2:].strip(), bold=True, size=28)}</w:p>"
        )
    if stripped.startswith("## "):
        return (
            '<w:p><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/></w:pPr>'
            f"{_run(stripped[3:].strip(), bold=True)}</w:p>"
        )
    if not stripped:
        return "<w:p/>"
    if stripped.startswith(("- ", "— ", "• ")):
        return (
            '<w:p><w:pPr><w:spacing w:after="40"/><w:ind w:left="357"/></w:pPr>'
            f"{_run(stripped)}</w:p>"
        )
    return f'<w:p><w:pPr><w:jc w:val="both"/></w:pPr>{_run(line.rstrip())}</w:p>'


def _paragraphs(content: str) -> str:
    """Каждая строка становится абзацем. Одна пустая строка только разделяет абзацы,
    несколько подряд оставляют пустое место, например для подписи.
    """
    lines = content.replace("\r\n", "\n").replace("\t", "    ").split("\n")
    result: list[str] = []
    blanks = 0
    for line in lines:
        if not line.strip():
            blanks += 1
            continue
        if blanks > 1 and result:
            result.append(_paragraph(""))
        blanks = 0
        result.append(_paragraph(line))
    return "".join(result)


def build_docx(content: str, title: str, created: datetime | None = None) -> bytes:
    """Документ Word из текста шаблона с подставленными значениями."""
    document = (
        f'{_XML}<w:document xmlns:w="{_W_NS}"><w:body>'
        f"{_paragraphs(content)}{_SECTION}</w:body></w:document>"
    )
    stamp = (created or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = (
        f"{_XML}<cp:coreProperties "
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{escape(title)}</dc:title><dc:creator>EDU-CRM</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created>'
        "</cp:coreProperties>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _PACKAGE_RELS)
        archive.writestr("word/_rels/document.xml.rels", _DOCUMENT_RELS)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", _STYLES)
        archive.writestr("docProps/core.xml", core)
    return buffer.getvalue()
