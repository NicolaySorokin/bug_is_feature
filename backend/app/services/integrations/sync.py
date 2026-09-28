"""Синхронизация с внешними системами.

Адаптер отдаёт данные в общем виде, а здесь решается, что с ними делать.
Связь external_links не даёт повторному обмену плодить дубли. Запись, похожую
на существующую, по названию не сопоставляем, она ждёт решения
администратора. Заявка вуза попадает в открытое взаимодействие или заводит
черновик, заявка студента идёт только в статистику. Ошибка одной записи
не останавливает обмен.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, ErrorCode, NotFoundError
from app.enums import (
    IntegrationRunStatus,
    InteractionSource,
    InteractionStatus,
    MappingStatus,
    UniversityStatus,
)
from app.models.catalog import ItDirection, ItProduct, ItProgram, Vendor
from app.models.content import Comment
from app.models.integration import (
    ExternalLink,
    IntegrationMapping,
    IntegrationRun,
    IntegrationRunError,
    IntegrationSource,
)
from app.models.interaction import InteractionProgram
from app.models.learning import Enrollment, Learner, LearningApplication, LearningStream
from app.models.university import University, UniversityContact
from app.models.user import User
from app.models.workflow import WorkflowEvent, WorkflowInstance
from app.services import workflow as workflow_service
from app.services.integrations.base import (
    IntegrationPayload,
    SourceAdapter,
    date_from_number,
)
from app.services.integrations.lms import LmsAdapter
from app.services.integrations.site import SiteAdapter

# Порядок важен: сначала LMS с программами, затем сайт с заявками на них.
ADAPTERS: dict[str, type[SourceAdapter]] = {
    LmsAdapter.code: LmsAdapter,
    SiteAdapter.code: SiteAdapter,
}

UNIVERSITY = "university"
PROGRAM = "it_program"
PRODUCT = "it_product"
INTERACTION = "interaction"
COURSE = "course"  # название курса в заявке сайта и программа

ENTITY_TITLES = {
    UNIVERSITY: "Вуз",
    PROGRAM: "ИТ-программа",
    PRODUCT: "ИТ-продукт",
    COURSE: "Курс в заявках сайта",
}

OPEN = (InteractionStatus.DRAFT, InteractionStatus.IN_PROGRESS, InteractionStatus.BLOCKED)


@dataclass(slots=True)
class SyncStats:
    received: int = 0
    created: int = 0
    updated: int = 0
    failed: int = 0
    pending: int = 0
    notes: list[str] = field(default_factory=list)
    errors: list[tuple[str, str | None, str]] = field(default_factory=list)

    def fail(self, entity_type: str, external_id: str | None, message: str) -> None:
        self.failed += 1
        self.errors.append((entity_type, external_id, message))


def build_adapter(code: str) -> SourceAdapter:
    adapter_class = ADAPTERS.get(code)
    if adapter_class is None:
        raise NotFoundError(f"Источник «{code}» не зарегистрирован")
    return adapter_class()


async def ensure_sources(session: AsyncSession) -> list[IntegrationSource]:
    """Заводит записи источников, которых ещё нет в базе."""
    existing = {
        source.code: source
        for source in (await session.execute(select(IntegrationSource))).scalars()
    }
    for code, adapter_class in ADAPTERS.items():
        adapter = adapter_class()
        if code in existing:
            existing[code].base_url = adapter.base_url or None
            continue
        source = IntegrationSource(
            code=code, name=adapter.name, base_url=adapter.base_url or None
        )
        session.add(source)
        existing[code] = source
    await session.flush()
    return list(existing.values())


async def get_source(session: AsyncSession, code: str) -> IntegrationSource:
    await ensure_sources(session)
    source = await session.scalar(
        select(IntegrationSource).where(IntegrationSource.code == code)
    )
    if source is None:  # pragma: no cover (ensure_sources только что его создал)
        raise NotFoundError(f"Источник «{code}» не найден")
    return source


def normalize_course(name: str) -> str:
    """Ключ курса: название без регистра и лишних пробелов."""
    return re.sub(r"\s+", " ", name.strip().lower().replace("ё", "е"))


# Связи с внешними объектами


async def linked_id(
    session: AsyncSession, source_id: uuid.UUID, entity_type: str, external_id: str
) -> uuid.UUID | None:
    return await session.scalar(
        select(ExternalLink.entity_id).where(
            ExternalLink.source_id == source_id,
            ExternalLink.entity_type == entity_type,
            ExternalLink.external_id == external_id,
        )
    )


async def remember(
    session: AsyncSession,
    source_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    external_id: str,
) -> None:
    link = await session.scalar(
        select(ExternalLink).where(
            ExternalLink.source_id == source_id,
            ExternalLink.entity_type == entity_type,
            ExternalLink.external_id == external_id,
        )
    )
    if link is None:
        session.add(
            ExternalLink(
                source_id=source_id,
                entity_type=entity_type,
                entity_id=entity_id,
                external_id=external_id,
            )
        )
    else:
        link.entity_id = entity_id
    await session.flush()


async def _mapping(
    session: AsyncSession, source_id: uuid.UUID, entity_type: str, external_id: str
) -> IntegrationMapping | None:
    return await session.scalar(
        select(IntegrationMapping).where(
            IntegrationMapping.source_id == source_id,
            IntegrationMapping.entity_type == entity_type,
            IntegrationMapping.external_id == external_id,
        )
    )


async def _ask_mapping(
    session: AsyncSession,
    source_id: uuid.UUID,
    entity_type: str,
    external_id: str,
    external_name: str,
    suggested: uuid.UUID | None,
    payload: dict,
) -> None:
    """Ставит внешнюю запись в очередь ручного сопоставления."""
    mapping = await _mapping(session, source_id, entity_type, external_id)
    if mapping is None:
        session.add(
            IntegrationMapping(
                source_id=source_id,
                entity_type=entity_type,
                external_id=external_id,
                external_name=external_name,
                suggested_entity_id=suggested,
                payload=payload,
            )
        )
    else:
        mapping.external_name = external_name
        mapping.suggested_entity_id = suggested
        mapping.payload = payload
    await session.flush()


async def _resolve_entity(
    session: AsyncSession,
    source: IntegrationSource,
    entity_type: str,
    external_id: str,
    name: str,
    model,  # noqa: ANN001 (класс модели)
    payload: dict,
    stats: SyncStats,
) -> tuple[uuid.UUID | None, bool]:
    """Находит нашу запись для внешней: (id, нужно ли создать новую).

    (None, False): запись ждёт ручного сопоставления или исключена.
    """
    entity_id = await linked_id(session, source.id, entity_type, external_id)
    if entity_id is not None and await session.get(model, entity_id) is not None:
        return entity_id, False
    mapping = await _mapping(session, source.id, entity_type, external_id)
    if mapping is not None and mapping.status == MappingStatus.IGNORED:
        return None, False
    if mapping is not None and mapping.status == MappingStatus.PENDING:
        stats.pending += 1
        return None, False
    twin = await session.scalar(
        select(model.id).where(func.lower(model.name) == name.lower()).limit(1)
    )
    if twin is not None:
        # Похожая запись есть, но по названию не сопоставляем, решает человек.
        await _ask_mapping(session, source.id, entity_type, external_id, name, twin, payload)
        stats.pending += 1
        return None, False
    return None, True


# Справочники


async def _direction(session: AsyncSession, name: str | None) -> ItDirection | None:
    if not name:
        return None
    direction = await session.scalar(select(ItDirection).where(ItDirection.name == name))
    if direction is None:
        direction = ItDirection(name=name)
        session.add(direction)
        await session.flush()
    return direction


async def _vendor(session: AsyncSession, name: str | None) -> Vendor | None:
    if not name:
        return None
    vendor = await session.scalar(select(Vendor).where(Vendor.name == name))
    if vendor is None:
        vendor = Vendor(name=name)
        session.add(vendor)
        await session.flush()
    return vendor


async def create_program(session: AsyncSession, data: dict) -> ItProgram:
    direction = await _direction(session, data.get("direction_name"))
    program = ItProgram(
        name=data["name"],
        description=data.get("description"),
        direction_id=direction.id if direction else None,
    )
    session.add(program)
    await session.flush()
    return program


async def create_product(session: AsyncSession, data: dict) -> ItProduct:
    vendor = await _vendor(session, data.get("vendor_name"))
    product = ItProduct(
        name=data["name"],
        description=data.get("description"),
        vendor_id=vendor.id if vendor else None,
    )
    session.add(product)
    await session.flush()
    return product


async def create_university(session: AsyncSession, data: dict, origin: str) -> University:
    """Вуз из внешнего источника всегда идёт на проверку руководителю."""
    university = University(
        name=data["name"],
        short_name=data.get("short_name"),
        city=data.get("city"),
        website=data.get("website"),
        status=UniversityStatus.PENDING,
        origin=origin,
    )
    session.add(university)
    await session.flush()
    return university


async def _sync_programs(
    session: AsyncSession, source: IntegrationSource, payload: IntegrationPayload
) -> SyncStats:
    stats = SyncStats()
    for item in payload.programs:
        stats.received += 1
        data = {
            "name": item.name,
            "direction_name": item.direction_name,
            "description": item.description,
        }
        entity_id, create = await _resolve_entity(
            session, source, PROGRAM, item.external_id, item.name, ItProgram, data, stats
        )
        if create:
            program = await create_program(session, data)
            await remember(session, source.id, PROGRAM, program.id, item.external_id)
            stats.created += 1
        elif entity_id is not None:
            program = await session.get(ItProgram, entity_id)
            program.name = item.name
            program.description = item.description or program.description
            direction = await _direction(session, item.direction_name)
            if direction is not None:
                program.direction_id = direction.id
            stats.updated += 1
    return stats


async def _sync_products(
    session: AsyncSession, source: IntegrationSource, payload: IntegrationPayload
) -> SyncStats:
    stats = SyncStats()
    for item in payload.products:
        stats.received += 1
        data = {
            "name": item.name,
            "vendor_name": item.vendor_name,
            "description": item.description,
        }
        entity_id, create = await _resolve_entity(
            session, source, PRODUCT, item.external_id, item.name, ItProduct, data, stats
        )
        if create:
            product = await create_product(session, data)
            await remember(session, source.id, PRODUCT, product.id, item.external_id)
            stats.created += 1
        elif entity_id is not None:
            product = await session.get(ItProduct, entity_id)
            product.name = item.name
            product.description = item.description or product.description
            vendor = await _vendor(session, item.vendor_name)
            if vendor is not None:
                product.vendor_id = vendor.id
            stats.updated += 1
    return stats


# Вузы


async def _sync_universities(
    session: AsyncSession, source: IntegrationSource, payload: IntegrationPayload
) -> SyncStats:
    stats = SyncStats()
    for item in payload.universities:
        stats.received += 1
        data = {
            "name": item.name,
            "short_name": item.short_name,
            "city": item.city,
            "website": item.website,
            "contacts": [
                {
                    "full_name": contact.full_name,
                    "position": contact.position,
                    "email": contact.email,
                    "phone": contact.phone,
                }
                for contact in item.contacts
            ],
        }
        entity_id, create = await _resolve_entity(
            session, source, UNIVERSITY, item.external_id, item.name, University, data, stats
        )
        if create:
            university = await create_university(session, data, source.code)
            await remember(session, source.id, UNIVERSITY, university.id, item.external_id)
            stats.created += 1
        elif entity_id is not None:
            university = await session.get(University, entity_id)
            university.short_name = item.short_name or university.short_name
            university.city = item.city or university.city
            university.website = item.website or university.website
            stats.updated += 1
        else:
            continue
        await sync_contacts(session, university, data["contacts"])
    return stats


async def sync_contacts(
    session: AsyncSession, university: University, contacts: list[dict]
) -> None:
    """Контакты сопоставляются по ФИО внутри вуза: внешних идентификаторов у них нет."""
    if not contacts:
        return
    existing = {
        contact.full_name.lower(): contact
        for contact in (
            await session.execute(
                select(UniversityContact).where(
                    UniversityContact.university_id == university.id
                )
            )
        ).scalars()
    }
    for contact in contacts:
        current = existing.get(contact["full_name"].lower())
        if current is None:
            session.add(UniversityContact(university_id=university.id, **contact))
        else:
            current.position = contact.get("position") or current.position
            current.email = contact.get("email") or current.email
            current.phone = contact.get("phone") or current.phone
    await session.flush()


# Заявки вузов на сотрудничество


async def _open_interaction(
    session: AsyncSession, university_id: uuid.UUID, program_ids: list[uuid.UUID]
) -> WorkflowInstance | None:
    """Открытое взаимодействие по вузу с одной из программ заявки."""
    statement = (
        select(WorkflowInstance)
        .where(
            WorkflowInstance.university_id == university_id,
            WorkflowInstance.status.in_(OPEN),
        )
        .order_by(WorkflowInstance.created_at.desc())
        .limit(1)
    )
    if program_ids:
        statement = statement.where(
            WorkflowInstance.id.in_(
                select(InteractionProgram.workflow_instance_id).where(
                    InteractionProgram.program_id.in_(program_ids)
                )
            )
        )
    return await session.scalar(statement)


async def _note(
    session: AsyncSession, instance: WorkflowInstance, user: User | None, text: str
) -> None:
    """Сведения из обмена комментарием к текущему шагу взаимодействия."""
    event_id = await session.scalar(
        select(WorkflowEvent.id)
        .where(WorkflowEvent.workflow_instance_id == instance.id)
        .order_by(WorkflowEvent.created_at.desc())
        .limit(1)
    )
    session.add(
        Comment(
            workflow_instance_id=instance.id,
            workflow_event_id=event_id,
            author_id=user.id if user else None,
            text=text,
        )
    )
    await session.flush()


async def _sync_requests(
    session: AsyncSession,
    source: IntegrationSource,
    payload: IntegrationPayload,
    user: User | None,
) -> SyncStats:
    """Заявка вуза на сотрудничество: в существующее взаимодействие или черновик."""
    stats = SyncStats()
    if not payload.requests:
        return stats
    lms = await get_source(session, LmsAdapter.code)
    template = await workflow_service.default_template(session)

    for item in payload.requests:
        stats.received += 1
        if await linked_id(session, source.id, INTERACTION, item.external_id) is not None:
            stats.updated += 1  # заявка уже разобрана в прошлый раз
            continue

        university_id = await linked_id(
            session, source.id, UNIVERSITY, item.university_external_id
        )
        university = await session.get(University, university_id) if university_id else None
        if university is None:
            stats.fail(
                INTERACTION,
                item.external_id,
                f"Вуз «{item.university_external_id}» не сопоставлен со справочником",
            )
            continue
        if university.status != UniversityStatus.CONFIRMED:
            stats.pending += 1
            stats.notes.append(
                f"Заявка {item.external_id} ждёт подтверждения вуза «{university.name}»"
            )
            continue

        program_ids: list[uuid.UUID] = []
        unknown: list[str] = []
        for external_program_id in item.program_external_ids:
            # Программы заявки заданы идентификаторами LMS, ищем их в LMS.
            program_id = await linked_id(session, lms.id, PROGRAM, external_program_id)
            if program_id is None:
                unknown.append(external_program_id)
            else:
                program_ids.append(program_id)
        if unknown:
            stats.errors.append(
                (
                    INTERACTION,
                    item.external_id,
                    "Программы не найдены среди программ LMS и не добавлены: "
                    + ", ".join(unknown),
                )
            )

        existing = await _open_interaction(session, university.id, program_ids)
        text = "Заявка вуза с сайта ИТ Школы" + (f": {item.comment}" if item.comment else "")
        if existing is not None:
            await _note(session, existing, user, f"{text} (заявка {item.external_id})")
            await remember(session, source.id, INTERACTION, existing.id, item.external_id)
            stats.updated += 1
            continue

        if template is None:
            stats.fail(
                INTERACTION, item.external_id, "Нет шаблона процесса с действующей версией"
            )
            continue
        version = await workflow_service.active_version(session, template.id)
        instance = await workflow_service.create_interaction(
            session,
            university_id=university.id,
            version=version,
            user=user,
            manager_id=university.manager_id,
            title="Заявка вуза с сайта ИТ Школы",
            comment=item.comment,
            source=InteractionSource.SITE,
        )
        for program_id in dict.fromkeys(program_ids):
            session.add(
                InteractionProgram(workflow_instance_id=instance.id, program_id=program_id)
            )
        await session.flush()
        await remember(session, source.id, INTERACTION, instance.id, item.external_id)
        stats.created += 1
    if stats.created:
        stats.notes.append(
            f"Новых взаимодействий-черновиков по заявкам вузов: {stats.created}. "
            "Процесс запускает ответственный"
        )
    return stats


# Заявки студентов: только статистика


async def _program_for_course(
    session: AsyncSession, source: IntegrationSource, course: str, stats: SyncStats
) -> uuid.UUID | None:
    """Программа курса из заявки: по сопоставлению, не по одному названию."""
    key = normalize_course(course)
    entity_id = await linked_id(session, source.id, COURSE, key)
    if entity_id is not None:
        return entity_id
    mapping = await _mapping(session, source.id, COURSE, key)
    if mapping is None:
        twin = await session.scalar(
            select(ItProgram.id).where(func.lower(ItProgram.name) == course.lower()).limit(1)
        )
        await _ask_mapping(session, source.id, COURSE, key, course, twin, {"name": course})
        stats.pending += 1
    return None


def stream_key(
    program_id: uuid.UUID | None, course: str, number: int, submitted_at: datetime
) -> tuple[str, str]:
    """Ключ потока без идентификатора источника: программа, номер и полугодие."""
    half = "H1" if submitted_at.month <= 6 else "H2"
    period = f"{submitted_at.year}-{half}"
    base = str(program_id) if program_id else normalize_course(course)
    return f"auto:{base}:{number}:{submitted_at.year}{half}", period


async def _stream(
    session: AsyncSession,
    source: IntegrationSource,
    application: LearningApplication,
    external_stream: str | None,
) -> uuid.UUID | None:
    if application.stream_number is None and not external_stream:
        return None
    if external_stream:
        key, period = external_stream, None
    else:
        key, period = stream_key(
            application.program_id,
            application.course_name,
            application.stream_number,
            application.submitted_at,
        )
    stream = await session.scalar(
        select(LearningStream).where(
            LearningStream.source_id == source.id, LearningStream.external_id == key
        )
    )
    if stream is None:
        stream = LearningStream(
            source_id=source.id,
            external_id=key,
            program_id=application.program_id,
            number=application.stream_number,
            period=period,
        )
        session.add(stream)
        await session.flush()
    return stream.id


async def enroll_by_contact(session: AsyncSession, application: LearningApplication) -> bool:
    """Зачисление по почте или телефону заявки, пока LMS не передаёт связь сама."""
    if application.program_id is None or not (application.email or application.phone):
        return False
    conditions = []
    if application.email:
        conditions.append(Learner.email == application.email)
    if application.phone:
        conditions.append(Learner.phone == application.phone)
    learner = await session.scalar(select(Learner).where(or_(*conditions)).limit(1))
    if learner is None:
        return False
    exists = await session.scalar(
        select(Enrollment.id).where(
            Enrollment.learner_id == learner.id,
            Enrollment.program_id == application.program_id,
            Enrollment.stream_id.is_not_distinct_from(application.stream_id),
        )
    )
    if exists is None:
        session.add(
            Enrollment(
                learner_id=learner.id,
                program_id=application.program_id,
                stream_id=application.stream_id,
                application_id=application.id,
                matched_by="contact",
            )
        )
        await session.flush()
    return True


async def _sync_applications(
    session: AsyncSession, source: IntegrationSource, payload: IntegrationPayload
) -> SyncStats:
    stats = SyncStats()
    if not payload.applications:
        return stats
    now = datetime.now(UTC)
    unknown_universities: set[str] = set()

    for item in payload.applications:
        stats.received += 1
        program_id = await _program_for_course(session, source, item.course_name, stats)
        application = await session.scalar(
            select(LearningApplication).where(
                LearningApplication.source_id == source.id,
                LearningApplication.external_id == item.external_id,
            )
        )
        if application is None:
            application = LearningApplication(
                source_id=source.id,
                external_id=item.external_id,
                submitted_at=item.submitted_at or date_from_number(item.external_id) or now,
            )
            session.add(application)
            stats.created += 1
        else:
            stats.updated += 1

        application.program_id = program_id
        application.course_name = item.course_name
        application.stream_number = item.stream_number
        application.last_name = item.last_name
        application.first_name = item.first_name
        application.middle_name = item.middle_name
        application.phone = item.phone
        application.email = item.email
        if item.university_name:
            university = await _university_by_name(session, item.university_name)
            if university is None:
                unknown_universities.add(item.university_name)
            application.university_id = university.id if university else None
        await session.flush()
        application.stream_id = await _stream(session, source, application, item.stream_id)
        await session.flush()
        await enroll_by_contact(session, application)

    stats.notes.append(
        "Заявки студентов учтены в статистике обучения: взаимодействия с вузами они не создают"
    )
    if unknown_universities:
        stats.notes.append(
            "Вузы заявителей не найдены в справочнике (в статистике - без вуза): "
            + ", ".join(sorted(unknown_universities))
        )
    return stats


async def _university_by_name(session: AsyncSession, name: str) -> University | None:
    """Вуз заявителя нужен только для статистики."""
    value = name.lower()
    return await session.scalar(
        select(University)
        .where(
            or_(
                func.lower(University.name) == value,
                func.lower(University.short_name) == value,
            ),
            University.status != UniversityStatus.ARCHIVED,
        )
        .limit(1)
    )


# Обучающиеся из LMS


async def _sync_learners(
    session: AsyncSession, source: IntegrationSource, payload: IntegrationPayload
) -> SyncStats:
    stats = SyncStats()
    site = await get_source(session, SiteAdapter.code)
    for item in payload.learners:
        stats.received += 1
        learner = None
        if item.external_id:
            learner = await session.scalar(
                select(Learner).where(
                    Learner.source_id == source.id, Learner.external_id == item.external_id
                )
            )
        if learner is None and item.email:
            learner = await session.scalar(select(Learner).where(Learner.email == item.email))
        if learner is None and item.phone:
            learner = await session.scalar(
                select(Learner).where(Learner.phone == item.phone).limit(1)
            )
        if learner is None:
            learner = Learner(source_id=source.id)
            session.add(learner)
            stats.created += 1
        else:
            stats.updated += 1
        learner.external_id = item.external_id or learner.external_id
        learner.last_name = item.last_name
        learner.first_name = item.first_name
        learner.middle_name = item.middle_name
        learner.email = item.email or learner.email
        learner.phone = item.phone or learner.phone
        learner.gender = item.gender or learner.gender
        learner.education = item.education or learner.education
        learner.region = item.region or learner.region
        await session.flush()

        if item.course_name:
            # LMS сама передала программу: зачисление надёжное.
            program_id = await linked_id(
                session, source.id, PROGRAM, item.program_external_id or ""
            ) or await _program_for_course(session, site, item.course_name, stats)
            if program_id is not None:
                stream_id = None
                if item.stream_external_id:
                    stream = await session.scalar(
                        select(LearningStream).where(
                            LearningStream.source_id == source.id,
                            LearningStream.external_id == item.stream_external_id,
                        )
                    )
                    if stream is None:
                        stream = LearningStream(
                            source_id=source.id,
                            external_id=item.stream_external_id,
                            program_id=program_id,
                            number=item.stream_number,
                        )
                        session.add(stream)
                        await session.flush()
                    stream_id = stream.id
                exists = await session.scalar(
                    select(Enrollment.id).where(
                        Enrollment.learner_id == learner.id,
                        Enrollment.program_id == program_id,
                        Enrollment.stream_id.is_not_distinct_from(stream_id),
                    )
                )
                if exists is None:
                    session.add(
                        Enrollment(
                            learner_id=learner.id,
                            program_id=program_id,
                            stream_id=stream_id,
                            matched_by="lms",
                        )
                    )
                    await session.flush()
            continue

        # Иначе ищем заявки с той же почтой или телефоном.
        conditions = []
        if learner.email:
            conditions.append(LearningApplication.email == learner.email)
        if learner.phone:
            conditions.append(LearningApplication.phone == learner.phone)
        if conditions:
            applications = (
                await session.execute(select(LearningApplication).where(or_(*conditions)))
            ).scalars()
            for application in applications:
                await enroll_by_contact(session, application)
    return stats


# Ручное сопоставление


async def apply_course_mapping(
    session: AsyncSession, source_id: uuid.UUID, key: str, program_id: uuid.UUID
) -> int:
    """Курс сопоставлен с программой: его заявки получают программу и зачисления."""
    applications = list(
        (
            await session.execute(
                select(LearningApplication).where(
                    LearningApplication.source_id == source_id,
                    LearningApplication.program_id.is_(None),
                )
            )
        ).scalars()
    )
    matched = [item for item in applications if normalize_course(item.course_name) == key]
    for application in matched:
        application.program_id = program_id
        await session.flush()
        await enroll_by_contact(session, application)
    await session.execute(
        update(LearningStream)
        .where(LearningStream.source_id == source_id, LearningStream.program_id.is_(None))
        .where(LearningStream.external_id.like(f"auto:{key}:%"))
        .values(program_id=program_id)
    )
    return len(matched)


# Запуск


async def _apply(
    session: AsyncSession,
    source: IntegrationSource,
    payload: IntegrationPayload,
    user: User | None,
) -> SyncStats:
    total = SyncStats()
    for part in (
        await _sync_programs(session, source, payload),
        await _sync_products(session, source, payload),
        await _sync_universities(session, source, payload),
        await _sync_requests(session, source, payload, user),
        await _sync_applications(session, source, payload),
        await _sync_learners(session, source, payload),
    ):
        total.received += part.received
        total.created += part.created
        total.updated += part.updated
        total.failed += part.failed
        total.pending += part.pending
        total.notes.extend(part.notes)
        total.errors.extend(part.errors)

    if payload.skipped:
        total.failed += payload.skipped
        total.received += payload.skipped
        total.errors.append(
            (
                "record",
                None,
                f"Пропущено записей без обязательных полей или пустых: {payload.skipped}",
            )
        )
    if payload.dropped_fields:
        total.notes.append(
            "Не сохранены лишние персональные данные (минимизация по 152-ФЗ): "
            + ", ".join(sorted(payload.dropped_fields))
        )
    if total.pending:
        total.notes.append(
            f"Ждут ручного сопоставления: {total.pending} - раздел «LMS и сайт», "
            "вкладка «Сопоставление»"
        )
    return total


async def run_sync(
    session: AsyncSession,
    code: str,
    user: User | None,
    raw: object | None = None,
    filename: str | None = None,
    trigger: str = "manual",
) -> IntegrationRun:
    """Выполняет синхронизацию и пишет результат в журнал запусков.

    raw: ответ источника, загруженный файлом. Его разбирает тот же адаптер.
    """
    source = await get_source(session, code)
    if not source.is_enabled:
        raise AppError(f"Источник «{source.name}» выключен", code=ErrorCode.INTEGRATION_FAILED)

    run = IntegrationRun(
        source_id=source.id,
        triggered_by=user.id if user else None,
        trigger="file" if raw is not None else trigger,
        status=IntegrationRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()

    try:
        adapter = build_adapter(code)
        payload = adapter.parse(raw) if raw is not None else await adapter.fetch()
        run.attempts = payload.attempts
        # Точка сохранения: сбой разбора откатит только данные этого запуска,
        # а запись о неудачном запуске останется.
        async with session.begin_nested():
            stats = await _apply(session, source, payload, user)
    except AppError as exc:
        # Сбой сети или неожиданный ответ записываем как неудачный запуск,
        # а не роняем запрос.
        run.status = IntegrationRunStatus.FAILED
        run.error_message = exc.message
        run.attempts = int((exc.details or {}).get("attempts", run.attempts))
        run.finished_at = datetime.now(UTC)
        await session.flush()
        return run

    run.status = (
        IntegrationRunStatus.PARTIAL
        if stats.failed or stats.errors
        else IntegrationRunStatus.SUCCESS
    )
    run.records_received = stats.received
    run.records_created = stats.created
    run.records_updated = stats.updated
    run.records_failed = stats.failed
    run.records_pending = stats.pending
    notes = ([f"Данные загружены файлом «{filename}»"] if filename else []) + stats.notes
    run.notes = "\n".join(notes) or None
    run.finished_at = datetime.now(UTC)
    for entity_type, external_id, message in stats.errors:
        session.add(
            IntegrationRunError(
                run_id=run.id,
                entity_type=entity_type,
                external_id=external_id,
                message=message,
            )
        )
    await session.flush()
    return run


async def list_runs(
    session: AsyncSession, source_code: str | None, limit: int, offset: int
) -> list[IntegrationRun]:
    statement = (
        select(IntegrationRun)
        .options(selectinload(IntegrationRun.source), selectinload(IntegrationRun.errors))
        .order_by(IntegrationRun.started_at.desc().nullslast())
        .limit(limit)
        .offset(offset)
    )
    if source_code:
        statement = statement.join(IntegrationSource).where(
            IntegrationSource.code == source_code
        )
    return list((await session.execute(statement)).scalars())


def group_errors(errors: list[tuple[str, str | None, str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for entity_type, external_id, message in errors:
        grouped[entity_type].append(f"{external_id or '—'}: {message}")
    return grouped
