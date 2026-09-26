"""Шаблоны процессов и их версии - для чтения.

Ход конкретного взаимодействия (схема, история, переходы) - в разделе
``/interactions/{id}``. Здесь - справочная часть: какие шаблоны есть, какая
версия у каждого действует и как выглядит схема версии.
"""

import uuid

from fastapi import APIRouter
from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserDep, SessionDep
from app.core.errors import NotFoundError
from app.enums import WorkflowVersionStatus
from app.models.workflow import WorkflowInstance, WorkflowTemplate, WorkflowVersion
from app.schemas.workflow import TemplateRead, VersionGraph, VersionRead
from app.services import workflow as workflow_service

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.get("/templates", response_model=list[TemplateRead], summary="Шаблоны процессов")
async def list_templates(session: SessionDep, _: CurrentUserDep) -> list[TemplateRead]:
    active = (
        select(WorkflowVersion.template_id, WorkflowVersion.id, WorkflowVersion.version_number)
        .where(WorkflowVersion.status == WorkflowVersionStatus.ACTIVE)
        .subquery()
    )
    result = await session.execute(
        select(WorkflowTemplate, active.c.id, active.c.version_number)
        .outerjoin(active, active.c.template_id == WorkflowTemplate.id)
        .order_by(WorkflowTemplate.created_at)
    )
    items = []
    for template, version_id, number in result.all():
        item = TemplateRead.model_validate(template)
        item.active_version_id = version_id
        item.active_version_number = number
        items.append(item)
    return items


@router.get(
    "/templates/{template_id}/versions",
    response_model=list[VersionRead],
    summary="Версии шаблона",
)
async def list_versions(
    template_id: uuid.UUID, session: SessionDep, _: CurrentUserDep
) -> list[VersionRead]:
    used = (
        select(
            WorkflowInstance.workflow_version_id,
            func.count().label("total"),
            func.count(case((WorkflowInstance.status.in_(workflow_service.OPEN), 1))).label(
                "open"
            ),
        )
        .group_by(WorkflowInstance.workflow_version_id)
        .subquery()
    )
    result = await session.execute(
        select(WorkflowVersion, used.c.total, used.c.open)
        .outerjoin(used, used.c.workflow_version_id == WorkflowVersion.id)
        .where(WorkflowVersion.template_id == template_id)
        .order_by(WorkflowVersion.version_number.desc())
    )
    versions = []
    for version, total, open_ in result.all():
        item = VersionRead.model_validate(version)
        item.instances_count = total or 0
        item.open_instances_count = open_ or 0
        versions.append(item)
    return versions


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
