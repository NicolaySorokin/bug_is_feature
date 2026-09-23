"""Рабочий процесс: шаблоны, схема, история и переходы."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    ContractDep,
    CurrentUserDep,
    PrincipalDep,
    SessionDep,
    require_roles,
)
from app.core.errors import ConflictError, ErrorCode, NotFoundError
from app.core.security import Principal
from app.enums import Role
from app.models.contract import Contract
from app.models.user import User
from app.models.workflow import WorkflowEvent, WorkflowInstance, WorkflowTemplate, WorkflowVersion
from app.schemas.workflow import (
    BlockRequest,
    EventRead,
    InstanceView,
    SkipRequest,
    StageInstanceState,
    StartRequest,
    TemplateRead,
    TransitionRead,
    TransitionRequest,
    VersionGraph,
    VersionRead,
)
from app.services import access
from app.services import workflow as workflow_service

router = APIRouter(prefix="/workflow", tags=["workflow"])
contract_router = APIRouter(prefix="/contracts", tags=["workflow"])


def _conflict(exc: workflow_service.WorkflowError) -> ConflictError:
    """Нарушение правил процесса клиент отличает по коду workflow_rule_violated."""
    return ConflictError(str(exc), code=ErrorCode.WORKFLOW_RULE_VIOLATED)


async def _build_view(session: AsyncSession, instance: WorkflowInstance) -> InstanceView:
    """Собирает полное представление процесса: схема, состояния, история."""
    version = await workflow_service.load_version(session, instance.workflow_version_id)
    event_result = await session.execute(
        select(WorkflowEvent)
        .where(WorkflowEvent.workflow_instance_id == instance.id)
        .options(selectinload(WorkflowEvent.user))
        .order_by(WorkflowEvent.created_at)
    )
    events = list(event_result.scalars())
    states = workflow_service.compute_stage_states(version, instance, events)
    transitions = workflow_service.available_transitions(version, instance.current_stage_id)

    return InstanceView(
        id=instance.id,
        contract_id=instance.contract_id,
        workflow_version_id=instance.workflow_version_id,
        current_stage_id=instance.current_stage_id,
        status=instance.status,
        current_stage_started_at=instance.current_stage_started_at,
        started_at=instance.started_at,
        completed_at=instance.completed_at,
        version=VersionGraph.model_validate(version),
        stage_states=[
            StageInstanceState(stage_id=stage_id, state=state)
            for stage_id, state in states.items()
        ],
        available_transitions=[TransitionRead.model_validate(t) for t in transitions],
        events=[EventRead.model_validate(event) for event in events],
    )


async def _get_instance(
    session: AsyncSession,
    instance_id: uuid.UUID,
    principal: Principal,
    user: User,
) -> WorkflowInstance:
    """Экземпляр процесса вместе с проверкой прав на его договор."""
    instance = await workflow_service.get_instance(session, instance_id)
    if instance is None:
        raise NotFoundError("Процесс не найден")

    contract = (
        await session.execute(
            select(Contract)
            .where(Contract.id == instance.contract_id)
            .options(selectinload(Contract.university))
        )
    ).scalar_one()
    access.ensure_contract_access(contract, principal, user)
    return instance


# --- Шаблоны и версии ---------------------------------------------------------


@router.get("/templates", response_model=list[TemplateRead], summary="Шаблоны процессов")
async def list_templates(session: SessionDep, _: CurrentUserDep) -> list[TemplateRead]:
    result = await session.execute(select(WorkflowTemplate).order_by(WorkflowTemplate.name))
    return [TemplateRead.model_validate(row) for row in result.scalars()]


@router.get(
    "/templates/{template_id}/versions",
    response_model=list[VersionRead],
    summary="Версии шаблона",
)
async def list_versions(
    template_id: uuid.UUID, session: SessionDep, _: CurrentUserDep
) -> list[VersionRead]:
    result = await session.execute(
        select(WorkflowVersion)
        .where(WorkflowVersion.template_id == template_id)
        .order_by(WorkflowVersion.version_number.desc())
    )
    return [VersionRead.model_validate(row) for row in result.scalars()]


@router.get(
    "/versions/{version_id}",
    response_model=VersionGraph,
    summary="Схема версии шаблона",
)
async def read_version(
    version_id: uuid.UUID, session: SessionDep, _: CurrentUserDep
) -> VersionGraph:
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
        raise NotFoundError("Версия шаблона не найдена")
    return VersionGraph.model_validate(version)


# --- Процесс по договору ------------------------------------------------------


@contract_router.get(
    "/{contract_id}/workflow",
    response_model=InstanceView,
    summary="Процесс по договору",
)
async def read_contract_workflow(
    contract: ContractDep, session: SessionDep
) -> InstanceView:
    instance = await workflow_service.get_contract_instance(session, contract.id)
    if instance is None:
        raise NotFoundError("По договору нет запущенного процесса")
    return await _build_view(session, instance)


@contract_router.post(
    "/{contract_id}/workflow",
    response_model=InstanceView,
    status_code=status.HTTP_201_CREATED,
    summary="Запустить процесс по договору",
)
async def start_contract_workflow(
    contract: ContractDep,
    payload: StartRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> InstanceView:
    try:
        version = (
            await workflow_service.load_version(session, payload.version_id)
            if payload.version_id
            else await workflow_service.latest_published_version(session, payload.template_id)
        )
        instance = await workflow_service.start_instance(session, contract.id, version, user)
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc

    await session.refresh(instance, ["events"])
    return await _build_view(session, instance)


# --- Действия по процессу -----------------------------------------------------


@router.post(
    "/instances/{instance_id}/transition",
    response_model=InstanceView,
    summary="Перейти на разрешённый этап",
)
async def transition(
    instance_id: uuid.UUID,
    payload: TransitionRequest,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> InstanceView:
    instance = await _get_instance(session, instance_id, principal, user)
    try:
        version = await workflow_service.load_version(session, instance.workflow_version_id)
        await workflow_service.move(
            session,
            instance,
            version,
            payload.to_stage_id,
            user,
            principal,
            comment=payload.comment,
        )
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc

    await session.refresh(instance, ["events"])
    return await _build_view(session, instance)


@router.post(
    "/instances/{instance_id}/skip",
    response_model=InstanceView,
    summary="Пропустить необязательный этап",
)
async def skip_stage(
    instance_id: uuid.UUID,
    payload: SkipRequest,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> InstanceView:
    instance = await _get_instance(session, instance_id, principal, user)
    try:
        version = await workflow_service.load_version(session, instance.workflow_version_id)
        await workflow_service.move(
            session,
            instance,
            version,
            payload.to_stage_id,
            user,
            principal,
            comment=payload.reason,
            skip=True,
        )
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc

    await session.refresh(instance, ["events"])
    return await _build_view(session, instance)


@router.post(
    "/instances/{instance_id}/block",
    response_model=InstanceView,
    summary="Заблокировать процесс",
)
async def block(
    instance_id: uuid.UUID,
    payload: BlockRequest,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> InstanceView:
    instance = await _get_instance(session, instance_id, principal, user)
    try:
        await workflow_service.set_blocked(session, instance, user, payload.reason, True)
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc

    await session.refresh(instance, ["events"])
    return await _build_view(session, instance)


@router.post(
    "/instances/{instance_id}/unblock",
    response_model=InstanceView,
    dependencies=[Depends(require_roles(Role.MANAGER, Role.HEAD, Role.ADMIN))],
    summary="Снять блокировку процесса",
)
async def unblock(
    instance_id: uuid.UUID,
    payload: BlockRequest,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> InstanceView:
    instance = await _get_instance(session, instance_id, principal, user)
    try:
        await workflow_service.set_blocked(session, instance, user, payload.reason, False)
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc

    await session.refresh(instance, ["events"])
    return await _build_view(session, instance)
