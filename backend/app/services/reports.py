"""Сбор данных для отчётов и диаграмм.

Порядок работы такой: один запрос отбирает взаимодействия по фильтрам,
дальше из них разворачиваются строки отчёта «взаимодействие - программа»,
а диаграммы считаются уже по этим строкам. Благодаря этому табличная часть
и диаграммы всегда описывают одну и ту же выборку (раздел 6.1 концепции).

Пункты 23-25 перечня исправлений:

* статус работы с вузом - статус взаимодействия, договор - необязательный
  блок; есть фильтры по результату, источнику и причине закрытия;
* в строке программы - только продукты, фактически связанные с ней;
  программы и продукты считаются по идентификаторам, а не по названиям;
* фильтры по программам, направлениям и продуктам сужают и строки: другие
  программы тех же взаимодействий в отчёт не попадают;
* период «по дате подписания» не подменяется датой заведения:
  взаимодействие без подписанного договора в такой отчёт не входит,
  и их число показывается отдельно.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, date, datetime

from sqlalchemy import Date, Select, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import Principal
from app.enums import InteractionStatus
from app.models.catalog import ItProgram
from app.models.contract import Contract
from app.models.interaction import InteractionProduct, InteractionProgram
from app.models.user import User
from app.models.workflow import WorkflowEvent, WorkflowInstance
from app.schemas.report import (
    COLUMN_TITLES,
    ChartData,
    ChartItem,
    ChartKey,
    PeriodBasis,
    ReportFilters,
    ReportRequest,
    ReportResponse,
    ReportRow,
    ReportTotals,
)
from app.services import access, cache
from app.services.labels import (
    CLOSURE_REASON_LABELS,
    CONTRACT_STATUS_LABELS,
    INTERACTION_STATUS_LABELS,
    OUTCOME_LABELS,
    PROGRAM_STATUS_LABELS,
    SOURCE_LABELS,
    label,
)

# Сколько позиций показывать на диаграммах со списком названий.
TOP_LIMIT = 10
NO_VALUE = "Не указано"
NO_PROCESS = "Процесс не запущен"


def _apply_filters(statement: Select, filters: ReportFilters) -> Select:
    if filters.university_ids:
        statement = statement.where(WorkflowInstance.university_id.in_(filters.university_ids))
    if filters.manager_ids:
        statement = statement.where(WorkflowInstance.manager_id.in_(filters.manager_ids))
    if filters.statuses:
        statement = statement.where(WorkflowInstance.status.in_(filters.statuses))
    if filters.outcomes:
        statement = statement.where(WorkflowInstance.outcome.in_(filters.outcomes))
    if filters.closure_reasons:
        statement = statement.where(
            WorkflowInstance.closure_reason.in_(filters.closure_reasons)
        )
    if filters.sources:
        statement = statement.where(WorkflowInstance.source.in_(filters.sources))
    if filters.contract_statuses:
        statement = statement.where(
            WorkflowInstance.id.in_(
                select(Contract.workflow_instance_id).where(
                    Contract.status.in_(filters.contract_statuses)
                )
            )
        )
    if filters.program_ids:
        statement = statement.where(
            WorkflowInstance.id.in_(
                select(InteractionProgram.workflow_instance_id).where(
                    InteractionProgram.program_id.in_(filters.program_ids)
                )
            )
        )
    if filters.direction_ids:
        statement = statement.where(
            WorkflowInstance.id.in_(
                select(InteractionProgram.workflow_instance_id)
                .join(ItProgram, ItProgram.id == InteractionProgram.program_id)
                .where(ItProgram.direction_id.in_(filters.direction_ids))
            )
        )
    if filters.product_ids:
        statement = statement.where(
            WorkflowInstance.id.in_(
                select(InteractionProduct.workflow_instance_id).where(
                    InteractionProduct.product_id.in_(filters.product_ids)
                )
            )
        )
    if filters.stage_ids:
        statement = statement.where(WorkflowInstance.current_stage_id.in_(filters.stage_ids))
    return statement


def _between(column, filters: ReportFilters) -> list:  # noqa: ANN001 - выражение SQLAlchemy
    conditions = []
    if filters.date_from is not None:
        conditions.append(column >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(column <= filters.date_to)
    return conditions


def _has_period(filters: ReportFilters) -> bool:
    return filters.date_from is not None or filters.date_to is not None


def _apply_period(statement: Select, filters: ReportFilters) -> Select:
    """Период применяется к разной дате в зависимости от основания выборки."""
    if not _has_period(filters):
        return statement
    if filters.period_basis is PeriodBasis.ACTIVITY:
        activity = select(WorkflowEvent.workflow_instance_id).where(
            *_between(cast(WorkflowEvent.created_at, Date), filters)
        )
        return statement.where(WorkflowInstance.id.in_(activity))
    if filters.period_basis is PeriodBasis.SIGNED:
        # Дата подписания не подменяется датой заведения: без подписанного
        # договора взаимодействие в отчёт «по подписанию» не входит.
        signed = select(Contract.workflow_instance_id).where(
            Contract.signed_at.is_not(None), *_between(Contract.signed_at, filters)
        )
        return statement.where(WorkflowInstance.id.in_(signed))
    if filters.period_basis is PeriodBasis.CLOSED:
        return statement.where(*_between(cast(WorkflowInstance.closed_at, Date), filters))
    return statement.where(*_between(cast(WorkflowInstance.created_at, Date), filters))


def _options() -> list:
    return [
        selectinload(WorkflowInstance.university),
        selectinload(WorkflowInstance.manager),
        selectinload(WorkflowInstance.current_stage),
        selectinload(WorkflowInstance.contract),
        selectinload(WorkflowInstance.programs)
        .selectinload(InteractionProgram.program)
        .selectinload(ItProgram.direction),
        selectinload(WorkflowInstance.programs).selectinload(InteractionProgram.product_links),
        selectinload(WorkflowInstance.products).selectinload(InteractionProduct.product),
    ]


async def fetch_interactions(
    session: AsyncSession,
    filters: ReportFilters,
    principal: Principal,
    user: User,
) -> list[WorkflowInstance]:
    """Взаимодействия выборки со всем, что нужно строкам отчёта."""
    statement = (
        select(WorkflowInstance)
        .options(*_options())
        .order_by(WorkflowInstance.created_at.desc())
    )
    statement = _apply_period(_apply_filters(statement, filters), filters)
    statement = access.apply_interaction_scope(statement, principal, user)
    result = await session.execute(statement)
    return list(result.scalars().unique())


async def count_unsigned_excluded(
    session: AsyncSession, filters: ReportFilters, principal: Principal, user: User
) -> int:
    """Сколько взаимодействий не вошли в отчёт «по подписанию» из-за
    отсутствия подписанного договора."""
    if filters.period_basis is not PeriodBasis.SIGNED or not _has_period(filters):
        return 0
    statement = _apply_filters(select(func.count()).select_from(WorkflowInstance), filters)
    statement = statement.where(
        WorkflowInstance.id.not_in(
            select(Contract.workflow_instance_id).where(Contract.signed_at.is_not(None))
        )
    )
    statement = access.apply_interaction_scope(statement, principal, user)
    return await session.scalar(statement) or 0


def days_on_stage(instance: WorkflowInstance) -> int | None:
    if instance.current_stage_started_at is None or instance.status not in (
        InteractionStatus.IN_PROGRESS,
        InteractionStatus.BLOCKED,
    ):
        return None
    return (datetime.now(UTC) - instance.current_stage_started_at).days


def stage_title(instance: WorkflowInstance) -> str:
    if instance.status == InteractionStatus.DRAFT or instance.current_stage is None:
        return NO_PROCESS
    name = instance.current_stage.name
    if instance.status == InteractionStatus.COMPLETED:
        return f"{name} (завершено)"
    if instance.status == InteractionStatus.CANCELLED:
        return f"{name} (отменено)"
    if instance.status == InteractionStatus.BLOCKED:
        return f"{name} (заблокировано)"
    return name


def _composition_filtered(filters: ReportFilters | None) -> bool:
    return filters is not None and bool(
        filters.program_ids or filters.direction_ids or filters.product_ids
    )


def _program_matches(
    link: InteractionProgram,
    products_by_id: dict[uuid.UUID, InteractionProduct],
    filters: ReportFilters,
) -> bool:
    """Строка программы подходит под фильтры по программам, направлениям и продуктам.

    Отбор взаимодействий идёт в базе, но у взаимодействия бывают и другие
    программы: отчёт «по направлению Разработка» не должен показывать строку
    программы из тестирования. Продукт - по фактической связи с программой.
    """
    if filters.program_ids and link.program_id not in filters.program_ids:
        return False
    if filters.direction_ids and (
        link.program is None or link.program.direction_id not in filters.direction_ids
    ):
        return False
    if filters.product_ids:
        used = {
            products_by_id[item.interaction_product_id].product_id
            for item in link.product_links
            if item.interaction_product_id in products_by_id
        }
        if not used.intersection(filters.product_ids):
            return False
    return True


def build_rows(
    interactions: list[WorkflowInstance], filters: ReportFilters | None = None
) -> list[ReportRow]:
    """Разворачивает взаимодействия в строки «взаимодействие - ИТ-программа».

    С фильтрами по программам, направлениям или продуктам в отчёт идут только
    подходящие программы взаимодействия - таблица и диаграммы описывают
    ровно то, что выбрано.
    """
    rows: list[ReportRow] = []
    narrowed = _composition_filtered(filters)
    for instance in interactions:
        contract = instance.contract
        university = instance.university
        products_by_id = {link.id: link for link in instance.products}
        base = {
            "interaction_id": instance.id,
            "university_id": instance.university_id,
            "university": (university.short_name or university.name)
            if university
            else NO_VALUE,
            "university_full": university.name if university else "",
            "interaction": instance.title or "",
            "status": InteractionStatus(instance.status),
            "status_label": label(INTERACTION_STATUS_LABELS, instance.status),
            "stage": stage_title(instance),
            "days_on_stage": days_on_stage(instance),
            "manager_id": instance.manager_id,
            "manager": instance.manager.full_name if instance.manager else NO_VALUE,
            "outcome": instance.outcome,
            "outcome_label": label(OUTCOME_LABELS, instance.outcome),
            "closure_reason": instance.closure_reason,
            "closure_reason_label": label(CLOSURE_REASON_LABELS, instance.closure_reason),
            "source": instance.source,
            "source_label": label(SOURCE_LABELS, instance.source),
            "contract_number": contract.number if contract else "",
            "contract_status": contract.status if contract else None,
            "contract_status_label": label(CONTRACT_STATUS_LABELS, contract.status)
            if contract
            else "",
            "signed_at": contract.signed_at if contract else None,
            "valid_to": contract.valid_to if contract else None,
            "created_at": instance.created_at.date() if instance.created_at else None,
            "closed_at": instance.closed_at.date() if instance.closed_at else None,
            "comment": instance.comment or "",
        }

        if not instance.programs:
            # Взаимодействие без программ - тоже строка отчёта, но не в отчёте,
            # суженном до конкретных программ, направлений или продуктов.
            if not narrowed:
                rows.append(ReportRow(**base))
            continue

        links = sorted(
            instance.programs, key=lambda item: item.program.name if item.program else ""
        )
        if narrowed:
            links = [link for link in links if _program_matches(link, products_by_id, filters)]
        for link in links:
            program = link.program
            direction = program.direction if program else None
            linked = [
                products_by_id[item.interaction_product_id]
                for item in link.product_links
                if item.interaction_product_id in products_by_id
            ]
            rows.append(
                ReportRow(
                    **base,
                    direction=direction.name if direction else NO_VALUE,
                    program_id=link.program_id,
                    program=program.name if program else NO_VALUE,
                    product_ids=sorted(item.product_id for item in linked),
                    product=", ".join(
                        sorted(item.product.name for item in linked if item.product)
                    ),
                    implementation_status=link.implementation_status,
                    implementation_status_label=label(
                        PROGRAM_STATUS_LABELS, link.implementation_status
                    ),
                )
            )
    return rows


def top_items(counter: Counter[str], limit: int = TOP_LIMIT) -> list[ChartItem]:
    """Крупнейшие позиции, остальные - одной строкой «Прочие».

    Сумма значений на диаграмме при этом совпадает с выборкой: ничего
    не теряется, просто хвост сворачивается.
    """
    ordered = counter.most_common()
    if len(ordered) <= limit:
        return [ChartItem(label=name, value=value) for name, value in ordered]
    head = ordered[:limit]
    rest = sum(value for _, value in ordered[limit:])
    return [
        *(ChartItem(label=name, value=value) for name, value in head),
        ChartItem(label="Прочие", value=rest),
    ]


def build_charts(rows: list[ReportRow], *, with_managers: bool = True) -> list[ChartData]:
    """Диаграммы по той же выборке, что и таблица."""
    seen: set[uuid.UUID] = set()
    by_status: Counter[str] = Counter()
    by_outcome: Counter[str] = Counter()
    by_stage: Counter[str] = Counter()
    by_university: Counter[str] = Counter()
    by_manager: Counter[str] = Counter()

    for row in rows:
        if row.interaction_id in seen:
            continue
        seen.add(row.interaction_id)
        by_status[row.status_label] += 1
        if row.outcome_label:
            by_outcome[row.outcome_label] += 1
        if row.status in (InteractionStatus.IN_PROGRESS, InteractionStatus.BLOCKED):
            by_stage[row.stage.replace(" (заблокировано)", "")] += 1
        by_university[row.university] += 1
        by_manager[row.manager] += 1

    # Направления и программы - по строкам состава: одна программа - одна строка.
    by_direction = Counter(row.direction for row in rows if row.direction)
    by_program = Counter(row.program for row in rows if row.program)

    charts = [
        ChartData(
            key=ChartKey.BY_STATUS,
            title="Взаимодействия по статусам",
            measure="взаимодействий",
            items=[ChartItem(label=name, value=value) for name, value in by_status.items()],
        ),
        ChartData(
            key=ChartKey.BY_OUTCOME,
            title="Результаты закрытых взаимодействий",
            measure="взаимодействий",
            items=[ChartItem(label=name, value=value) for name, value in by_outcome.items()],
        ),
        ChartData(
            key=ChartKey.BY_STAGE,
            title="Текущие этапы взаимодействий в работе",
            measure="взаимодействий",
            items=top_items(by_stage),
        ),
        ChartData(
            key=ChartKey.BY_DIRECTION,
            title="Программы по ИТ-направлениям",
            measure="программ во взаимодействиях",
            items=top_items(by_direction),
        ),
        ChartData(
            key=ChartKey.BY_PROGRAM,
            title="Взаимодействия по ИТ-программам",
            measure="взаимодействий",
            items=top_items(by_program),
        ),
        ChartData(
            key=ChartKey.BY_UNIVERSITY,
            title="Взаимодействия по вузам",
            measure="взаимодействий",
            items=top_items(by_university),
        ),
    ]
    if with_managers:
        charts.append(
            ChartData(
                key=ChartKey.BY_MANAGER,
                title="Нагрузка ответственных",
                measure="взаимодействий",
                items=top_items(by_manager),
            )
        )
    return charts


def build_totals(rows: list[ReportRow], unsigned_excluded: int = 0) -> ReportTotals:
    """Итоги по идентификаторам: одноимённые программы или продукты не сливаются."""
    products: set[uuid.UUID] = set()
    for row in rows:
        products.update(row.product_ids)
    return ReportTotals(
        rows=len(rows),
        interactions=len({row.interaction_id for row in rows}),
        universities=len({row.university_id for row in rows}),
        programs=len({row.program_id for row in rows if row.program_id}),
        products=len(products),
        contracts=len({row.interaction_id for row in rows if row.contract_number}),
        unsigned_excluded=unsigned_excluded,
    )


async def build_report(
    session: AsyncSession,
    request: ReportRequest,
    principal: Principal,
    user: User,
) -> ReportResponse:
    """Выборка отчёта. Одинаковые запросы одного пользователя берутся из кэша:
    предпросмотр, выгрузка и диаграмма по тем же фильтрам считаются один раз."""
    key = cache.make_key(
        "report",
        str(user.id),
        sorted(principal.roles),
        access.effective_scope(principal, user).value,
        request.model_dump(mode="json"),
    )
    return await cache.cached(
        session, key, lambda: _build_report(session, request, principal, user)
    )


async def _build_report(
    session: AsyncSession,
    request: ReportRequest,
    principal: Principal,
    user: User,
) -> ReportResponse:
    interactions = await fetch_interactions(session, request.filters, principal, user)
    rows = build_rows(interactions, request.filters)
    unsigned = await count_unsigned_excluded(session, request.filters, principal, user)
    return ReportResponse(
        title=request.title,
        generated_at=datetime.now(UTC),
        filters=request.filters,
        columns=request.columns,
        column_titles={column.value: COLUMN_TITLES[column] for column in request.columns},
        totals=build_totals(rows, unsigned),
        rows=rows,
        charts=build_charts(rows),
    )


def row_value(row: ReportRow, column: str) -> object:
    """Значение строки для выгрузки: даты и статусы уже в читаемом виде."""
    mapping: dict[str, object] = {
        "university": row.university,
        "direction": row.direction,
        "program": row.program,
        "product": row.product,
        "status": row.status_label,
        "manager": row.manager,
        "interaction": row.interaction,
        "stage": row.stage,
        "days_on_stage": row.days_on_stage,
        "outcome": row.outcome_label,
        "closure_reason": row.closure_reason_label,
        "source": row.source_label,
        "implementation_status": row.implementation_status_label,
        "contract_number": row.contract_number,
        "contract_status": row.contract_status_label,
        "signed_at": row.signed_at,
        "valid_to": row.valid_to,
        "created_at": row.created_at,
        "closed_at": row.closed_at,
        "comment": row.comment,
    }
    return mapping.get(column, "")


def format_period(filters: ReportFilters) -> str:
    def fmt(value: date | None) -> str:
        return value.strftime("%d.%m.%Y") if value else "…"

    if filters.date_from is None and filters.date_to is None:
        return "за всё время"
    basis = {
        PeriodBasis.CREATED: "по дате начала взаимодействия",
        PeriodBasis.ACTIVITY: "по движениям процесса",
        PeriodBasis.SIGNED: "по дате подписания договора",
        PeriodBasis.CLOSED: "по дате закрытия",
    }[filters.period_basis]
    return f"с {fmt(filters.date_from)} по {fmt(filters.date_to)} ({basis})"
