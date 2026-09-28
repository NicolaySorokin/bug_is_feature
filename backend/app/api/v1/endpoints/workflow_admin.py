"""Шаблоны процессов: создание, правка схемы, публикация версий.

Редактор сохраняет схему целиком через PUT /versions/{id}/graph. Структуру
меняет администратор. Названия этапов и расположение узлов правит ещё
и сотрудник с отдельным правом.
"""

import uuid

from fastapi import APIRouter, status

from app.api.deps import SessionDep, require_action
from app.core.errors import NotFoundError
from app.models.workflow import WorkflowStage
from app.schemas.workflow import (
    GraphWrite,
    LayoutWrite,
    StageRead,
    StageRename,
    TemplateCreate,
    TemplateRead,
    TemplateUpdate,
    VersionCreate,
    VersionGraph,
    VersionRead,
)
from app.services import workflow_admin
from app.services.access import Action

router = APIRouter(
    prefix="/workflow",
    tags=["workflow admin"],
    dependencies=[
        require_action(Action.EDIT_TEMPLATES, "Шаблоны процессов меняет администратор")
    ],
)
# Правки, которые не меняют ход процессов: по отдельному праву.
presentation_router = APIRouter(
    prefix="/workflow",
    tags=["workflow admin"],
    dependencies=[
        require_action(
            Action.EDIT_WORKFLOW_PRESENTATION,
            "Названия этапов и расположение схемы меняют по отдельному праву",
        )
    ],
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


@presentation_router.put(
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
    description=(
        "Схема проверяется целиком (details.problems - что мешает). Версия "
        "становится действующей, прежняя - устаревшей: новые взаимодействия "
        "пойдут по новой, начатые продолжат по своей."
    ),
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


@presentation_router.patch(
    "/stages/{stage_id}",
    response_model=StageRead,
    summary="Переименовать статус (этап) процесса",
    description=(
        "Корректировка названия и описания этапа. Работает и в опубликованной "
        "версии: на ход процессов название не влияет, а новое видно сразу - "
        "в схеме, истории и отчётах."
    ),
)
async def rename_stage(
    stage_id: uuid.UUID, payload: StageRename, session: SessionDep
) -> StageRead:
    stage = await session.get(WorkflowStage, stage_id)
    if stage is None:
        raise NotFoundError("Этап не найден")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "name" and value is None:
            continue
        setattr(stage, field, value)
    await session.flush()
    return StageRead.model_validate(stage)
