"""Редактирование шаблонов рабочих процессов.

Ключевое правило раздела 3.1 концепции: изменение шаблона не меняет уже
запущенные процессы. Отсюда весь порядок работы:

* этапы и переходы правятся только в черновике - версии без ``published_at``;
* публикация фиксирует версию, и после неё схема неизменна;
* новый договор получает последнюю опубликованную версию, а запущенный
  процесс продолжает идти по своей.

Исключение одно - координаты узлов: их можно двигать и в опубликованной
версии, потому что расположение схемы на экране ничего не решает.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError
from app.models.workflow import (
    WorkflowInstance,
    WorkflowStage,
    WorkflowTemplate,
    WorkflowTransition,
    WorkflowVersion,
)
from app.schemas.workflow import GraphWrite, LayoutWrite


async def get_template(session: AsyncSession, template_id: uuid.UUID) -> WorkflowTemplate:
    template = await session.get(WorkflowTemplate, template_id)
    if template is None:
        raise NotFoundError("Шаблон процесса не найден")
    return template


async def get_version(session: AsyncSession, version_id: uuid.UUID) -> WorkflowVersion:
    statement = (
        select(WorkflowVersion)
        .where(WorkflowVersion.id == version_id)
        .options(
            selectinload(WorkflowVersion.stages),
            selectinload(WorkflowVersion.transitions),
        )
        # Версию только что правили: без populate_existing в ответ уйдёт
        # то, что осталось в сессии от прошлого чтения.
        .execution_options(populate_existing=True)
    )
    version = (await session.execute(statement)).scalar_one_or_none()
    if version is None:
        raise NotFoundError("Версия шаблона не найдена")
    return version


def ensure_draft(version: WorkflowVersion) -> None:
    if version.is_published:
        raise ConflictError(
            "Опубликованную версию менять нельзя: по ней идут запущенные процессы. "
            "Создайте новую версию шаблона."
        )


async def create_template(
    session: AsyncSession, name: str, description: str | None, graph: GraphWrite | None
) -> tuple[WorkflowTemplate, WorkflowVersion]:
    existing = await session.scalar(
        select(WorkflowTemplate).where(WorkflowTemplate.name == name)
    )
    if existing is not None:
        raise ConflictError(f"Шаблон «{name}» уже есть")

    template = WorkflowTemplate(name=name, description=description)
    session.add(template)
    await session.flush()

    version = WorkflowVersion(template_id=template.id, version_number=1)
    session.add(version)
    await session.flush()

    if graph is not None:
        await replace_graph(session, version, graph)
    return template, version


async def create_version(
    session: AsyncSession,
    template: WorkflowTemplate,
    from_version_id: uuid.UUID | None,
    copy_graph: bool,
) -> WorkflowVersion:
    """Новая версия-черновик, по умолчанию - копия последней существующей."""
    last_number = (
        await session.scalar(
            select(func.max(WorkflowVersion.version_number)).where(
                WorkflowVersion.template_id == template.id
            )
        )
        or 0
    )

    source: WorkflowVersion | None = None
    if copy_graph:
        source_id = from_version_id
        if source_id is None:
            source_id = await session.scalar(
                select(WorkflowVersion.id)
                .where(WorkflowVersion.template_id == template.id)
                .order_by(WorkflowVersion.version_number.desc())
                .limit(1)
            )
        if source_id is not None:
            source = await get_version(session, source_id)
            if source.template_id != template.id:
                raise ConflictError("Версия принадлежит другому шаблону")

    version = WorkflowVersion(template_id=template.id, version_number=last_number + 1)
    session.add(version)
    await session.flush()

    if source is not None:
        await _copy_graph(session, source, version)
    return version


async def _copy_graph(
    session: AsyncSession, source: WorkflowVersion, target: WorkflowVersion
) -> None:
    stage_by_code: dict[str, WorkflowStage] = {}
    for stage in source.stages:
        copy = WorkflowStage(
            workflow_version_id=target.id,
            code=stage.code,
            name=stage.name,
            description=stage.description,
            sort_order=stage.sort_order,
            is_optional=stage.is_optional,
            is_final=stage.is_final,
            sla_days=stage.sla_days,
            layout_x=stage.layout_x,
            layout_y=stage.layout_y,
        )
        session.add(copy)
        stage_by_code[stage.code] = copy
    await session.flush()

    code_by_id = {stage.id: stage.code for stage in source.stages}
    for transition in source.transitions:
        from_code = code_by_id.get(transition.from_stage_id)
        to_code = code_by_id.get(transition.to_stage_id)
        if from_code is None or to_code is None:  # pragma: no cover - битая схема
            continue
        session.add(
            WorkflowTransition(
                workflow_version_id=target.id,
                from_stage_id=stage_by_code[from_code].id,
                to_stage_id=stage_by_code[to_code].id,
                name=transition.name,
                is_backward=transition.is_backward,
                requires_comment=transition.requires_comment,
            )
        )
    await session.flush()


def _check_graph(graph: GraphWrite) -> None:
    codes = [stage.code for stage in graph.stages]
    duplicates = {code for code in codes if codes.count(code) > 1}
    if duplicates:
        raise ConflictError(f"Коды этапов повторяются: {', '.join(sorted(duplicates))}")

    known = set(codes)
    for transition in graph.transitions:
        missing = {transition.from_code, transition.to_code} - known
        if missing:
            raise ConflictError(
                f"Переход ссылается на несуществующий этап: {', '.join(sorted(missing))}"
            )
        if transition.from_code == transition.to_code:
            raise ConflictError(f"Переход этапа «{transition.from_code}» сам в себя")

    pairs = [(item.from_code, item.to_code) for item in graph.transitions]
    repeated = {pair for pair in pairs if pairs.count(pair) > 1}
    if repeated:
        raise ConflictError("Один и тот же переход задан дважды")

    if not any(stage.is_final for stage in graph.stages):
        raise ConflictError(
            "В схеме нет завершающего этапа: процесс по ней невозможно закончить"
        )


async def replace_graph(
    session: AsyncSession, version: WorkflowVersion, graph: GraphWrite
) -> WorkflowVersion:
    """Заменяет схему черновика целиком - так её сохраняет редактор."""
    ensure_draft(version)
    _check_graph(graph)

    # Версия могла быть только что создана: связи подгружаем явно, иначе
    # обращение к ним попытается сходить в базу в неподходящий момент.
    await session.refresh(version, ["stages", "transitions"])
    for transition in list(version.transitions):
        await session.delete(transition)
    for stage in list(version.stages):
        await session.delete(stage)
    await session.flush()

    stage_by_code: dict[str, WorkflowStage] = {}
    for index, item in enumerate(graph.stages):
        stage = WorkflowStage(
            workflow_version_id=version.id,
            code=item.code,
            name=item.name,
            description=item.description,
            sort_order=item.sort_order if item.sort_order is not None else (index + 1) * 10,
            is_optional=item.is_optional,
            is_final=item.is_final,
            sla_days=item.sla_days,
            # Без координат этап раскладывает клиент - по порядку этапов.
            layout_x=item.layout_x,
            layout_y=item.layout_y,
        )
        session.add(stage)
        stage_by_code[item.code] = stage
    await session.flush()

    for item in graph.transitions:
        session.add(
            WorkflowTransition(
                workflow_version_id=version.id,
                from_stage_id=stage_by_code[item.from_code].id,
                to_stage_id=stage_by_code[item.to_code].id,
                name=item.name,
                is_backward=item.is_backward,
                requires_comment=item.requires_comment,
            )
        )
    await session.flush()
    return await get_version(session, version.id)


async def save_layout(
    session: AsyncSession, version: WorkflowVersion, layout: LayoutWrite
) -> WorkflowVersion:
    """Сохраняет расположение узлов. Работает и для опубликованной версии."""
    by_id = {stage.id: stage for stage in version.stages}
    for item in layout.stages:
        stage = by_id.get(item.stage_id)
        if stage is None:
            raise NotFoundError("Этап не найден в этой версии шаблона")
        stage.layout_x = item.layout_x
        stage.layout_y = item.layout_y
    await session.flush()
    return version


async def publish(session: AsyncSession, version: WorkflowVersion) -> WorkflowVersion:
    if version.is_published:
        raise ConflictError("Версия уже опубликована")
    if not version.stages:
        raise ConflictError("В версии нет этапов")
    if not any(stage.is_final for stage in version.stages):
        raise ConflictError("В версии нет завершающего этапа")

    version.published_at = datetime.now(UTC)
    await session.flush()
    return version


async def delete_version(session: AsyncSession, version: WorkflowVersion) -> None:
    """Удалить можно только черновик, по которому не запускали процессы."""
    ensure_draft(version)
    used = await session.scalar(
        select(func.count())
        .select_from(WorkflowInstance)
        .where(WorkflowInstance.workflow_version_id == version.id)
    )
    if used:
        raise ConflictError("По этой версии есть запущенные процессы")
    await session.delete(version)
