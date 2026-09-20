"""Сбор данных для отчётов и диаграмм.

Порядок работы такой: один запрос отбирает договоры по фильтрам, дальше
из них разворачиваются строки отчёта, а диаграммы считаются уже по этим
строкам. Благодаря этому табличная часть и диаграммы всегда описывают
одну и ту же выборку (раздел 6.1 концепции) - расхождений между цифрами
в таблице и картинкой быть не может.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, date, datetime

from sqlalchemy import Date, Select, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import Principal
from app.enums import ContractStatus, WorkflowInstanceStatus
from app.models.catalog import ItProgram
from app.models.contract import Contract, ContractProduct, ContractProgram
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
from app.services import access
from app.services.labels import (
    CONTRACT_STATUS_LABELS,
    IMPLEMENTATION_STATUS_LABELS,
    label,
)

# Сколько позиций показывать на диаграммах со списком названий.
TOP_LIMIT = 10
NO_VALUE = "Не указано"
NO_PROCESS = "Процесс не запущен"


def _apply_filters(statement: Select, filters: ReportFilters) -> Select:
    if filters.university_ids:
        statement = statement.where(Contract.university_id.in_(filters.university_ids))
    if filters.manager_ids:
        statement = statement.where(Contract.manager_id.in_(filters.manager_ids))
    if filters.statuses:
        statement = statement.where(Contract.status.in_(filters.statuses))

    if filters.program_ids:
        statement = statement.where(
            Contract.id.in_(
                select(ContractProgram.contract_id).where(
                    ContractProgram.program_id.in_(filters.program_ids)
                )
            )
        )
    if filters.direction_ids:
        statement = statement.where(
            Contract.id.in_(
                select(ContractProgram.contract_id)
                .join(ItProgram, ItProgram.id == ContractProgram.program_id)
                .where(ItProgram.direction_id.in_(filters.direction_ids))
            )
        )
    if filters.product_ids:
        statement = statement.where(
            Contract.id.in_(
                select(ContractProduct.contract_id).where(
                    ContractProduct.product_id.in_(filters.product_ids)
                )
            )
        )
    if filters.stage_ids:
        statement = statement.where(
            Contract.id.in_(
                select(WorkflowInstance.contract_id).where(
                    WorkflowInstance.current_stage_id.in_(filters.stage_ids)
                )
            )
        )

    return _apply_period(statement, filters)


def _apply_period(statement: Select, filters: ReportFilters) -> Select:
    """Период применяется к разной дате в зависимости от основания выборки."""
    if filters.date_from is None and filters.date_to is None:
        return statement

    if filters.period_basis is PeriodBasis.ACTIVITY:
        # Договоры, по которым внутри периода были движения по процессу.
        activity = (
            select(WorkflowInstance.contract_id)
            .join(WorkflowEvent, WorkflowEvent.workflow_instance_id == WorkflowInstance.id)
            .where(*_between(cast(WorkflowEvent.created_at, Date), filters))
        )
        return statement.where(Contract.id.in_(activity))

    if filters.period_basis is PeriodBasis.CREATED:
        column = cast(Contract.created_at, Date)
    else:
        # Договор без даты подписания (черновик) попадает в период по дате
        # заведения - иначе он выпал бы из отчёта совсем.
        column = func.coalesce(Contract.signed_at, cast(Contract.created_at, Date))

    return statement.where(*_between(column, filters))


def _between(column, filters: ReportFilters) -> list:
    conditions = []
    if filters.date_from is not None:
        conditions.append(column >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(column <= filters.date_to)
    return conditions


async def fetch_contracts(
    session: AsyncSession,
    filters: ReportFilters,
    principal: Principal,
    user: User,
) -> list[Contract]:
    """Договоры выборки со всем, что нужно строкам отчёта."""
    statement = (
        select(Contract)
        .options(
            selectinload(Contract.university),
            selectinload(Contract.manager),
            selectinload(Contract.programs)
            .selectinload(ContractProgram.program)
            .selectinload(ItProgram.direction),
            selectinload(Contract.products).selectinload(ContractProduct.product),
            selectinload(Contract.workflow_instances).selectinload(
                WorkflowInstance.current_stage
            ),
        )
        .order_by(Contract.created_at.desc())
    )
    statement = _apply_filters(statement, filters)
    statement = access.apply_contract_scope(statement, principal, user)
    result = await session.execute(statement)
    return list(result.scalars().unique())


def active_instance(contract: Contract) -> WorkflowInstance | None:
    """Текущий процесс договора: в первой версии он один."""
    instances = sorted(
        contract.workflow_instances,
        key=lambda item: item.started_at or datetime.min.replace(tzinfo=UTC),
    )
    return instances[-1] if instances else None


def _days_on_stage(instance: WorkflowInstance | None) -> int | None:
    if instance is None or instance.current_stage_started_at is None:
        return None
    return (datetime.now(UTC) - instance.current_stage_started_at).days


def _stage_title(instance: WorkflowInstance | None) -> str:
    if instance is None:
        return NO_PROCESS
    if instance.status == WorkflowInstanceStatus.COMPLETED:
        return "Процесс завершён"
    if instance.current_stage is None:
        return NO_PROCESS
    name = instance.current_stage.name
    if instance.status == WorkflowInstanceStatus.BLOCKED:
        return f"{name} (заблокирован)"
    return name


def build_rows(contracts: list[Contract]) -> list[ReportRow]:
    """Разворачивает договоры в строки «договор - ИТ-программа»."""
    rows: list[ReportRow] = []
    for contract in contracts:
        instance = active_instance(contract)
        products = ", ".join(
            sorted(link.product.name for link in contract.products if link.product)
        )
        base = {
            "contract_id": contract.id,
            "university_id": contract.university_id,
            "university": contract.university.name if contract.university else NO_VALUE,
            "product": products,
            "contract_number": contract.number,
            "contract_status": ContractStatus(contract.status),
            "contract_status_label": label(
                CONTRACT_STATUS_LABELS, ContractStatus(contract.status)
            ),
            "stage": _stage_title(instance),
            "days_on_stage": _days_on_stage(instance),
            "manager": contract.manager.full_name if contract.manager else NO_VALUE,
            "signed_at": contract.signed_at,
            "valid_to": contract.valid_to,
            "comment": contract.comment or "",
        }

        if not contract.programs:
            # Договор без программ тоже взаимодействие - строка остаётся.
            rows.append(ReportRow(**base))
            continue

        for link in contract.programs:
            program = link.program
            direction = program.direction if program else None
            rows.append(
                ReportRow(
                    **base,
                    direction=direction.name if direction else NO_VALUE,
                    program=program.name if program else NO_VALUE,
                    implementation_status=link.implementation_status,
                    implementation_status_label=label(
                        IMPLEMENTATION_STATUS_LABELS, link.implementation_status
                    ),
                )
            )
    return rows


def _top(counter: Counter[str], limit: int = TOP_LIMIT) -> list[ChartItem]:
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


def build_charts(contracts: list[Contract], rows: list[ReportRow]) -> list[ChartData]:
    """Диаграммы по той же выборке, что и таблица."""
    seen: set[uuid.UUID] = set()
    by_status: Counter[str] = Counter()
    by_stage: Counter[str] = Counter()
    by_university: Counter[str] = Counter()
    by_manager: Counter[str] = Counter()

    for row in rows:
        if row.contract_id in seen:
            continue
        seen.add(row.contract_id)
        by_status[row.contract_status_label] += 1
        by_stage[row.stage] += 1
        by_university[row.university] += 1
        by_manager[row.manager] += 1

    # Направления считаем по строкам состава: одна программа - одна строка.
    by_direction = Counter(row.direction for row in rows if row.direction)

    return [
        ChartData(
            key=ChartKey.BY_STATUS,
            title="Договоры по статусам",
            measure="договоров",
            items=[ChartItem(label=name, value=value) for name, value in by_status.items()],
        ),
        ChartData(
            key=ChartKey.BY_STAGE,
            title="Договоры по этапам процесса",
            measure="договоров",
            items=_top(by_stage),
        ),
        ChartData(
            key=ChartKey.BY_DIRECTION,
            title="Программы по ИТ-направлениям",
            measure="программ в договорах",
            items=_top(by_direction),
        ),
        ChartData(
            key=ChartKey.BY_UNIVERSITY,
            title="Договоры по вузам",
            measure="договоров",
            items=_top(by_university),
        ),
        ChartData(
            key=ChartKey.BY_MANAGER,
            title="Нагрузка ответственных",
            measure="договоров",
            items=_top(by_manager),
        ),
    ]


def build_totals(rows: list[ReportRow]) -> ReportTotals:
    products: set[str] = set()
    for row in rows:
        products.update(part for part in row.product.split(", ") if part)
    return ReportTotals(
        rows=len(rows),
        contracts=len({row.contract_id for row in rows}),
        universities=len({row.university_id for row in rows}),
        programs=len({row.program for row in rows if row.program}),
        products=len(products),
    )


async def build_report(
    session: AsyncSession,
    request: ReportRequest,
    principal: Principal,
    user: User,
) -> ReportResponse:
    contracts = await fetch_contracts(session, request.filters, principal, user)
    rows = build_rows(contracts)
    return ReportResponse(
        title=request.title,
        generated_at=datetime.now(UTC),
        filters=request.filters,
        columns=request.columns,
        column_titles={column.value: COLUMN_TITLES[column] for column in request.columns},
        totals=build_totals(rows),
        rows=rows,
        charts=build_charts(contracts, rows),
    )


def row_value(row: ReportRow, column: str) -> object:
    """Значение строки для выгрузки: даты и статусы уже в читаемом виде."""
    mapping: dict[str, object] = {
        "university": row.university,
        "direction": row.direction,
        "program": row.program,
        "product": row.product,
        "contract_number": row.contract_number,
        "contract_status": row.contract_status_label,
        "stage": row.stage,
        "days_on_stage": row.days_on_stage,
        "manager": row.manager,
        "implementation_status": row.implementation_status_label,
        "signed_at": row.signed_at,
        "valid_to": row.valid_to,
        "comment": row.comment,
    }
    return mapping.get(column, "")


def format_period(filters: ReportFilters) -> str:
    def fmt(value: date | None) -> str:
        return value.strftime("%d.%m.%Y") if value else "…"

    if filters.date_from is None and filters.date_to is None:
        return "за всё время"
    return f"с {fmt(filters.date_from)} по {fmt(filters.date_to)}"
