"""Контроль проблемных взаимодействий.

Каждое правило говорит, что не так, кто отвечает и сколько времени ситуация
не меняется. Правила работают по одной загруженной выборке. Технические
поводы видят только те, кто может их разобрать.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.enums import (
    AlertKind,
    AlertSeverity,
    ContractStatus,
    DocumentType,
    IntegrationRunStatus,
    InteractionStatus,
    LicenseStatus,
    MappingStatus,
    ProgramImplementationStatus,
    UniversityStatus,
)
from app.models.content import Attachment
from app.models.contract import License
from app.models.integration import IntegrationMapping, IntegrationRun, IntegrationSource
from app.models.interaction import InteractionProduct
from app.models.university import University
from app.models.user import User
from app.models.workflow import WorkflowInstance
from app.schemas.report import ReportFilters
from app.services import access, app_settings, cache, licenses, reports
from app.services.access import Action
from app.services.labels import DOCUMENT_TYPE_LABELS, label


@dataclass(frozen=True, slots=True)
class Norms:
    """Нормы контроля: задаются администратором в системных настройках."""

    default_sla_days: int
    expiring_days: int


@dataclass(slots=True)
class Alert:
    kind: AlertKind
    severity: AlertSeverity
    message: str
    interaction_id: uuid.UUID | None = None
    interaction_title: str = ""
    contract_number: str = ""
    university_name: str = ""
    university_full_name: str = ""
    manager_id: uuid.UUID | None = None
    manager_name: str = ""
    days: int | None = None  # сколько времени ситуация не меняется
    link: str | None = None
    # Что именно не так, если поводов одного вида несколько: этап, лицензия, запуск.
    subject: str = ""

    @property
    def key(self) -> str:
        """Ключ проблемы для отметки «прочитано».

        Текст в ключ не входит: «осталось 38 дней»
        меняется каждый день, а проблема та же.
        """
        return f"{self.kind.value}:{self.interaction_id or ''}:{self.subject}"


def _severity_by_days(days: int | None, limit: int) -> AlertSeverity:
    """Чем дольше висит ситуация, тем выше важность."""
    if days is None:
        return AlertSeverity.WARNING
    if days < 0 or days >= limit * 2:
        return AlertSeverity.CRITICAL
    return AlertSeverity.WARNING


def _base(instance: WorkflowInstance) -> dict:
    university = instance.university
    return {
        "interaction_id": instance.id,
        "interaction_title": instance.title or "",
        "contract_number": instance.contract.number if instance.contract else "",
        "university_name": (university.short_name or university.name) if university else "",
        "university_full_name": university.name if university else "",
        "manager_id": instance.manager_id,
        "manager_name": instance.manager.full_name if instance.manager else "",
    }


def _days_since(moment: datetime | None) -> int | None:
    return None if moment is None else (datetime.now(UTC) - moment).days


def _process_alerts(instance: WorkflowInstance, norms: Norms) -> list[Alert]:
    if instance.status == InteractionStatus.DRAFT:
        days = _days_since(instance.created_at)
        return [
            Alert(
                kind=AlertKind.PROCESS_NOT_STARTED,
                severity=AlertSeverity.INFO,
                message="Взаимодействие в черновике: процесс не запущен",
                days=days,
                **_base(instance),
            )
        ]

    if instance.status == InteractionStatus.BLOCKED:
        reason = f": {instance.blocked_reason}" if instance.blocked_reason else ""
        return [
            Alert(
                kind=AlertKind.PROCESS_BLOCKED,
                severity=AlertSeverity.CRITICAL,
                message=f"Заблокировано на этапе «{_stage_name(instance)}»{reason}",
                days=_days_since(instance.blocked_at or instance.current_stage_started_at),
                **_base(instance),
            )
        ]

    if instance.status != InteractionStatus.IN_PROGRESS:
        return []

    days = _days_since(instance.current_stage_started_at)
    stage = instance.current_stage
    limit = stage.sla_days if stage and stage.sla_days else norms.default_sla_days
    if days is not None and days > limit:
        return [
            Alert(
                kind=AlertKind.STAGE_STALE,
                subject=str(instance.current_stage_id),
                severity=_severity_by_days(days - limit, limit),
                message=(
                    f"Этап «{_stage_name(instance)}»: {days} дн. при норме {limit} дн. - "
                    f"просрочено на {days - limit} дн."
                ),
                days=days,
                **_base(instance),
            )
        ]
    return []


def _stage_name(instance: WorkflowInstance) -> str:
    return instance.current_stage.name if instance.current_stage else "без этапа"


def _interaction_alerts(instance: WorkflowInstance, today: date, norms: Norms) -> list[Alert]:
    found: list[Alert] = []
    open_ = instance.status in (
        InteractionStatus.DRAFT,
        InteractionStatus.IN_PROGRESS,
        InteractionStatus.BLOCKED,
    )
    if open_ and instance.manager_id is None:
        found.append(
            Alert(
                kind=AlertKind.NO_MANAGER,
                severity=AlertSeverity.WARNING,
                message="Не назначен ответственный",
                days=_days_since(instance.created_at),
                **_base(instance),
            )
        )

    contract = instance.contract
    if contract is not None and contract.status == ContractStatus.ACTIVE and contract.valid_to:
        left = (contract.valid_to - today).days
        if left <= norms.expiring_days:
            found.append(
                Alert(
                    kind=AlertKind.CONTRACT_EXPIRING,
                    severity=AlertSeverity.CRITICAL if left < 0 else AlertSeverity.WARNING,
                    message=(
                        f"Срок договора истёк {abs(left)} дн. назад"
                        if left < 0
                        else f"Срок договора заканчивается через {left} дн."
                    ),
                    days=left,
                    **_base(instance),
                )
            )

    if (
        contract is not None
        and contract.status == ContractStatus.ACTIVE
        and instance.programs
        and all(
            link.implementation_status == ProgramImplementationStatus.NOT_STARTED
            for link in instance.programs
        )
    ):
        found.append(
            Alert(
                kind=AlertKind.IMPLEMENTATION_NOT_STARTED,
                severity=AlertSeverity.INFO,
                message=(
                    f"Договор действует, а внедрение не начато ни по одной "
                    f"из {len(instance.programs)} программ"
                ),
                **_base(instance),
            )
        )
    return found


async def _license_alerts(
    session: AsyncSession, by_id: dict[uuid.UUID, WorkflowInstance], today: date, norms: Norms
) -> list[Alert]:
    """Сроки лицензий только по действующим договорам."""
    active = [
        interaction_id
        for interaction_id, instance in by_id.items()
        if instance.contract is not None and instance.contract.status == ContractStatus.ACTIVE
    ]
    if not active:
        return []
    statement = (
        select(License, InteractionProduct.workflow_instance_id)
        .join(InteractionProduct, InteractionProduct.id == License.interaction_product_id)
        .where(
            InteractionProduct.workflow_instance_id.in_(active),
            License.valid_to.is_not(None),
            License.status != LicenseStatus.REVOKED,
        )
    )
    found: list[Alert] = []
    for license_, interaction_id in (await session.execute(statement)).all():
        left = (license_.valid_to - today).days
        if left > norms.expiring_days:
            continue
        found.append(
            Alert(
                kind=AlertKind.LICENSE_EXPIRING,
                subject=str(license_.id),
                severity=AlertSeverity.CRITICAL if left < 0 else AlertSeverity.WARNING,
                message=(
                    f"Лицензия истекла {abs(left)} дн. назад"
                    if left < 0
                    else f"Срок лицензии заканчивается через {left} дн."
                ),
                days=left,
                **_base(by_id[interaction_id]),
            )
        )
    return found


async def _document_alerts(
    session: AsyncSession, by_id: dict[uuid.UUID, WorkflowInstance]
) -> list[Alert]:
    """Не загружен обязательный документ этапа или скан действующего договора."""
    if not by_id:
        return []
    present: dict[uuid.UUID, set[str]] = {}
    rows = await session.execute(
        select(Attachment.workflow_instance_id, Attachment.document_type)
        .where(Attachment.workflow_instance_id.in_(by_id))
        .group_by(Attachment.workflow_instance_id, Attachment.document_type)
    )
    for interaction_id, kind in rows.all():
        present.setdefault(interaction_id, set()).add(kind)

    found: list[Alert] = []
    for interaction_id, instance in by_id.items():
        stage = instance.current_stage
        have = present.get(interaction_id, set())
        if instance.status == InteractionStatus.IN_PROGRESS and stage is not None:
            missing = [item for item in stage.required_documents or [] if item not in have]
            if missing:
                names = ", ".join(label(DOCUMENT_TYPE_LABELS, item) for item in missing)
                found.append(
                    Alert(
                        kind=AlertKind.NO_DOCUMENTS,
                        subject=f"stage:{stage.id}",
                        severity=AlertSeverity.WARNING,
                        message=f"Этап «{stage.name}»: не загружены {names}",
                        days=_days_since(instance.current_stage_started_at),
                        **_base(instance),
                    )
                )
                continue
        contract = instance.contract
        if (
            contract is not None
            and contract.status == ContractStatus.ACTIVE
            and DocumentType.CONTRACT not in have
        ):
            found.append(
                Alert(
                    kind=AlertKind.NO_DOCUMENTS,
                    subject="scan",
                    severity=AlertSeverity.INFO,
                    message="Договор действует, а его скан не приложен",
                    **_base(instance),
                )
            )
    return found


async def _composition_alerts(
    session: AsyncSession, by_id: dict[uuid.UUID, WorkflowInstance]
) -> list[Alert]:
    """Продукт без связи с программой: данные нужно поправить."""
    open_ids = [
        interaction_id
        for interaction_id, instance in by_id.items()
        if instance.status
        in (InteractionStatus.DRAFT, InteractionStatus.IN_PROGRESS, InteractionStatus.BLOCKED)
    ]
    if not open_ids:
        return []
    rows = await session.execute(
        select(InteractionProduct.workflow_instance_id, func.count())
        .where(
            InteractionProduct.workflow_instance_id.in_(open_ids),
            ~InteractionProduct.program_links.any(),
        )
        .group_by(InteractionProduct.workflow_instance_id)
    )
    return [
        Alert(
            kind=AlertKind.PRODUCT_WITHOUT_PROGRAM,
            severity=AlertSeverity.WARNING,
            message=f"Продуктов без программы: {count} - свяжите их с программами",
            **_base(by_id[interaction_id]),
        )
        for interaction_id, count in rows.all()
    ]


async def _integration_alerts(session: AsyncSession) -> list[Alert]:
    """Последний запуск обмена завершился ошибкой или загрузил не всё."""
    last_run = (
        select(
            IntegrationRun.source_id,
            func.max(IntegrationRun.started_at).label("started_at"),
        )
        .group_by(IntegrationRun.source_id)
        .subquery()
    )
    statement = (
        select(IntegrationRun, IntegrationSource.name)
        .join(
            last_run,
            (IntegrationRun.source_id == last_run.c.source_id)
            & (IntegrationRun.started_at == last_run.c.started_at),
        )
        .join(IntegrationSource, IntegrationSource.id == IntegrationRun.source_id)
        .where(
            IntegrationRun.status.in_(
                [IntegrationRunStatus.FAILED, IntegrationRunStatus.PARTIAL]
            )
        )
    )
    found: list[Alert] = []
    for run, name in (await session.execute(statement)).all():
        failed = run.status == IntegrationRunStatus.FAILED
        found.append(
            Alert(
                kind=AlertKind.INTEGRATION_FAILED,
                subject=str(run.id),
                severity=AlertSeverity.WARNING,
                message=(
                    f"Последняя синхронизация «{name}» не удалась: {run.error_message}"
                    if failed
                    else f"Синхронизация «{name}» загрузила не всё: "
                    f"ошибок по записям - {run.records_failed}"
                ),
                days=_days_since(run.started_at),
                link="/integrations",
            )
        )
    return found


async def _queue_alerts(
    session: AsyncSession, principal: Principal, user: User
) -> list[Alert]:
    found: list[Alert] = []
    if access.can(principal, user, Action.RESOLVE_MAPPINGS):
        pending = await session.scalar(
            select(func.count())
            .select_from(IntegrationMapping)
            .where(IntegrationMapping.status == MappingStatus.PENDING)
        )
        if pending:
            found.append(
                Alert(
                    kind=AlertKind.MAPPING_PENDING,
                    severity=AlertSeverity.WARNING,
                    message=f"Записей LMS и сайта ждут сопоставления: {pending}",
                    link="/integrations?tab=mappings",
                )
            )
    if access.can(principal, user, Action.MANAGE_UNIVERSITIES):
        pending = await session.scalar(
            select(func.count())
            .select_from(University)
            .where(University.status == UniversityStatus.PENDING)
        )
        if pending:
            found.append(
                Alert(
                    kind=AlertKind.UNIVERSITY_PENDING,
                    severity=AlertSeverity.INFO,
                    message=(
                        f"Вузов на проверке: {pending} - подтвердите "
                        "или объедините с существующими"
                    ),
                    link="/universities?status=pending",
                )
            )
    return found


SEVERITY_ORDER = {
    AlertSeverity.CRITICAL: 0,
    AlertSeverity.WARNING: 1,
    AlertSeverity.INFO: 2,
}


async def load_norms(session: AsyncSession) -> Norms:
    values = await app_settings.load(session)
    return Norms(
        default_sla_days=values["alert_default_sla_days"],
        expiring_days=values["alert_expiring_days"],
    )


async def _collect_all(session: AsyncSession, principal: Principal, user: User) -> list[Alert]:
    today = date.today()
    norms = await load_norms(session)
    interactions = await reports.fetch_interactions(session, ReportFilters(), principal, user)
    by_id = {instance.id: instance for instance in interactions}

    found: list[Alert] = []
    for instance in interactions:
        found.extend(_process_alerts(instance, norms))
        found.extend(_interaction_alerts(instance, today, norms))
    found.extend(await _license_alerts(session, by_id, today, norms))
    found.extend(await _document_alerts(session, by_id))
    found.extend(await _composition_alerts(session, by_id))
    if access.can(principal, user, Action.VIEW_INTEGRATION_LOG):
        found.extend(await _integration_alerts(session))
    found.extend(await _queue_alerts(session, principal, user))

    found.sort(
        key=lambda alert: (
            SEVERITY_ORDER[alert.severity],
            -(alert.days if alert.days is not None else 0),
        )
    )
    return found


async def collect_all(session: AsyncSession, principal: Principal, user: User) -> list[Alert]:
    """Все поводы вмешаться по видимым взаимодействиям, через кэш."""
    await licenses.expire_overdue(session)
    key = cache.make_key(
        "alerts",
        str(user.id),
        sorted(principal.roles),
        sorted(user.permissions or []),
        access.effective_scope(principal, user).value,
        date.today(),
    )
    return await cache.cached(session, key, lambda: _collect_all(session, principal, user))


async def collect(
    session: AsyncSession,
    principal: Principal,
    user: User,
    *,
    kinds: set[AlertKind] | None = None,
    limit: int = 100,
) -> list[Alert]:
    """Поводы с отбором по видам, самые важные первыми."""
    found = await collect_all(session, principal, user)
    if kinds:
        found = [alert for alert in found if alert.kind in kinds]
    return found[:limit]


def summarize(alerts: list[Alert]) -> dict[str, int]:
    """Сколько поводов каждого вида."""
    return dict(Counter(alert.kind.value for alert in alerts))
