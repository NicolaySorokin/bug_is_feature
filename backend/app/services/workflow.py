"""Бизнес-логика взаимодействия и его рабочего процесса.

Какие переходы разрешены, кто пропускает этапы, когда процесс завершается
и с каким результатом. Статусы: draft, in_progress, blocked, completed,
cancelled. Для неуспешного завершения и отмены причина обязательна.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import mark_changed
from app.enums import (
    ClosureReason,
    InteractionOutcome,
    InteractionStatus,
    ProductTransferStatus,
    ProgramImplementationStatus,
    StageState,
    WorkflowEventType,
    WorkflowVersionStatus,
)
from app.models.content import Attachment
from app.models.interaction import InteractionProduct, InteractionProgram
from app.models.user import User
from app.models.workflow import (
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStage,
    WorkflowTemplate,
    WorkflowTransition,
    WorkflowVersion,
)
from app.services.labels import DOCUMENT_TYPE_LABELS, label

OPEN = (InteractionStatus.DRAFT, InteractionStatus.IN_PROGRESS, InteractionStatus.BLOCKED)


class WorkflowError(Exception):
    """Нарушение правил процесса. Слой API превращает это в 409."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details


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


async def active_version(session: AsyncSession, template_id: uuid.UUID) -> WorkflowVersion:
    """Действующая версия шаблона. Шаблон выбирает пользователь, версию система,
    начатый процесс идёт по своей.
    """
    template = await session.get(WorkflowTemplate, template_id)
    if template is None:
        raise WorkflowError("Шаблон процесса не найден")
    if not template.is_active:
        raise WorkflowError(
            f"Шаблон «{template.name}» отключён: новые процессы по нему не идут"
        )
    statement = (
        select(WorkflowVersion)
        .where(
            WorkflowVersion.template_id == template_id,
            WorkflowVersion.status == WorkflowVersionStatus.ACTIVE,
        )
        .options(
            selectinload(WorkflowVersion.stages),
            selectinload(WorkflowVersion.transitions),
        )
    )
    version = (await session.execute(statement)).scalar_one_or_none()
    if version is None:
        raise WorkflowError("У шаблона нет действующей версии - опубликуйте её")
    return version


# Старое имя: «последняя опубликованная» теперь значит «действующая».
latest_published_version = active_version


async def default_template(session: AsyncSession) -> WorkflowTemplate | None:
    """Основной шаблон: самый ранний включённый шаблон с действующей версией."""
    return await session.scalar(
        select(WorkflowTemplate)
        .join(WorkflowVersion, WorkflowVersion.template_id == WorkflowTemplate.id)
        .where(
            WorkflowTemplate.is_active.is_(True),
            WorkflowVersion.status == WorkflowVersionStatus.ACTIVE,
        )
        .order_by(WorkflowTemplate.created_at)
        .limit(1)
    )


def initial_stage(version: WorkflowVersion) -> WorkflowStage:
    """Стартовый этап, явно отмеченный в схеме."""
    for stage in version.stages:
        if stage.is_initial:
            return stage
    raise WorkflowError("В версии шаблона не отмечен стартовый этап")


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
    """Восстанавливает состояния этапов из истории переходов и текущего этапа."""
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
        if instance.status == InteractionStatus.COMPLETED:
            states[current] = StageState.COMPLETED
        elif instance.status == InteractionStatus.BLOCKED:
            states[current] = StageState.BLOCKED
        elif instance.status == InteractionStatus.CANCELLED:
            # Работа прекращена на этом этапе, он не пройден.
            states[current] = StageState.SKIPPED
        else:
            states[current] = StageState.ACTIVE

    return states


def _event(
    instance: WorkflowInstance,
    user: User | None,
    kind: WorkflowEventType,
    *,
    from_stage: uuid.UUID | None = None,
    to_stage: uuid.UUID | None = None,
    comment: str | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        id=uuid.uuid4(),
        workflow_instance_id=instance.id,
        from_stage_id=from_stage,
        to_stage_id=to_stage,
        user_id=user.id if user else None,
        event_type=kind,
        comment=comment,
    )


async def create_interaction(
    session: AsyncSession,
    *,
    university_id: uuid.UUID,
    version: WorkflowVersion,
    user: User | None,
    manager_id: uuid.UUID | None,
    title: str | None = None,
    comment: str | None = None,
    source: str = "manual",
    start: bool = False,
) -> WorkflowInstance:
    """Заводит взаимодействие-черновик. start сразу запускает процесс."""
    if version.status != WorkflowVersionStatus.ACTIVE:
        raise WorkflowError("Новые взаимодействия идут только по действующей версии шаблона")
    instance = WorkflowInstance(
        id=uuid.uuid4(),
        university_id=university_id,
        manager_id=manager_id,
        title=title,
        comment=comment,
        source=source,
        created_by_id=user.id if user else None,
        workflow_version_id=version.id,
        status=InteractionStatus.DRAFT,
    )
    session.add(instance)
    await session.flush()
    session.add(_event(instance, user, WorkflowEventType.CREATED))
    await session.flush()
    if start:
        await start_instance(session, instance, user)
    return instance


async def start_instance(
    session: AsyncSession, instance: WorkflowInstance, user: User | None
) -> WorkflowInstance:
    """Запускает процесс черновика со стартового этапа.

    Черновик перепривязывается к действующей версии шаблона: если шаблон
    успели обновить, процесс пойдёт по новой версии.
    """
    if instance.status != InteractionStatus.DRAFT:
        raise WorkflowError("Процесс уже запущен")
    current = await load_version(session, instance.workflow_version_id)
    version = await active_version(session, current.template_id)
    stage = initial_stage(version)
    now = _now()
    previous_version = instance.workflow_version_id
    instance.workflow_version_id = version.id
    instance.current_stage_id = stage.id
    instance.status = InteractionStatus.IN_PROGRESS
    instance.current_stage_started_at = now
    instance.started_at = now
    session.add(_event(instance, user, WorkflowEventType.STARTED, to_stage=stage.id))
    await session.flush()
    await apply_stage_statuses(session, instance, stage)
    if previous_version != version.id:
        await maybe_retire(session, previous_version)
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


async def missing_documents(
    session: AsyncSession, instance: WorkflowInstance, stage: WorkflowStage
) -> list[str]:
    """Типы обязательных документов этапа, которых нет во вложениях."""
    required = [item for item in stage.required_documents or [] if item]
    if not required:
        return []
    present = set(
        (
            await session.execute(
                select(Attachment.document_type).where(
                    Attachment.workflow_instance_id == instance.id,
                    Attachment.document_type.in_(required),
                )
            )
        ).scalars()
    )
    return [item for item in required if item not in present]


async def move(
    session: AsyncSession,
    instance: WorkflowInstance,
    version: WorkflowVersion,
    to_stage_id: uuid.UUID,
    user: User,
    *,
    comment: str | None = None,
    skip: bool = False,
    may_skip_required: bool = False,
    closure_reason: ClosureReason | None = None,
) -> WorkflowEvent:
    """Переход на разрешённый этап.

    Проверяются переход, комментарий, обязательные документы и правила пропуска.
    """
    if instance.status == InteractionStatus.DRAFT:
        raise WorkflowError("Процесс ещё не запущен")
    if instance.status != InteractionStatus.IN_PROGRESS:
        raise WorkflowError("Взаимодействие не в работе: переход недоступен")
    if instance.current_stage_id is None:
        raise WorkflowError("У процесса не задан текущий этап")

    transition = _find_transition(version, instance.current_stage_id, to_stage_id)
    current_stage = _stage_by_id(version, instance.current_stage_id)
    target_stage = _stage_by_id(version, to_stage_id)

    if transition.requires_comment and not comment:
        raise WorkflowError("Для этого перехода обязателен комментарий")

    if skip:
        # Менеджер пропускает только необязательные этапы, руководитель любые,
        # но с обязательной причиной.
        if not current_stage.is_optional and not may_skip_required:
            raise WorkflowError("Этап обязательный, пропуск недоступен")
        if not comment:
            raise WorkflowError("При пропуске этапа нужно указать причину")
        event_type = WorkflowEventType.SKIPPED
    elif transition.is_backward:
        event_type = WorkflowEventType.BACKWARD
    else:
        event_type = WorkflowEventType.FORWARD
        missing = await missing_documents(session, instance, current_stage)
        if missing:
            names = ", ".join(label(DOCUMENT_TYPE_LABELS, item) for item in missing)
            raise WorkflowError(
                f"Чтобы завершить этап «{current_stage.name}», загрузите документы: {names}",
                details={"missing_documents": missing},
            )

    outcome = target_stage.outcome if target_stage.is_final else None
    if target_stage.is_final and outcome not in (None, InteractionOutcome.SUCCESSFUL):
        if closure_reason is None:
            raise WorkflowError("Укажите причину: этап завершает взаимодействие без успеха")
        if closure_reason is ClosureReason.OTHER and not comment:
            raise WorkflowError("Для причины «Иное» нужен комментарий")

    event = WorkflowEvent(
        workflow_instance_id=instance.id,
        from_stage_id=instance.current_stage_id,
        to_stage_id=to_stage_id,
        user_id=user.id,
        event_type=event_type,
        comment=comment,
    )
    session.add(event)

    now = _now()
    instance.current_stage_id = to_stage_id
    instance.current_stage_started_at = now
    if event_type != WorkflowEventType.BACKWARD:
        await apply_stage_statuses(session, instance, target_stage)
    if target_stage.is_final:
        instance.status = InteractionStatus.COMPLETED
        instance.outcome = outcome or InteractionOutcome.SUCCESSFUL
        instance.closure_reason = (
            closure_reason if instance.outcome != InteractionOutcome.SUCCESSFUL else None
        )
        instance.closure_comment = comment
        instance.closed_by_id = user.id
        instance.closed_at = now

    await session.flush()
    if target_stage.is_final:
        await maybe_retire(session, instance.workflow_version_id)
    return event


async def apply_stage_statuses(
    session: AsyncSession, instance: WorkflowInstance, stage: WorkflowStage
) -> None:
    """Этап сам ставит статусы внедрения программ и передачи продуктов.

    Приостановленные позиции не трогаем, это решение человека. Возврат назад
    статусы не откатывает.
    """
    if stage.program_status_on_enter:
        await session.execute(
            update(InteractionProgram)
            .where(
                InteractionProgram.workflow_instance_id == instance.id,
                InteractionProgram.implementation_status
                != ProgramImplementationStatus.SUSPENDED,
            )
            .values(implementation_status=stage.program_status_on_enter)
        )
    if stage.product_status_on_enter:
        await session.execute(
            update(InteractionProduct)
            .where(
                InteractionProduct.workflow_instance_id == instance.id,
                InteractionProduct.transfer_status != ProductTransferStatus.SUSPENDED,
            )
            .values(transfer_status=stage.product_status_on_enter)
        )
    if stage.program_status_on_enter or stage.product_status_on_enter:
        mark_changed(session)


async def set_blocked(
    session: AsyncSession,
    instance: WorkflowInstance,
    user: User,
    reason: str,
    blocked: bool,
) -> WorkflowEvent:
    """Блокирует или разблокирует процесс на текущем этапе. Причина обязательна."""
    if blocked and instance.status != InteractionStatus.IN_PROGRESS:
        raise WorkflowError("Блокировать можно только взаимодействие в работе")
    if not blocked and instance.status != InteractionStatus.BLOCKED:
        raise WorkflowError("Взаимодействие не заблокировано")

    now = _now()
    instance.status = InteractionStatus.BLOCKED if blocked else InteractionStatus.IN_PROGRESS
    instance.blocked_reason = reason if blocked else None
    instance.blocked_at = now if blocked else None
    event = _event(
        instance,
        user,
        WorkflowEventType.BLOCKED if blocked else WorkflowEventType.UNBLOCKED,
        from_stage=instance.current_stage_id,
        to_stage=instance.current_stage_id,
        comment=reason,
    )
    session.add(event)
    await session.flush()
    return event


async def cancel(
    session: AsyncSession,
    instance: WorkflowInstance,
    user: User,
    reason: ClosureReason,
    comment: str | None,
) -> WorkflowEvent:
    """Досрочное прекращение: причина обязательна, результат неуспешный."""
    if instance.status not in OPEN:
        raise WorkflowError("Взаимодействие уже закрыто")
    if reason is ClosureReason.OTHER and not comment:
        raise WorkflowError("Для причины «Иное» нужен комментарий")
    now = _now()
    instance.status = InteractionStatus.CANCELLED
    instance.outcome = InteractionOutcome.UNSUCCESSFUL
    instance.closure_reason = reason
    instance.closure_comment = comment
    instance.closed_by_id = user.id
    instance.closed_at = now
    # Закрытое взаимодействие не «заблокировано»: блокировка остаётся в истории.
    instance.blocked_reason = None
    instance.blocked_at = None
    event = _event(
        instance,
        user,
        WorkflowEventType.CANCELLED,
        from_stage=instance.current_stage_id,
        to_stage=instance.current_stage_id,
        comment=comment,
    )
    session.add(event)
    await session.flush()
    await maybe_retire(session, instance.workflow_version_id)
    return event


async def reassign(
    session: AsyncSession,
    instance: WorkflowInstance,
    user: User,
    manager: User | None,
    previous: User | None,
) -> WorkflowEvent:
    """Смена ответственного попадает в историю событием."""
    instance.manager_id = manager.id if manager else None
    before = previous.full_name if previous else "не назначен"
    after = manager.full_name if manager else "не назначен"
    event = _event(
        instance,
        user,
        WorkflowEventType.REASSIGNED,
        from_stage=instance.current_stage_id,
        to_stage=instance.current_stage_id,
        comment=f"Ответственный: {before} → {after}",
    )
    session.add(event)
    await session.flush()
    return event


async def maybe_retire(session: AsyncSession, version_id: uuid.UUID) -> None:
    """Устаревшая версия без открытых взаимодействий выводится из использования."""
    version = await session.get(WorkflowVersion, version_id)
    if version is None or version.status != WorkflowVersionStatus.DEPRECATED:
        return
    open_count = await session.scalar(
        select(func.count())
        .select_from(WorkflowInstance)
        .where(
            WorkflowInstance.workflow_version_id == version_id,
            WorkflowInstance.status.in_(OPEN),
        )
    )
    if not open_count:
        version.status = WorkflowVersionStatus.RETIRED
        version.retired_at = _now()
        await session.flush()


async def get_instance(
    session: AsyncSession, instance_id: uuid.UUID
) -> WorkflowInstance | None:
    statement = (
        select(WorkflowInstance)
        .where(WorkflowInstance.id == instance_id)
        .options(
            selectinload(WorkflowInstance.events).selectinload(WorkflowEvent.user),
            selectinload(WorkflowInstance.university),
        )
    )
    return (await session.execute(statement)).scalar_one_or_none()
