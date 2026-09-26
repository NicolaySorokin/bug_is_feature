"""Контроль проблемных процессов.

Раздел 7 концепции: на главной выделяются договоры, по которым требуется
действие. Каждое правило отвечает на три вопроса - что не так, кто за это
отвечает и сколько времени ситуация не меняется.

Правила намеренно собраны в одном месте и работают по уже загруженной
выборке договоров: так их легко читать, проверять и дополнять, а база
опрашивается один раз, а не по разу на правило.
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
    ImplementationStatus,
    IntegrationRunStatus,
    LicenseStatus,
    WorkflowInstanceStatus,
)
from app.models.content import Attachment
from app.models.contract import Contract, ContractProduct, License
from app.models.integration import IntegrationRun, IntegrationSource
from app.models.user import User
from app.schemas.report import ReportFilters
from app.services import app_settings, cache, reports


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
    contract_id: uuid.UUID | None = None
    contract_number: str = ""
    university_name: str = ""
    manager_id: uuid.UUID | None = None
    manager_name: str = ""
    days: int | None = None  # сколько времени ситуация не меняется


def _severity_by_days(days: int | None, limit: int) -> AlertSeverity:
    """Чем дольше висит ситуация, тем выше важность."""
    if days is None:
        return AlertSeverity.WARNING
    if days < 0 or days >= limit * 2:
        return AlertSeverity.CRITICAL
    return AlertSeverity.WARNING


def _base(contract: Contract) -> dict:
    return {
        "contract_id": contract.id,
        "contract_number": contract.number,
        "university_name": contract.university.name if contract.university else "",
        "manager_id": contract.manager_id,
        "manager_name": contract.manager.full_name if contract.manager else "",
    }


def _process_alerts(contract: Contract, norms: Norms) -> list[Alert]:
    instance = reports.active_instance(contract)
    if instance is None:
        if contract.status in {ContractStatus.DRAFT, ContractStatus.ACTIVE}:
            return [
                Alert(
                    kind=AlertKind.PROCESS_NOT_STARTED,
                    severity=AlertSeverity.INFO,
                    message="По договору не запущен рабочий процесс",
                    **_base(contract),
                )
            ]
        return []

    if instance.status == WorkflowInstanceStatus.BLOCKED:
        return [
            Alert(
                kind=AlertKind.PROCESS_BLOCKED,
                severity=AlertSeverity.CRITICAL,
                message=f"Процесс заблокирован на этапе «{_stage_name(instance)}»",
                days=_days_on_stage(instance),
                **_base(contract),
            )
        ]

    if instance.status != WorkflowInstanceStatus.IN_PROGRESS:
        return []

    days = _days_on_stage(instance)
    stage = instance.current_stage
    limit = stage.sla_days if stage and stage.sla_days else norms.default_sla_days
    if days is not None and days > limit:
        return [
            Alert(
                kind=AlertKind.STAGE_STALE,
                severity=_severity_by_days(days - limit, limit),
                message=(
                    f"Этап «{_stage_name(instance)}» не менялся {days} дн. "
                    f"при норме {limit} дн."
                ),
                days=days,
                **_base(contract),
            )
        ]
    return []


def _stage_name(instance) -> str:  # noqa: ANN001 - модель SQLAlchemy
    return instance.current_stage.name if instance.current_stage else "без этапа"


def _days_on_stage(instance) -> int | None:  # noqa: ANN001 - модель SQLAlchemy
    if instance.current_stage_started_at is None:
        return None
    return (datetime.now(UTC) - instance.current_stage_started_at).days


def _contract_alerts(contract: Contract, today: date, norms: Norms) -> list[Alert]:
    found: list[Alert] = []

    if contract.manager_id is None:
        found.append(
            Alert(
                kind=AlertKind.NO_MANAGER,
                severity=AlertSeverity.WARNING,
                message="По договору не назначен ответственный",
                **_base(contract),
            )
        )

    if contract.status == ContractStatus.ACTIVE and contract.valid_to is not None:
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
                    **_base(contract),
                )
            )

    if contract.status == ContractStatus.ACTIVE and contract.programs:
        stalled = [
            link
            for link in contract.programs
            if link.implementation_status == ImplementationStatus.NOT_STARTED
        ]
        if len(stalled) == len(contract.programs):
            found.append(
                Alert(
                    kind=AlertKind.IMPLEMENTATION_NOT_STARTED,
                    severity=AlertSeverity.INFO,
                    message=f"Не начато внедрение ни по одной из {len(stalled)} программ",
                    **_base(contract),
                )
            )

    return found


async def _license_alerts(
    session: AsyncSession, contracts: dict[uuid.UUID, Contract], today: date, norms: Norms
) -> list[Alert]:
    """Сроки лицензий - только по действующим договорам.

    Лицензия закрытого или приостановленного договора, как и отозванная
    лицензия, действия не требует: иначе давно закрытый договор вечно
    висел бы критичной тревогой.
    """
    active = [
        contract_id
        for contract_id, contract in contracts.items()
        if contract.status == ContractStatus.ACTIVE
    ]
    if not active:
        return []
    statement = (
        select(License, ContractProduct.contract_id)
        .join(ContractProduct, ContractProduct.id == License.contract_product_id)
        .where(
            ContractProduct.contract_id.in_(active),
            License.valid_to.is_not(None),
            License.status != LicenseStatus.REVOKED,
        )
    )
    found: list[Alert] = []
    for license_, contract_id in (await session.execute(statement)).all():
        left = (license_.valid_to - today).days
        if left > norms.expiring_days:
            continue
        contract = contracts[contract_id]
        found.append(
            Alert(
                kind=AlertKind.LICENSE_EXPIRING,
                severity=AlertSeverity.CRITICAL if left < 0 else AlertSeverity.WARNING,
                message=(
                    f"Лицензия истекла {abs(left)} дн. назад"
                    if left < 0
                    else f"Срок лицензии заканчивается через {left} дн."
                ),
                days=left,
                **_base(contract),
            )
        )
    return found


async def _document_alerts(
    session: AsyncSession, contracts: dict[uuid.UUID, Contract]
) -> list[Alert]:
    """Действующий договор без единого приложенного документа."""
    active = {
        contract_id: contract
        for contract_id, contract in contracts.items()
        if contract.status == ContractStatus.ACTIVE
    }
    if not active:
        return []

    with_files = set(
        (
            await session.execute(
                select(Attachment.contract_id)
                .where(Attachment.contract_id.in_(active))
                .group_by(Attachment.contract_id)
            )
        ).scalars()
    )
    return [
        Alert(
            kind=AlertKind.NO_DOCUMENTS,
            severity=AlertSeverity.INFO,
            message="К действующему договору не приложено ни одного документа",
            **_base(contract),
        )
        for contract_id, contract in active.items()
        if contract_id not in with_files
    ]


async def _integration_alerts(session: AsyncSession) -> list[Alert]:
    """Последний запуск обмена завершился ошибкой."""
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
        .where(IntegrationRun.status == IntegrationRunStatus.FAILED)
    )
    return [
        Alert(
            kind=AlertKind.INTEGRATION_FAILED,
            severity=AlertSeverity.WARNING,
            message=f"Последняя синхронизация «{name}» не удалась: {run.error_message}",
            days=(datetime.now(UTC) - run.started_at).days if run.started_at else None,
        )
        for run, name in (await session.execute(statement)).all()
    ]


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
    contracts = await reports.fetch_contracts(session, ReportFilters(), principal, user)
    by_id = {contract.id: contract for contract in contracts}

    found: list[Alert] = []
    for contract in contracts:
        found.extend(_process_alerts(contract, norms))
        found.extend(_contract_alerts(contract, today, norms))
    found.extend(await _license_alerts(session, by_id, today, norms))
    found.extend(await _document_alerts(session, by_id))
    found.extend(await _integration_alerts(session))

    found.sort(
        key=lambda alert: (
            SEVERITY_ORDER[alert.severity],
            -(alert.days if alert.days is not None else 0),
        )
    )
    return found


async def collect_all(session: AsyncSession, principal: Principal, user: User) -> list[Alert]:
    """Все поводы вмешаться по договорам, видимым пользователю, - через кэш."""
    key = cache.make_key(
        "alerts", str(user.id), sorted(principal.roles), user.data_scope, date.today()
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
    """Поводы вмешаться с отбором по видам, самые важные - первыми."""
    found = await collect_all(session, principal, user)
    if kinds:
        found = [alert for alert in found if alert.kind in kinds]
    return found[:limit]


def summarize(alerts: list[Alert]) -> dict[str, int]:
    """Сколько поводов каждого вида - для плашек на главной."""
    return dict(Counter(alert.kind.value for alert in alerts))
