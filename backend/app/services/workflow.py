"""Бизнес-логика рабочего процесса по договору.

Здесь собраны все правила, которые не должны утечь в слой HTTP: какие
переходы разрешены, кто может пропускать этапы и как из истории переходов
получаются пять состояний этапа из раздела 3.4.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import Principal
from app.enums import Role, StageState, WorkflowEventType, WorkflowInstanceStatus
from app.models.user import User
from app.models.workflow import (
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStage,
    WorkflowTransition,
    WorkflowVersion,
)


class WorkflowError(Exception):
    """Нарушение правил процесса. Слой API превращает это в 409."""


def _now() -> datetime:
    return datetime.now(UTC)


async def load_version(session: AsyncSession, version_id: uuid.UUID) -> WorkflowVersion:
    """Версия шаблона вместе с этапами и переходами."""
    statement = (
        select(WorkflowVersion)
        .where(WorkflowVersion.id == version_id)
        .options(
            selectinload(WorkflowVersion.stages),
            selectinload(WorkflowVersion.transitions),
        )
    )
    version = (await session.execute(statement)).scalar_one_or_none()
    if version is None:
        raise WorkflowError("Версия шаблона не найдена")
    return version


async def latest_published_version(
    session: AsyncSession, template_id: uuid.UUID
) -> WorkflowVersion:
    """Текущая версия шаблона: последняя опубликованная.

    Новый договор получает её, а уже начатый процесс продолжает работать
    по своей версии (раздел 3.4).
    """
    statement = (
        select(WorkflowVersion)
        .where(
            WorkflowVersion.template_id == template_id,
            WorkflowVersion.published_at.is_not(None),
        )
        .order_by(WorkflowVersion.version_number.desc())
        .limit(1)
        .options(
            selectinload(WorkflowVersion.stages),
            selectinload(WorkflowVersion.transitions),
        )
    )
    version = (await session.execute(statement)).scalar_one_or_none()
    if version is None:
        raise WorkflowError("У шаблона нет опубликованных версий")
    return version


def initial_stage(version: WorkflowVersion) -> WorkflowStage:
    """Стартовый этап - этап с наименьшим порядком сортировки."""
    if not version.stages:
        raise WorkflowError("В версии шаблона нет этапов")
    return min(version.stages, key=lambda stage: stage.sort_order)


def available_transitions(
    version: WorkflowVersion, current_stage_id: uuid.UUID | None
) -> list[WorkflowTransition]:
    if current_stage_id is None:
        return []
    return [t for t in version.transitions if t.from_stage_id == current_stage_id]


def compute_stage_states(
    version: WorkflowVersion,
    instance: WorkflowInstance,
    events: list[WorkflowEvent],
) -> dict[uuid.UUID, StageState]:
    """Восстанавливает состояния всех этапов из истории переходов.

    Отдельной таблицы состояний нет: единственный источник истины -
    последовательность событий плюс текущий этап экземпляра.
    """
    states: dict[uuid.UUID, StageState] = {
        stage.id: StageState.NOT_STARTED for stage in version.stages
    }

    for event in events:
        if event.from_stage_id in states:
            if event.event_type == WorkflowEventType.FORWARD:
                states[event.from_stage_id] = StageState.COMPLETED
            elif event.event_type == WorkflowEventType.SKIPPED:
                states[event.from_stage_id] = StageState.SKIPPED
            elif event.event_type == WorkflowEventType.BACKWARD:
                # Возврат назад отменяет прохождение этапа, с которого вернулись.
                states[event.from_stage_id] = StageState.NOT_STARTED
        if event.to_stage_id in states and event.event_type in {
            WorkflowEventType.FORWARD,
            WorkflowEventType.BACKWARD,
            WorkflowEventType.SKIPPED,
            WorkflowEventType.STARTED,
        }:
            states[event.to_stage_id] = StageState.NOT_STARTED

    current = instance.current_stage_id
    if current in states:
        if instance.status == WorkflowInstanceStatus.COMPLETED:
            states[current] = StageState.COMPLETED
        elif instance.status == WorkflowInstanceStatus.BLOCKED:
            states[current] = StageState.BLOCKED
        else:
            states[current] = StageState.ACTIVE

    return states


async def start_instance(
    session: AsyncSession,
    contract_id: uuid.UUID,
    version: WorkflowVersion,
    user: User,
) -> WorkflowInstance:
    """Создаёт экземпляр процесса по договору и ставит его на стартовый этап."""
    if not version.is_published:
        # Черновик ещё правят: запускать по нему процессы нельзя, иначе
        # правка шаблона изменит ход уже идущей работы.
        raise WorkflowError("Версия шаблона не опубликована")

    existing = await session.execute(
        select(WorkflowInstance).where(
            WorkflowInstance.contract_id == contract_id,
            WorkflowInstance.status.in_(
                [WorkflowInstanceStatus.IN_PROGRESS, WorkflowInstanceStatus.BLOCKED]
            ),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise WorkflowError("По договору уже есть активный процесс")

    stage = initial_stage(version)
    now = _now()
    instance = WorkflowInstance(
        contract_id=contract_id,
        workflow_version_id=version.id,
        current_stage_id=stage.id,
        status=WorkflowInstanceStatus.IN_PROGRESS,
        current_stage_started_at=now,
        started_at=now,
    )
    session.add(instance)
    await session.flush()

    session.add(
        WorkflowEvent(
            workflow_instance_id=instance.id,
            from_stage_id=None,
            to_stage_id=stage.id,
            user_id=user.id,
            event_type=WorkflowEventType.STARTED,
            comment=None,
        )
    )
    await session.flush()
    return instance


def _find_transition(
    version: WorkflowVersion,
    from_stage_id: uuid.UUID,
    to_stage_id: uuid.UUID,
) -> WorkflowTransition:
    for transition in version.transitions:
        if transition.from_stage_id == from_stage_id and transition.to_stage_id == to_stage_id:
            return transition
    raise WorkflowError("Такой переход не предусмотрен шаблоном процесса")


def _stage_by_id(version: WorkflowVersion, stage_id: uuid.UUID) -> WorkflowStage:
    for stage in version.stages:
        if stage.id == stage_id:
            return stage
    raise WorkflowError("Этап не принадлежит версии шаблона этого процесса")


async def move(
    session: AsyncSession,
    instance: WorkflowInstance,
    version: WorkflowVersion,
    to_stage_id: uuid.UUID,
    user: User,
    principal: Principal,
    comment: str | None = None,
    skip: bool = False,
) -> WorkflowEvent:
    """Выполняет переход на разрешённый этап.

    Менеджер работает строго в пределах правил шаблона: структура шаблона
    здесь не меняется, проверяется только наличие перехода.
    """
    if instance.status != WorkflowInstanceStatus.IN_PROGRESS:
        raise WorkflowError(f"Процесс в статусе «{instance.status}», переход недоступен")
    if instance.current_stage_id is None:
        raise WorkflowError("У процесса не задан текущий этап")

    transition = _find_transition(version, instance.current_stage_id, to_stage_id)
    current_stage = _stage_by_id(version, instance.current_stage_id)
    target_stage = _stage_by_id(version, to_stage_id)

    if transition.requires_comment and not comment:
        raise WorkflowError("Для этого перехода обязателен комментарий")

    if skip:
        # Менеджер пропускает только необязательные этапы;
        # руководитель и администратор - любые (раздел 3.3).
        privileged = principal.has_role(Role.HEAD, Role.ADMIN)
        if not current_stage.is_optional and not privileged:
            raise WorkflowError("Этап обязательный, пропуск недоступен")
        if not comment:
            raise WorkflowError("При пропуске этапа нужно указать причину")
        event_type = WorkflowEventType.SKIPPED
    elif transition.is_backward:
        event_type = WorkflowEventType.BACKWARD
    else:
        event_type = WorkflowEventType.FORWARD

    event = WorkflowEvent(
        workflow_instance_id=instance.id,
        from_stage_id=instance.current_stage_id,
        to_stage_id=to_stage_id,
        user_id=user.id,
        event_type=event_type,
        comment=comment,
    )
    session.add(event)

    instance.current_stage_id = to_stage_id
    instance.current_stage_started_at = _now()
    if target_stage.is_final:
        instance.status = WorkflowInstanceStatus.COMPLETED
        instance.completed_at = _now()

    await session.flush()
    return event


async def set_blocked(
    session: AsyncSession,
    instance: WorkflowInstance,
    user: User,
    reason: str,
    blocked: bool,
) -> WorkflowEvent:
    """Блокирует или разблокирует процесс на текущем этапе."""
    if blocked and instance.status != WorkflowInstanceStatus.IN_PROGRESS:
        raise WorkflowError("Блокировать можно только процесс в работе")
    if not blocked and instance.status != WorkflowInstanceStatus.BLOCKED:
        raise WorkflowError("Процесс не заблокирован")

    instance.status = (
        WorkflowInstanceStatus.BLOCKED if blocked else WorkflowInstanceStatus.IN_PROGRESS
    )
    event = WorkflowEvent(
        workflow_instance_id=instance.id,
        from_stage_id=instance.current_stage_id,
        to_stage_id=instance.current_stage_id,
        user_id=user.id,
        event_type=(
            WorkflowEventType.BLOCKED if blocked else WorkflowEventType.UNBLOCKED
        ),
        comment=reason,
    )
    session.add(event)
    await session.flush()
    return event


async def get_instance(
    session: AsyncSession, instance_id: uuid.UUID
) -> WorkflowInstance | None:
    statement = (
        select(WorkflowInstance)
        .where(WorkflowInstance.id == instance_id)
        .options(selectinload(WorkflowInstance.events))
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def get_contract_instance(
    session: AsyncSession, contract_id: uuid.UUID
) -> WorkflowInstance | None:
    """Активный (или последний) процесс по договору.

    В первой версии у договора один активный экземпляр процесса.
    """
    statement = (
        select(WorkflowInstance)
        .where(WorkflowInstance.contract_id == contract_id)
        .order_by(WorkflowInstance.started_at.desc().nullslast())
        .limit(1)
        .options(selectinload(WorkflowInstance.events))
    )
    return (await session.execute(statement)).scalar_one_or_none()
