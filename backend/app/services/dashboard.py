"""Главная страница.

Раздел 2.1 концепции: у каждой роли свой взгляд на одни и те же данные.
Менеджер видит свои договоры и ближайшие действия, руководитель - картину
по команде, администратор - вдобавок состояние обменов и загрузок.

Выборка берётся ровно та же, что у отчётов, поэтому числа на главной
и в отчёте за тот же период совпадают.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import Principal
from app.enums import ContractStatus, Role, WorkflowEventType, WorkflowInstanceStatus
from app.models.contract import Contract
from app.models.user import User
from app.models.workflow import WorkflowEvent, WorkflowInstance
from app.schemas.dashboard import (
    AlertRead,
    DashboardCounters,
    DashboardResponse,
    ManagerLoad,
    RecentChange,
)
from app.schemas.report import ReportFilters
from app.services import access, alerts, reports
from app.services.labels import (
    ALERT_KIND_LABELS,
    ALERT_SEVERITY_LABELS,
    EVENT_TYPE_LABELS,
    label,
)

RECENT_LIMIT = 15
ALERTS_LIMIT = 20


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


def _counters(
    contracts: list[Contract], user: User, problem_count: int
) -> DashboardCounters:
    instances = [reports.active_instance(contract) for contract in contracts]
    statuses = Counter(
        instance.status for instance in instances if instance is not None
    )
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
                event_type_label=label(
                    EVENT_TYPE_LABELS, WorkflowEventType(event.event_type)
                ),
                stage=event.to_stage.name if event.to_stage else "",
                user_name=event.user.full_name if event.user else "",
                comment=event.comment,
                created_at=event.created_at,
            )
        )
    return changes


def _manager_load(
    contracts: list[Contract], found: list[alerts.Alert]
) -> list[ManagerLoad]:
    """Нагрузка менеджеров: сколько договоров и сколько из них проблемных."""
    problems = Counter(
        alert.manager_id for alert in found if alert.contract_id is not None
    )
    by_manager: dict[tuple, int] = Counter(
        (
            contract.manager_id,
            contract.manager.full_name if contract.manager else "Без ответственного",
        )
        for contract in contracts
    )
    load = [
        ManagerLoad(
            manager_id=manager_id,
            manager_name=manager_name,
            contracts=count,
            problems=problems.get(manager_id, 0),
        )
        for (manager_id, manager_name), count in by_manager.items()
    ]
    load.sort(key=lambda item: (-item.problems, -item.contracts))
    return load


async def build(
    session: AsyncSession, principal: Principal, user: User
) -> DashboardResponse:
    contracts = await reports.fetch_contracts(session, ReportFilters(), principal, user)
    rows = reports.build_rows(contracts)
    found = await alerts.collect(session, principal, user, limit=ALERTS_LIMIT)
    role = _role(principal)

    return DashboardResponse(
        role=role,
        generated_at=datetime.now(UTC),
        counters=_counters(contracts, user, len(found)),
        alerts_summary=alerts.summarize(found),
        alerts=[to_alert_read(alert) for alert in found],
        recent=await _recent(session, principal, user),
        charts=reports.build_charts(contracts, rows),
        manager_load=(
            _manager_load(contracts, found) if role in {Role.HEAD, Role.ADMIN} else []
        ),
    )
