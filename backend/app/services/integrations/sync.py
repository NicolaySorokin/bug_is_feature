"""Синхронизация с внешними системами.

Адаптер отдаёт данные в общем виде, а этот модуль решает, что с ними делать:
обновляет справочники, вузы и контакты, а по новым заявкам заводит договор
и запускает рабочий процесс.

Повторный запуск не плодит дубли: для каждой внешней записи хранится связь
``external_links`` - «объект источника X с идентификатором Y - это вот эта
наша запись». Пока связи нет, запись ищется по названию, а уже потом
создаётся.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, ErrorCode, NotFoundError
from app.enums import ContractStatus, IntegrationRunStatus, WorkflowInstanceStatus
from app.models.catalog import ItDirection, ItProduct, ItProgram, Vendor
from app.models.content import Comment
from app.models.contract import Contract, ContractProgram
from app.models.integration import ExternalLink, IntegrationRun, IntegrationSource
from app.models.learning import Learner, LearningApplication
from app.models.university import University, UniversityContact
from app.models.user import User
from app.models.workflow import (
    WorkflowEvent,
    WorkflowInstance,
    WorkflowTemplate,
    WorkflowVersion,
)
from app.services import workflow as workflow_service
from app.services.integrations.base import (
    ExternalApplication,
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
CONTRACT = "contract"


@dataclass(slots=True)
class SyncStats:
    received: int = 0
    created: int = 0
    updated: int = 0
    failed: int = 0
    notes: list[str] = field(default_factory=list)


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
    if source is None:  # pragma: no cover - ensure_sources только что его создал
        raise NotFoundError(f"Источник «{code}» не найден")
    return source


# --- Связи с внешними объектами ----------------------------------------------


async def _linked_id(
    session: AsyncSession, source_id: uuid.UUID, entity_type: str, external_id: str
) -> uuid.UUID | None:
    return await session.scalar(
        select(ExternalLink.entity_id).where(
            ExternalLink.source_id == source_id,
            ExternalLink.entity_type == entity_type,
            ExternalLink.external_id == external_id,
        )
    )


async def _linked_anywhere(
    session: AsyncSession, entity_type: str, external_id: str
) -> uuid.UUID | None:
    """Поиск по всем источникам: заявка с сайта ссылается на программы LMS."""
    return await session.scalar(
        select(ExternalLink.entity_id).where(
            ExternalLink.entity_type == entity_type,
            ExternalLink.external_id == external_id,
        )
    )


async def _remember(
    session: AsyncSession,
    source_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    external_id: str,
) -> None:
    if await _linked_id(session, source_id, entity_type, external_id) is not None:
        return
    session.add(
        ExternalLink(
            source_id=source_id,
            entity_type=entity_type,
            entity_id=entity_id,
            external_id=external_id,
        )
    )
    await session.flush()


# --- Справочники --------------------------------------------------------------


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


async def _sync_programs(
    session: AsyncSession, source: IntegrationSource, payload: IntegrationPayload
) -> SyncStats:
    stats = SyncStats()
    for item in payload.programs:
        stats.received += 1
        direction = await _direction(session, item.direction_name)
        entity_id = await _linked_id(session, source.id, PROGRAM, item.external_id)
        program = (
            await session.get(ItProgram, entity_id)
            if entity_id
            else await session.scalar(select(ItProgram).where(ItProgram.name == item.name))
        )
        if program is None:
            program = ItProgram(
                name=item.name,
                description=item.description,
                direction_id=direction.id if direction else None,
            )
            session.add(program)
            await session.flush()
            stats.created += 1
        else:
            program.name = item.name
            program.description = item.description or program.description
            if direction is not None:
                program.direction_id = direction.id
            stats.updated += 1
        await _remember(session, source.id, PROGRAM, program.id, item.external_id)
    return stats


async def _sync_products(
    session: AsyncSession, source: IntegrationSource, payload: IntegrationPayload
) -> SyncStats:
    stats = SyncStats()
    for item in payload.products:
        stats.received += 1
        vendor = await _vendor(session, item.vendor_name)
        entity_id = await _linked_id(session, source.id, PRODUCT, item.external_id)
        product = (
            await session.get(ItProduct, entity_id)
            if entity_id
            else await session.scalar(select(ItProduct).where(ItProduct.name == item.name))
        )
        if product is None:
            product = ItProduct(
                name=item.name,
                description=item.description,
                vendor_id=vendor.id if vendor else None,
            )
            session.add(product)
            await session.flush()
            stats.created += 1
        else:
            product.name = item.name
            product.description = item.description or product.description
            if vendor is not None:
                product.vendor_id = vendor.id
            stats.updated += 1
        await _remember(session, source.id, PRODUCT, product.id, item.external_id)
    return stats


# --- Вузы ---------------------------------------------------------------------


async def _sync_universities(
    session: AsyncSession, source: IntegrationSource, payload: IntegrationPayload
) -> SyncStats:
    stats = SyncStats()
    for item in payload.universities:
        stats.received += 1
        entity_id = await _linked_id(session, source.id, UNIVERSITY, item.external_id)
        university = (
            await session.get(University, entity_id)
            if entity_id
            else await session.scalar(
                select(University).where(University.name == item.name)
            )
        )
        if university is None:
            university = University(
                name=item.name,
                short_name=item.short_name,
                city=item.city,
                website=item.website,
            )
            session.add(university)
            await session.flush()
            stats.created += 1
        else:
            university.short_name = item.short_name or university.short_name
            university.city = item.city or university.city
            university.website = item.website or university.website
            stats.updated += 1

        await _sync_contacts(session, university, item.contacts)
        await _remember(session, source.id, UNIVERSITY, university.id, item.external_id)
    return stats


async def _sync_contacts(session: AsyncSession, university: University, contacts) -> None:
    """Контакты сопоставляются по ФИО внутри вуза: внешних идентификаторов у них нет."""
    if not contacts:
        return
    existing = {
        contact.full_name: contact
        for contact in (
            await session.execute(
                select(UniversityContact).where(
                    UniversityContact.university_id == university.id
                )
            )
        ).scalars()
    }
    for contact in contacts:
        current = existing.get(contact.full_name)
        if current is None:
            session.add(
                UniversityContact(
                    university_id=university.id,
                    full_name=contact.full_name,
                    position=contact.position,
                    email=contact.email,
                    phone=contact.phone,
                )
            )
        else:
            current.position = contact.position or current.position
            current.email = contact.email or current.email
            current.phone = contact.phone or current.phone
    await session.flush()


# --- Заявки -------------------------------------------------------------------


async def _default_version(session: AsyncSession) -> WorkflowVersion | None:
    """Текущая версия основного шаблона процесса."""
    template = await session.scalar(
        select(WorkflowTemplate)
        .where(WorkflowTemplate.is_active.is_(True))
        .order_by(WorkflowTemplate.created_at)
        .limit(1)
    )
    if template is None:
        return None
    try:
        return await workflow_service.latest_published_version(session, template.id)
    except workflow_service.WorkflowError:
        return None


async def _sync_requests(
    session: AsyncSession,
    source: IntegrationSource,
    payload: IntegrationPayload,
    user: User,
) -> SyncStats:
    """Каждая новая заявка становится договором-черновиком с запущенным процессом."""
    stats = SyncStats()
    version = await _default_version(session)

    for item in payload.requests:
        stats.received += 1
        if await _linked_id(session, source.id, CONTRACT, item.external_id) is not None:
            stats.updated += 1  # заявка уже разобрана в прошлый раз
            continue

        university_id = await _linked_id(
            session, source.id, UNIVERSITY, item.university_external_id
        )
        if university_id is None:
            stats.failed += 1
            continue

        university = await session.get(University, university_id)
        contract = Contract(
            university_id=university_id,
            manager_id=(university.manager_id if university else None) or user.id,
            number=f"ЗАЯВКА-{item.external_id}",
            title="Заявка с сайта ИТ Школы",
            status=ContractStatus.DRAFT,
            comment=item.comment,
        )
        session.add(contract)
        await session.flush()

        for external_program_id in item.program_external_ids:
            program_id = await _linked_anywhere(session, PROGRAM, external_program_id)
            if program_id is not None:
                session.add(
                    ContractProgram(contract_id=contract.id, program_id=program_id)
                )
        await session.flush()

        if version is not None:
            await workflow_service.start_instance(session, contract.id, version, user)

        await _remember(session, source.id, CONTRACT, contract.id, item.external_id)
        stats.created += 1
    return stats


# --- Заявки на обучение ---------------------------------------------------------


async def _program_by_course(
    session: AsyncSession, course: str, created: list[str]
) -> ItProgram:
    """Программа по названию курса; неизвестный курс заводится в справочник."""
    program = await session.scalar(
        select(ItProgram).where(func.lower(ItProgram.name) == course.lower()).limit(1)
    )
    if program is None:
        program = ItProgram(
            name=course,
            description="Заведена автоматически по заявке с сайта: уточните направление",
        )
        session.add(program)
        await session.flush()
        created.append(course)
    return program


async def _university_by_name(session: AsyncSession, name: str) -> University | None:
    value = name.lower()
    return await session.scalar(
        select(University)
        .where(
            or_(
                func.lower(University.name) == value,
                func.lower(University.short_name) == value,
            )
        )
        .limit(1)
    )


async def _contract_for(
    session: AsyncSession,
    university: University,
    program: ItProgram,
    user: User,
    version: WorkflowVersion | None,
    opened: list[str],
) -> Contract:
    """Договор вуза, в процесс которого попадает заявка.

    Сначала ищется действующий договор (или черновик) с этой программой -
    заявка добавляется в его процесс. Нет такого - заводится черновик
    договора с программой и по нему запускается процесс по основному шаблону.
    """
    contract = await session.scalar(
        select(Contract)
        .join(ContractProgram, ContractProgram.contract_id == Contract.id)
        .where(
            Contract.university_id == university.id,
            ContractProgram.program_id == program.id,
            Contract.status.in_([ContractStatus.ACTIVE, ContractStatus.DRAFT]),
        )
        .order_by(Contract.created_at.desc())
        .limit(1)
    )
    if contract is not None:
        return contract

    contract = Contract(
        university_id=university.id,
        manager_id=university.manager_id or user.id,
        number=f"ЗАЯВКИ-{(university.short_name or university.name)[:40]}-{program.name[:30]}",
        title=f"Заявки на программу «{program.name}»",
        status=ContractStatus.DRAFT,
        comment="Заведён автоматически: с сайта пришли заявки на программу, договора ещё нет",
    )
    session.add(contract)
    await session.flush()
    session.add(ContractProgram(contract_id=contract.id, program_id=program.id))
    await session.flush()
    if version is not None:
        await workflow_service.start_instance(session, contract.id, version, user)
    opened.append(contract.number)
    return contract


async def _note_in_process(
    session: AsyncSession,
    contract_id: uuid.UUID,
    applications: list[ExternalApplication],
    user: User,
) -> None:
    """Сводка о новых заявках - комментарием к текущему шагу процесса договора."""
    event_id = await session.scalar(
        select(WorkflowEvent.id)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowEvent.workflow_instance_id)
        .where(
            WorkflowInstance.contract_id == contract_id,
            WorkflowInstance.status.in_(
                [WorkflowInstanceStatus.IN_PROGRESS, WorkflowInstanceStatus.BLOCKED]
            ),
        )
        .order_by(WorkflowEvent.created_at.desc())
        .limit(1)
    )
    lines = [
        f"• {item.external_id}: «{item.course_name}»"
        + (f", поток {item.stream_number}" if item.stream_number else "")
        for item in applications
    ]
    session.add(
        Comment(
            contract_id=contract_id,
            workflow_event_id=event_id,
            author_id=user.id,
            text=f"С сайта поступили заявки на обучение ({len(applications)}):\n"
            + "\n".join(lines),
        )
    )
    await session.flush()


async def _sync_applications(
    session: AsyncSession,
    source: IntegrationSource,
    payload: IntegrationPayload,
    user: User,
) -> SyncStats:
    """Заявки с сайта: в статистику спроса и, если известен вуз, - в процесс."""
    stats = SyncStats()
    if not payload.applications:
        return stats

    now = datetime.now(UTC)
    programs_created: list[str] = []
    contracts_opened: list[str] = []
    new_by_contract: dict[uuid.UUID, list[ExternalApplication]] = defaultdict(list)
    unknown_universities: set[str] = set()
    version = None

    for item in payload.applications:
        stats.received += 1
        program = await _program_by_course(session, item.course_name, programs_created)

        application = await session.scalar(
            select(LearningApplication).where(
                LearningApplication.source_id == source.id,
                LearningApplication.external_id == item.external_id,
            )
        )
        is_new = application is None
        if is_new:
            application = LearningApplication(
                source_id=source.id,
                external_id=item.external_id,
                submitted_at=item.submitted_at or date_from_number(item.external_id) or now,
            )
            session.add(application)
            stats.created += 1
        else:
            stats.updated += 1

        application.program_id = program.id
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
            elif application.contract_id is None:
                if version is None:
                    version = await _default_version(session)
                contract = await _contract_for(
                    session, university, program, user, version, contracts_opened
                )
                application.university_id = university.id
                application.contract_id = contract.id
                new_by_contract[contract.id].append(item)
        await session.flush()

    for contract_id, items in new_by_contract.items():
        await _note_in_process(session, contract_id, items, user)

    if programs_created:
        stats.notes.append(
            "Новые курсы заведены в справочник программ (уточните направление): "
            + ", ".join(sorted(set(programs_created)))
        )
    if new_by_contract:
        stats.notes.append(
            f"Заявки добавлены в процессы по договорам: {len(new_by_contract)}"
            + (
                f", из них новых договоров: {len(contracts_opened)}"
                if contracts_opened
                else ""
            )
        )
    if unknown_universities:
        stats.notes.append(
            "Вузы не найдены в справочнике, заявки учтены только в статистике: "
            + ", ".join(sorted(unknown_universities))
        )
    return stats


# --- Обучающиеся из LMS ------------------------------------------------------------


async def _sync_learners(
    session: AsyncSession, source: IntegrationSource, payload: IntegrationPayload
) -> SyncStats:
    stats = SyncStats()
    for item in payload.learners:
        stats.received += 1
        learner = None
        if item.email:
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
        learner.last_name = item.last_name
        learner.first_name = item.first_name
        learner.middle_name = item.middle_name
        learner.email = item.email or learner.email
        learner.phone = item.phone or learner.phone
        learner.gender = item.gender or learner.gender
        learner.education = item.education or learner.education
        learner.region = item.region or learner.region
        await session.flush()
    return stats


# --- Запуск -------------------------------------------------------------------


async def _apply(
    session: AsyncSession,
    source: IntegrationSource,
    payload: IntegrationPayload,
    user: User,
) -> SyncStats:
    total = SyncStats()
    for part in (
        await _sync_programs(session, source, payload),
        await _sync_products(session, source, payload),
        await _sync_universities(session, source, payload),
        await _sync_requests(session, source, payload, user),
        await _sync_applications(session, source, payload, user),
        await _sync_learners(session, source, payload),
    ):
        total.received += part.received
        total.created += part.created
        total.updated += part.updated
        total.failed += part.failed
        total.notes.extend(part.notes)

    if payload.skipped:
        total.failed += payload.skipped
        total.received += payload.skipped
        total.notes.append(
            f"Пропущено записей без обязательных полей или пустых: {payload.skipped}"
        )
    if payload.dropped_fields:
        total.notes.append(
            "Не сохранены лишние персональные данные (минимизация по 152-ФЗ): "
            + ", ".join(sorted(payload.dropped_fields))
        )
    return total


async def run_sync(
    session: AsyncSession,
    code: str,
    user: User,
    raw: object | None = None,
    filename: str | None = None,
) -> IntegrationRun:
    """Выполняет синхронизацию и записывает результат в журнал запусков.

    ``raw`` - ответ источника, переданный файлом (например, выгрузка API,
    полученная до того, как открыли сетевой доступ). Разбирается тем же
    адаптером, что и ответ по сети, поэтому путь данных один.
    """
    source = await get_source(session, code)
    if not source.is_enabled:
        raise AppError(
            f"Источник «{source.name}» выключен", code=ErrorCode.INTEGRATION_FAILED
        )

    run = IntegrationRun(
        source_id=source.id,
        triggered_by=user.id,
        status=IntegrationRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()

    try:
        adapter = build_adapter(code)
        payload = adapter.parse(raw) if raw is not None else await adapter.fetch()
        # Точка сохранения: сбой разбора откатит только данные этого запуска,
        # а сама запись о неудачном запуске останется в журнале.
        async with session.begin_nested():
            stats = await _apply(session, source, payload, user)
    except AppError as exc:
        # Сетевые сбои и неожиданный формат ответа - ожидаемый исход обмена,
        # поэтому не роняем запрос, а записываем неудачный запуск.
        run.status = IntegrationRunStatus.FAILED
        run.error_message = exc.message
        run.finished_at = datetime.now(UTC)
        await session.flush()
        return run

    run.status = IntegrationRunStatus.SUCCESS
    run.records_received = stats.received
    run.records_created = stats.created
    run.records_updated = stats.updated
    run.records_failed = stats.failed
    notes = ([f"Данные загружены файлом «{filename}»"] if filename else []) + stats.notes
    run.notes = "\n".join(notes) or None
    run.finished_at = datetime.now(UTC)
    await session.flush()
    return run


async def list_runs(
    session: AsyncSession, source_code: str | None, limit: int, offset: int
) -> list[IntegrationRun]:
    statement = (
        select(IntegrationRun)
        .options(selectinload(IntegrationRun.source))
        .order_by(IntegrationRun.started_at.desc().nullslast())
        .limit(limit)
        .offset(offset)
    )
    if source_code:
        statement = statement.join(IntegrationSource).where(
            IntegrationSource.code == source_code
        )
    return list((await session.execute(statement)).scalars())
