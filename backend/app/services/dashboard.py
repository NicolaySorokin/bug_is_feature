"""Главная страница.

Раздел 2.1 концепции: у каждой роли свой взгляд на одни и те же данные.
Менеджер видит свои договоры, ближайшие действия и последние изменения,
руководитель - картину по команде и нагрузку менеджеров, администратор -
вдобавок состояние интеграций, импортов, пользователей и настроек.

Выборка берётся ровно та же, что у отчётов, поэтому числа на главной
и в отчёте за тот же период совпадают. Результат кэшируется
(см. app.services.cache): главная - самая посещаемая страница.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import Principal
from app.enums import ContractStatus, Role, WorkflowEventType, WorkflowInstanceStatus
from app.models.contract import Contract
from app.models.importing import ImportRun
from app.models.integration import IntegrationRun, IntegrationSource
from app.models.user import User
from app.models.workflow import WorkflowEvent, WorkflowInstance, WorkflowTransition
from app.schemas.dashboard import (
    AdminSummary,
    AlertRead,
    DashboardCounters,
    DashboardResponse,
    ImportSummary,
    IntegrationStatus,
    ManagerLoad,
    NextAction,
    RecentChange,
)
from app.schemas.report import ReportFilters
from app.services import access, alerts, app_settings, cache, reports
from app.services.labels import (
    ALERT_KIND_LABELS,
    ALERT_SEVERITY_LABELS,
    EVENT_TYPE_LABELS,
    label,
)

RECENT_LIMIT = 15
ALERTS_LIMIT = 20
NEXT_ACTIONS_LIMIT = 8


def _role(principal: Principal) -> str:
    if principal.has_role(Role.ADMIN):
        return Role.ADMIN
    if principal.has_role(Role.HEAD):
        return Role.HEAD
    return Role.MANAGER


def to_alert_read(alert: alerts.Alert) -> AlertRead:
    return AlertRead(
        kind=alert.kind,
        kind_label=label(ALERT_KIND_LABELS, alert.kind),
        severity=alert.severity,
        severity_label=label(ALERT_SEVERITY_LABELS, alert.severity),
        message=alert.message,
        contract_id=alert.contract_id,
        contract_number=alert.contract_number,
        university_name=alert.university_name,
        manager_id=alert.manager_id,
        manager_name=alert.manager_name,
        days=alert.days,
    )


def _counters(contracts: list[Contract], user: User, problem_count: int) -> DashboardCounters:
    instances = [reports.active_instance(contract) for contract in contracts]
    statuses = Counter(instance.status for instance in instances if instance is not None)
    contract_statuses = Counter(contract.status for contract in contracts)

    return DashboardCounters(
        contracts=len(contracts),
        contracts_active=contract_statuses.get(ContractStatus.ACTIVE, 0),
        contracts_draft=contract_statuses.get(ContractStatus.DRAFT, 0),
        universities=len({contract.university_id for contract in contracts}),
        my_contracts=sum(1 for c in contracts if c.manager_id == user.id),
        processes_in_progress=statuses.get(WorkflowInstanceStatus.IN_PROGRESS, 0),
        processes_blocked=statuses.get(WorkflowInstanceStatus.BLOCKED, 0),
        processes_completed=statuses.get(WorkflowInstanceStatus.COMPLETED, 0),
        alerts=problem_count,
    )


async def _recent(
    session: AsyncSession, principal: Principal, user: User
) -> list[RecentChange]:
    """Последние движения по процессам, видимым пользователю."""
    statement = (
        select(WorkflowEvent)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowEvent.workflow_instance_id)
        .join(Contract, Contract.id == WorkflowInstance.contract_id)
        .options(
            selectinload(WorkflowEvent.user),
            selectinload(WorkflowEvent.to_stage),
            selectinload(WorkflowEvent.instance)
            .selectinload(WorkflowInstance.contract)
            .selectinload(Contract.university),
        )
        .order_by(WorkflowEvent.created_at.desc())
        .limit(RECENT_LIMIT)
    )
    statement = access.apply_contract_scope(statement, principal, user)

    changes: list[RecentChange] = []
    for event in (await session.execute(statement)).scalars():
        contract = event.instance.contract
        changes.append(
            RecentChange(
                contract_id=contract.id,
                contract_number=contract.number,
                university_name=contract.university.name if contract.university else "",
                event_type=WorkflowEventType(event.event_type),
                event_type_label=label(EVENT_TYPE_LABELS, WorkflowEventType(event.event_type)),
                stage=event.to_stage.name if event.to_stage else "",
                user_name=event.user.full_name if event.user else "",
                comment=event.comment,
                created_at=event.created_at,
            )
        )
    return changes


def _manager_load(contracts: list[Contract], found: list[alerts.Alert]) -> list[ManagerLoad]:
    """Нагрузка менеджеров: сколько договоров, сколько в работе и сколько проблемных."""
    problems: Counter[uuid.UUID | None] = Counter()
    seen: set[tuple[uuid.UUID | None, uuid.UUID]] = set()
    for alert in found:
        # Договор с тремя тревогами - это одна проблема менеджера, а не три.
        if alert.contract_id is not None and (alert.manager_id, alert.contract_id) not in seen:
            seen.add((alert.manager_id, alert.contract_id))
            problems[alert.manager_id] += 1

    names: dict[uuid.UUID | None, str] = {}
    total: Counter[uuid.UUID | None] = Counter()
    active: Counter[uuid.UUID | None] = Counter()
    blocked: Counter[uuid.UUID | None] = Counter()
    for contract in contracts:
        manager_id = contract.manager_id
        names[manager_id] = (
            contract.manager.full_name if contract.manager else "Без ответственного"
        )
        total[manager_id] += 1
        instance = reports.active_instance(contract)
        if instance is not None and instance.status == WorkflowInstanceStatus.IN_PROGRESS:
            active[manager_id] += 1
        if instance is not None and instance.status == WorkflowInstanceStatus.BLOCKED:
            blocked[manager_id] += 1

    load = [
        ManagerLoad(
            manager_id=manager_id,
            manager_name=names[manager_id],
            contracts=count,
            problems=problems.get(manager_id, 0),
            active=active.get(manager_id, 0),
            blocked=blocked.get(manager_id, 0),
        )
        for manager_id, count in total.items()
    ]
    load.sort(key=lambda item: (-item.problems, -item.contracts, item.manager_name))
    return load


async def _next_actions(
    session: AsyncSession, contracts: list[Contract], user: User, default_sla: int
) -> list[NextAction]:
    """Свои договоры с идущим процессом: где пора действовать, первыми."""
    candidates: list[tuple[Contract, WorkflowInstance]] = []
    for contract in contracts:
        if contract.manager_id != user.id:
            continue
        instance = reports.active_instance(contract)
        if instance is None or instance.status not in {
            WorkflowInstanceStatus.IN_PROGRESS,
            WorkflowInstanceStatus.BLOCKED,
        }:
            continue
        candidates.append((contract, instance))
    if not candidates:
        return []

    stage_ids = {instance.current_stage_id for _, instance in candidates}
    transitions: dict[uuid.UUID, list[str]] = {}
    rows = await session.execute(
        select(WorkflowTransition)
        .where(WorkflowTransition.from_stage_id.in_(stage_ids))
        .options(selectinload(WorkflowTransition.to_stage))
    )
    for transition in rows.scalars():
        transitions.setdefault(transition.from_stage_id, []).append(
            transition.name or transition.to_stage.name
        )

    now = datetime.now(UTC)
    actions: list[NextAction] = []
    for contract, instance in candidates:
        stage = instance.current_stage
        days = (
            (now - instance.current_stage_started_at).days
            if instance.current_stage_started_at
            else None
        )
        sla = stage.sla_days if stage and stage.sla_days else default_sla
        actions.append(
            NextAction(
                contract_id=contract.id,
                contract_number=contract.number,
                university_name=contract.university.name if contract.university else "",
                stage_name=stage.name if stage else "",
                process_status=instance.status,
                days_on_stage=days,
                sla_days=sla,
                overdue=days is not None and days > sla,
                actions=transitions.get(instance.current_stage_id, []),
            )
        )
    # Сначала заблокированные, потом по доле израсходованного срока этапа.
    actions.sort(
        key=lambda item: (
            item.process_status != WorkflowInstanceStatus.BLOCKED,
            -((item.days_on_stage or 0) / max(item.sla_days or 1, 1)),
        )
    )
    return actions[:NEXT_ACTIONS_LIMIT]


async def _admin_summary(session: AsyncSession) -> AdminSummary:
    users = list((await session.execute(select(User))).scalars())
    recently = datetime.now(UTC) - timedelta(days=7)
    by_role: Counter[str] = Counter()
    for item in users:
        by_role.update(item.roles or [])

    last_run = (
        select(IntegrationRun.source_id, func.max(IntegrationRun.started_at).label("started"))
        .group_by(IntegrationRun.source_id)
        .subquery()
    )
    runs = await session.execute(
        select(IntegrationSource, IntegrationRun)
        .outerjoin(last_run, last_run.c.source_id == IntegrationSource.id)
        .outerjoin(
            IntegrationRun,
            (IntegrationRun.source_id == IntegrationSource.id)
            & (IntegrationRun.started_at == last_run.c.started),
        )
        .order_by(IntegrationSource.code)
    )
    integrations = [
        IntegrationStatus(
            code=source.code,
            name=source.name,
            is_enabled=source.is_enabled,
            uses_fixture=not source.base_url,
            last_status=run.status if run else None,
            last_started_at=run.started_at if run else None,
            last_error=run.error_message if run else None,
        )
        for source, run in runs.all()
    ]
    imports = await session.execute(
        select(ImportRun).order_by(ImportRun.created_at.desc()).limit(5)
    )
    return AdminSummary(
        users_total=len(users),
        users_active=sum(1 for item in users if item.is_active),
        users_seen_recently=sum(
            1 for item in users if item.last_seen_at and item.last_seen_at >= recently
        ),
        users_by_role=dict(by_role),
        integrations=integrations,
        imports=[
            ImportSummary(
                id=run.id,
                filename=run.filename,
                import_type=run.import_type,
                status=run.status,
                rows_created=run.rows_created,
                rows_updated=run.rows_updated,
                rows_failed=run.rows_failed,
                created_at=run.created_at,
            )
            for run in imports.scalars()
        ],
        settings=await app_settings.load(session),
    )


async def _build(session: AsyncSession, principal: Principal, user: User) -> DashboardResponse:
    contracts = await reports.fetch_contracts(session, ReportFilters(), principal, user)
    rows = reports.build_rows(contracts)
    found = await alerts.collect_all(session, principal, user)
    norms = await alerts.load_norms(session)
    role = _role(principal)

    return DashboardResponse(
        role=role,
        generated_at=datetime.now(UTC),
        counters=_counters(contracts, user, len(found)),
        alerts_summary=alerts.summarize(found),
        alerts=[to_alert_read(alert) for alert in found[:ALERTS_LIMIT]],
        recent=await _recent(session, principal, user),
        charts=reports.build_charts(contracts, rows),
        next_actions=await _next_actions(session, contracts, user, norms.default_sla_days),
        manager_load=(
            _manager_load(contracts, found) if role in {Role.HEAD, Role.ADMIN} else []
        ),
        admin=await _admin_summary(session) if role == Role.ADMIN else None,
    )


async def build(session: AsyncSession, principal: Principal, user: User) -> DashboardResponse:
    key = cache.make_key("dashboard", str(user.id), sorted(principal.roles), user.data_scope)
    return await cache.cached(session, key, lambda: _build(session, principal, user))
