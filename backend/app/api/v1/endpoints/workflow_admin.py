"""Шаблоны рабочих процессов: создание, правка схемы, публикация версий.

Это серверная часть визуального редактора (раздел 3.2 концепции). Редактор
сохраняет схему целиком - список этапов и переходов между ними, - поэтому
основной метод здесь один: ``PUT /versions/{id}/graph``.

Доступ у администратора: менеджер работает внутри правил шаблона,
но саму структуру не меняет.
"""

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import SessionDep, require_roles
from app.enums import Role
from app.schemas.workflow import (
    GraphWrite,
    LayoutWrite,
    TemplateCreate,
    TemplateRead,
    TemplateUpdate,
    VersionCreate,
    VersionGraph,
    VersionRead,
)
from app.services import workflow_admin

router = APIRouter(
    prefix="/workflow",
    tags=["workflow admin"],
    dependencies=[Depends(require_roles(Role.ADMIN))],
)


@router.post(
    "/templates",
    response_model=VersionGraph,
    status_code=status.HTTP_201_CREATED,
    summary="Создать шаблон процесса",
    description="Создаёт шаблон и первую версию-черновик. Схему можно задать сразу.",
)
async def create_template(payload: TemplateCreate, session: SessionDep) -> VersionGraph:
    _, version = await workflow_admin.create_template(
        session, payload.name, payload.description, payload.graph
    )
    return VersionGraph.model_validate(await workflow_admin.get_version(session, version.id))


@router.patch(
    "/templates/{template_id}",
    response_model=TemplateRead,
    summary="Изменить шаблон",
)
async def update_template(
    template_id: uuid.UUID, payload: TemplateUpdate, session: SessionDep
) -> TemplateRead:
    template = await workflow_admin.get_template(session, template_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    await session.flush()
    return TemplateRead.model_validate(template)


@router.post(
    "/templates/{template_id}/versions",
    response_model=VersionGraph,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новую версию шаблона",
    description=(
        "По умолчанию новая версия копирует схему последней существующей. "
        "Запущенные процессы остаются на своих версиях."
    ),
)
async def create_version(
    template_id: uuid.UUID, payload: VersionCreate, session: SessionDep
) -> VersionGraph:
    template = await workflow_admin.get_template(session, template_id)
    version = await workflow_admin.create_version(
        session, template, payload.from_version_id, payload.copy_graph
    )
    return VersionGraph.model_validate(await workflow_admin.get_version(session, version.id))


@router.put(
    "/versions/{version_id}/graph",
    response_model=VersionGraph,
    summary="Сохранить схему версии",
    description=(
        "Заменяет этапы и переходы черновика целиком. Опубликованную версию "
        "менять нельзя - создайте новую."
    ),
)
async def save_graph(
    version_id: uuid.UUID, payload: GraphWrite, session: SessionDep
) -> VersionGraph:
    version = await workflow_admin.get_version(session, version_id)
    return VersionGraph.model_validate(
        await workflow_admin.replace_graph(session, version, payload)
    )


@router.put(
    "/versions/{version_id}/layout",
    response_model=VersionGraph,
    summary="Сохранить расположение узлов схемы",
    description=(
        "Координаты узлов на бизнес-логику не влияют, поэтому их можно менять "
        "и в опубликованной версии."
    ),
)
async def save_layout(
    version_id: uuid.UUID, payload: LayoutWrite, session: SessionDep
) -> VersionGraph:
    version = await workflow_admin.get_version(session, version_id)
    return VersionGraph.model_validate(
        await workflow_admin.save_layout(session, version, payload)
    )


@router.post(
    "/versions/{version_id}/publish",
    response_model=VersionRead,
    summary="Опубликовать версию",
    description="После публикации схема неизменна, а новые договоры пойдут по ней.",
)
async def publish_version(version_id: uuid.UUID, session: SessionDep) -> VersionRead:
    version = await workflow_admin.get_version(session, version_id)
    return VersionRead.model_validate(await workflow_admin.publish(session, version))


@router.delete(
    "/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить черновик версии",
)
async def delete_version(version_id: uuid.UUID, session: SessionDep) -> None:
    version = await workflow_admin.get_version(session, version_id)
    await workflow_admin.delete_version(session, version)
