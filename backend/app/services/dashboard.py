"""Главная страница: у каждой роли свой взгляд на одни данные.

Выборка та же, что у отчётов, поэтому числа совпадают. Результат кэшируется.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import Principal
from app.enums import (
    AlertKind,
    DataScope,
    InteractionOutcome,
    InteractionStatus,
    MappingStatus,
    Role,
    UniversityStatus,
    WorkflowEventType,
)
from app.models.access import UserUniversityAccess
from app.models.importing import ImportRun
from app.models.integration import IntegrationMapping, IntegrationRun, IntegrationSource
from app.models.university import University
from app.models.user import User
from app.models.workflow import WorkflowEvent, WorkflowInstance
from app.schemas.dashboard import (
    AdminSummary,
    AlertRead,
    ControlItem,
    DashboardCounters,
    DashboardResponse,
    ImportSummary,
    IntegrationStatus,
    ManagerLoad,
    NextStep,
    RecentChange,
)
from app.schemas.interaction import SlaState
from app.schemas.report import ReportFilters
from app.schemas.university import UniversityBrief
from app.schemas.user import UserBrief
from app.services import (
    access,
    alert_marks,
    alerts,
    app_settings,
    cache,
    interactions,
    reports,
)
from app.services.access import Action
from app.services.labels import (
    ALERT_KIND_LABELS,
    ALERT_SEVERITY_LABELS,
    EVENT_TYPE_LABELS,
    label,
)

RECENT_LIMIT = 15
ALERTS_LIMIT = 20
STEPS_LIMIT = 10
QUEUE_LIMIT = 15

SCOPE_LABELS = {
    DataScope.OWN: "по вашим взаимодействиям",
    DataScope.TEAM: "по данным команды",
    DataScope.ALL: "по всем взаимодействиям",
    DataScope.NONE: "бизнес-данные недоступны",
}

CONTROL_REASONS = {
    "unassigned": "Без ответственного",
    "blocked": "Заблокировано",
    "overdue": "Просрочен срок этапа",
    "draft": "Процесс не запущен",
}

OPEN = (InteractionStatus.DRAFT, InteractionStatus.IN_PROGRESS, InteractionStatus.BLOCKED)


def _role(principal: Principal) -> str:
    """Главная роль, от неё зависит вид главной."""
    if principal.has_role(Role.HEAD):
        return Role.HEAD
    if principal.has_role(Role.MANAGER):
        return Role.MANAGER
    return Role.ADMIN


def to_alert_read(alert: alerts.Alert, read: set[str] | None = None) -> AlertRead:
    return AlertRead(
        kind=alert.kind,
        kind_label=label(ALERT_KIND_LABELS, alert.kind),
        severity=alert.severity,
        severity_label=label(ALERT_SEVERITY_LABELS, alert.severity),
        message=alert.message,
        interaction_id=alert.interaction_id,
        interaction_title=alert.interaction_title,
        contract_number=alert.contract_number,
        university_name=alert.university_name,
        university_full_name=alert.university_full_name,
        manager_id=alert.manager_id,
        manager_name=alert.manager_name,
        days=alert.days,
        link=alert.link,
        key=alert.key,
        is_read=alert.key in (read or set()),
    )


def _step(
    instance: WorkflowInstance, actions: dict[uuid.UUID, list[str]], default_sla: int
) -> NextStep:
    summary = interactions.stage_summary(instance, actions, default_sla)
    return NextStep(
        interaction_id=instance.id,
        title=instance.title,
        university=UniversityBrief.of(instance.university),
        manager=UserBrief.model_validate(instance.manager) if instance.manager else None,
        status=instance.status,
        blocked_reason=instance.blocked_reason,
        stage_name=summary.stage_name if summary else "",
        next_actions=summary.next_actions if summary else [],
        sla=summary.sla if summary else None,
        contract=interactions.contract_brief(instance.contract),
    )


_SLA_ORDER = {SlaState.OVERDUE: 0, SlaState.WARNING: 1, SlaState.OK: 2}


def _step_order(step: NextStep) -> tuple:
    """Сначала заблокированные, затем просроченные, близкие к сроку и остальные."""
    blocked = step.status == InteractionStatus.BLOCKED
    sla_rank = _SLA_ORDER[step.sla.state] if step.sla else 3
    used = step.sla.used_percent if step.sla else 0
    return (not blocked, sla_rank, -used)


def _counters(
    items: list[WorkflowInstance], user: User, found: list[alerts.Alert], default_sla: int
) -> DashboardCounters:
    counters = DashboardCounters(alerts=len(found))
    statuses = Counter(instance.status for instance in items)
    outcomes = Counter(instance.outcome for instance in items if instance.outcome)
    counters.drafts = statuses.get(InteractionStatus.DRAFT, 0)
    counters.in_progress = statuses.get(InteractionStatus.IN_PROGRESS, 0)
    counters.blocked = statuses.get(InteractionStatus.BLOCKED, 0)
    counters.completed = statuses.get(InteractionStatus.COMPLETED, 0)
    counters.cancelled = statuses.get(InteractionStatus.CANCELLED, 0)
    counters.open = counters.drafts + counters.in_progress + counters.blocked
    counters.successful = outcomes.get(InteractionOutcome.SUCCESSFUL, 0)
    counters.partial = outcomes.get(InteractionOutcome.PARTIAL, 0)
    counters.unsuccessful = outcomes.get(InteractionOutcome.UNSUCCESSFUL, 0)
    counters.universities = len({instance.university_id for instance in items})
    for instance in items:
        if instance.status not in OPEN:
            continue
        if instance.manager_id is None:
            counters.unassigned += 1
        if instance.manager_id == user.id:
            counters.mine_open += 1
        if instance.status == InteractionStatus.IN_PROGRESS and instance.current_stage:
            sla = interactions.stage_sla(
                instance.current_stage_started_at, instance.current_stage.sla_days, default_sla
            )
            if sla and sla.state == SlaState.OVERDUE:
                counters.overdue += 1
            elif sla and sla.state == SlaState.WARNING:
                counters.near_deadline += 1
    return counters


async def _recent(
    session: AsyncSession, principal: Principal, user: User
) -> list[RecentChange]:
    """Последние движения по взаимодействиям, видимым пользователю."""
    statement = (
        select(WorkflowEvent)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowEvent.workflow_instance_id)
        .options(
            selectinload(WorkflowEvent.user),
            selectinload(WorkflowEvent.to_stage),
            selectinload(WorkflowEvent.instance).selectinload(WorkflowInstance.university),
        )
        .order_by(WorkflowEvent.created_at.desc())
        .limit(RECENT_LIMIT)
    )
    statement = access.apply_interaction_scope(statement, principal, user)
    changes: list[RecentChange] = []
    for event in (await session.execute(statement)).scalars():
        instance = event.instance
        changes.append(
            RecentChange(
                interaction_id=instance.id,
                title=instance.title,
                university=UniversityBrief.of(instance.university),
                event_type=WorkflowEventType(event.event_type),
                event_type_label=label(EVENT_TYPE_LABELS, WorkflowEventType(event.event_type)),
                stage=event.to_stage.name if event.to_stage else "",
                user_name=event.user.full_name if event.user else "Система",
                comment=event.comment,
                created_at=event.created_at,
            )
        )
    return changes


def _team_load(
    items: list[WorkflowInstance], found: list[alerts.Alert], default_sla: int
) -> list[ManagerLoad]:
    """Нагрузка менеджеров: активные взаимодействия, просрочки, блокировки, проблемы."""
    problems: Counter[uuid.UUID | None] = Counter()
    seen: set[tuple[uuid.UUID | None, uuid.UUID]] = set()
    for alert in found:
        # Три тревоги по одному взаимодействию считаем одной проблемой менеджера.
        if (
            alert.interaction_id is not None
            and (alert.manager_id, alert.interaction_id) not in seen
        ):
            seen.add((alert.manager_id, alert.interaction_id))
            problems[alert.manager_id] += 1

    load: dict[uuid.UUID | None, ManagerLoad] = {}
    for instance in items:
        if instance.status not in OPEN:
            continue
        key = instance.manager_id
        row = load.setdefault(
            key,
            ManagerLoad(
                manager_id=key,
                manager_name=instance.manager.full_name
                if instance.manager
                else "Без ответственного",
            ),
        )
        row.open += 1
        if instance.status == InteractionStatus.IN_PROGRESS:
            row.in_progress += 1
            if instance.current_stage is not None:
                sla = interactions.stage_sla(
                    instance.current_stage_started_at,
                    instance.current_stage.sla_days,
                    default_sla,
                )
                if sla and sla.state == SlaState.OVERDUE:
                    row.overdue += 1
        if instance.status == InteractionStatus.BLOCKED:
            row.blocked += 1
    for key, row in load.items():
        row.problems = problems.get(key, 0)
    result = list(load.values())
    result.sort(
        key=lambda item: (
            -item.problems,
            -item.blocked,
            -item.overdue,
            -item.open,
            item.manager_name,
        )
    )
    return result


def _control_queue(
    items: list[WorkflowInstance], actions: dict[uuid.UUID, list[str]], default_sla: int
) -> list[ControlItem]:
    """Что требует решения руководителя: без ответственного, блокировки, просрочки."""
    queue: list[ControlItem] = []
    for instance in items:
        if instance.status not in OPEN:
            continue
        step = _step(instance, actions, default_sla)
        reason = None
        if instance.manager_id is None:
            reason = "unassigned"
        elif instance.status == InteractionStatus.BLOCKED:
            reason = "blocked"
        elif step.sla is not None and step.sla.state == SlaState.OVERDUE:
            reason = "overdue"
        if reason is None:
            continue
        queue.append(
            ControlItem(
                **step.model_dump(), reason=reason, reason_label=CONTROL_REASONS[reason]
            )
        )
    rank = {"blocked": 0, "unassigned": 1, "overdue": 2}
    queue.sort(key=lambda item: (rank[item.reason], *_step_order(item)))
    return queue[:QUEUE_LIMIT]


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
    integrations_status = [
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
    # Три последние загрузки, вся история на странице «Загрузка из Excel».
    imports = await session.execute(
        select(ImportRun).order_by(ImportRun.created_at.desc()).limit(3)
    )
    now = datetime.now(UTC)
    temporary = sum(
        1
        for item in users
        if item.data_scope_expires_at is not None and item.data_scope_expires_at > now
    )
    temporary += (
        await session.scalar(
            select(func.count())
            .select_from(UserUniversityAccess)
            .where(
                UserUniversityAccess.revoked_at.is_(None),
                UserUniversityAccess.expires_at.is_not(None),
                UserUniversityAccess.expires_at > now,
            )
        )
        or 0
    )
    return AdminSummary(
        users_total=len(users),
        users_active=sum(1 for item in users if item.is_active),
        users_seen_recently=sum(
            1 for item in users if item.last_seen_at and item.last_seen_at >= recently
        ),
        users_by_role=dict(by_role),
        integrations=integrations_status,
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
        mappings_pending=await session.scalar(
            select(func.count())
            .select_from(IntegrationMapping)
            .where(IntegrationMapping.status == MappingStatus.PENDING)
        )
        or 0,
        universities_pending=await session.scalar(
            select(func.count())
            .select_from(University)
            .where(University.status == UniversityStatus.PENDING)
        )
        or 0,
        temporary_access=temporary,
    )


# Строка шага или очереди сама показывает блокировку, просрочку и отсутствие
# ответственного, поэтому в «Требует внимания» такие поводы не повторяются.
# Но только если взаимодействие на главной есть: вуз коллеги, открытый на время
# замещения, в свои шаги не попадает, и его поводы остаются здесь.
SHOWN_IN_STEPS = {
    AlertKind.PROCESS_BLOCKED,
    AlertKind.STAGE_STALE,
    AlertKind.NO_MANAGER,
}


async def _build(session: AsyncSession, principal: Principal, user: User) -> DashboardResponse:
    scope = access.effective_scope(principal, user)
    role = _role(principal)
    items = await reports.fetch_interactions(session, ReportFilters(), principal, user)
    found = await alerts.collect_all(session, principal, user)
    norms = await alerts.load_norms(session)
    default_sla = norms.default_sla_days
    actions = await interactions.transitions_by_stage(
        session,
        {
            instance.current_stage_id
            for instance in items
            if instance.current_stage_id and instance.status in OPEN
        },
    )

    head = access.can(principal, user, Action.ASSIGN_RESPONSIBLE)
    works = principal.has_role(Role.MANAGER)
    own = [
        instance
        for instance in items
        if instance.manager_id == user.id and instance.status in OPEN
    ]
    steps: list[NextStep] = []
    if works:
        steps = sorted(
            (_step(instance, actions, default_sla) for instance in own), key=_step_order
        )[:STEPS_LIMIT]
    queue = _control_queue(items, actions, default_sla) if head else []
    on_page = {item.interaction_id for item in (*steps, *queue)}
    attention = [
        alert
        for alert in found
        if alert.kind not in SHOWN_IN_STEPS or alert.interaction_id not in on_page
    ]

    rows = reports.build_rows(items)
    read = await alert_marks.read_keys(session, user, found)
    return DashboardResponse(
        role=role,
        scope=scope,
        scope_label=SCOPE_LABELS.get(scope, ""),
        generated_at=datetime.now(UTC),
        counters=_counters(items, user, found, default_sla),
        alerts_summary=alerts.summarize(found),
        alerts=[to_alert_read(alert, read) for alert in attention[:ALERTS_LIMIT]],
        alerts_in_steps=len(found) - len(attention),
        recent=await _recent(session, principal, user) if scope is not DataScope.NONE else [],
        charts=reports.build_charts(rows, with_managers=head) if items else [],
        next_steps=steps,
        control_queue=queue,
        team_load=_team_load(items, found, default_sla) if head else [],
        admin=await _admin_summary(session)
        if access.can(principal, user, Action.MANAGE_USERS)
        else None,
    )


async def build(session: AsyncSession, principal: Principal, user: User) -> DashboardResponse:
    key = cache.make_key(
        "dashboard",
        str(user.id),
        sorted(principal.roles),
        sorted(user.permissions or []),
        access.effective_scope(principal, user).value,
    )
    return await cache.cached(session, key, lambda: _build(session, principal, user))
