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
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, ErrorCode, NotFoundError
from app.enums import ContractStatus, IntegrationRunStatus
from app.models.catalog import ItDirection, ItProduct, ItProgram, Vendor
from app.models.contract import Contract, ContractProgram
from app.models.integration import ExternalLink, IntegrationRun, IntegrationSource
from app.models.university import University, UniversityContact
from app.models.user import User
from app.models.workflow import WorkflowTemplate, WorkflowVersion
from app.services import workflow as workflow_service
from app.services.integrations.base import IntegrationPayload, SourceAdapter
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
    ):
        total.received += part.received
        total.created += part.created
        total.updated += part.updated
        total.failed += part.failed
    return total


async def run_sync(session: AsyncSession, code: str, user: User) -> IntegrationRun:
    """Выполняет синхронизацию и записывает результат в журнал запусков."""
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
        payload = await build_adapter(code).fetch()
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
