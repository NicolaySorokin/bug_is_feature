"""Редактирование шаблонов рабочих процессов.

Этапы и переходы правятся только в черновике. Публикация делает черновик
действующей версией, прежняя становится устаревшей, начатые процессы идут
по своей версии. Отката нет, новая версия создаётся копией старой.
Перед публикацией граф проверяется целиком.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError
from app.enums import InteractionOutcome, WorkflowVersionStatus
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
        # Версию только что правили: без populate_existing вернётся старое из сессии.
        .execution_options(populate_existing=True)
    )
    version = (await session.execute(statement)).scalar_one_or_none()
    if version is None:
        raise NotFoundError("Версия шаблона не найдена")
    return version


def ensure_draft(version: WorkflowVersion) -> None:
    if not version.is_draft:
        raise ConflictError(
            "Опубликованную версию менять нельзя: по ней идут взаимодействия. "
            "Создайте новую версию шаблона - копию этой."
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
    """Новая версия-черновик, по умолчанию копия последней."""
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
            is_initial=stage.is_initial,
            is_optional=stage.is_optional,
            is_final=stage.is_final,
            outcome=stage.outcome,
            sla_days=stage.sla_days,
            required_documents=list(stage.required_documents or []),
            program_status_on_enter=stage.program_status_on_enter,
            product_status_on_enter=stage.product_status_on_enter,
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
        if from_code is None or to_code is None:  # pragma: no cover (битая схема)
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


def _check_references(graph: GraphWrite) -> None:
    """Проверки, без которых схему не сохранить даже черновиком."""
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


def validate_graph(
    stages: list[tuple[str, str, bool, bool, str | None]],
    transitions: list[tuple[str, str, bool]],
) -> list[str]:
    """Проверка графа перед публикацией. Возвращает список проблем.

    stages: (код, название, стартовый, финальный, результат).
    transitions: (откуда, куда, возврат назад).
    """
    problems: list[str] = []
    names = {code: name for code, name, *_ in stages}
    initial = [code for code, _, is_initial, _, _ in stages if is_initial]
    finals = {code for code, _, _, is_final, _ in stages if is_final}

    if len(initial) != 1:
        problems.append(
            "Стартовый этап должен быть ровно один"
            + (f" (сейчас: {len(initial)})" if initial else " - отметьте его")
        )
    if not finals:
        problems.append("Нет финального этапа: процесс по схеме невозможно закончить")
    for _code, name, _, is_final, outcome in stages:
        if is_final and outcome is None:
            problems.append(f"У финального этапа «{name}» не задан результат")
        if not is_final and outcome is not None:
            problems.append(
                f"Результат задаётся только финальному этапу, а «{name}» не финальный"
            )

    outgoing: dict[str, list[tuple[str, bool]]] = {code: [] for code in names}
    for source, target, backward in transitions:
        outgoing.setdefault(source, []).append((target, backward))

    for code in finals:
        if outgoing.get(code):
            problems.append(f"Из финального этапа «{names[code]}» не должно быть переходов")
    for code in names:
        if code not in finals and not any(True for _ in outgoing.get(code, [])):
            problems.append(f"Этап «{names[code]}» - тупик: из него нет переходов")
        forward_less = all(backward for _, backward in outgoing.get(code, []))
        if code not in finals and outgoing.get(code) and forward_less:
            problems.append(
                f"Из этапа «{names[code]}» можно только вернуться назад - нет пути вперёд"
            )

    if len(initial) == 1:
        seen = {initial[0]}
        queue = [initial[0]]
        while queue:
            current = queue.pop()
            for target, _ in outgoing.get(current, []):
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
        unreachable = [names[code] for code in names if code not in seen]
        if unreachable:
            problems.append("Недостижимые этапы: " + ", ".join(sorted(unreachable)))
        if not seen & finals:
            problems.append("Из стартового этапа не дойти ни до одного финального")

    # Циклы допустимы только через переходы-возвраты.
    forward: dict[str, list[str]] = {code: [] for code in names}
    for source, target, backward in transitions:
        if not backward:
            forward.setdefault(source, []).append(target)
    state: dict[str, int] = {}

    def has_cycle(node: str) -> bool:
        state[node] = 1
        for target in forward.get(node, []):
            if state.get(target) == 1:
                return True
            if state.get(target) is None and has_cycle(target):
                return True
        state[node] = 2
        return False

    if any(state.get(code) is None and has_cycle(code) for code in names):
        problems.append(
            "В схеме есть цикл из переходов вперёд: повтор этапов оформляется "
            "переходом-возвратом"
        )
    return problems


def _graph_problems_of_version(version: WorkflowVersion) -> list[str]:
    code_by_id = {stage.id: stage.code for stage in version.stages}
    return validate_graph(
        [
            (stage.code, stage.name, stage.is_initial, stage.is_final, stage.outcome)
            for stage in version.stages
        ],
        [
            (code_by_id[t.from_stage_id], code_by_id[t.to_stage_id], t.is_backward)
            for t in version.transitions
            if t.from_stage_id in code_by_id and t.to_stage_id in code_by_id
        ],
    )


async def replace_graph(
    session: AsyncSession, version: WorkflowVersion, graph: GraphWrite
) -> WorkflowVersion:
    """Заменяет схему черновика целиком, так её сохраняет редактор."""
    ensure_draft(version)
    _check_references(graph)

    # Версия могла быть только что создана, поэтому связи подгружаем явно.
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
            is_initial=item.is_initial,
            is_optional=item.is_optional,
            is_final=item.is_final,
            outcome=(item.outcome or InteractionOutcome.SUCCESSFUL) if item.is_final else None,
            sla_days=item.sla_days,
            required_documents=[str(value) for value in item.required_documents],
            program_status_on_enter=item.program_status_on_enter,
            product_status_on_enter=item.product_status_on_enter,
            # Без координат этапы раскладывает клиент по порядку.
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
    """Черновик становится действующей версией шаблона.

    Прежняя действующая становится устаревшей, а если открытых взаимодействий
    по ней нет, сразу выводится из использования.
    """
    if not version.is_draft:
        raise ConflictError("Версия уже опубликована")
    if not version.stages:
        raise ConflictError("В версии нет этапов")
    problems = _graph_problems_of_version(version)
    if problems:
        raise ConflictError(
            "Схему нельзя опубликовать: " + "; ".join(problems),
            details={"problems": problems},
        )

    now = datetime.now(UTC)
    previous = await session.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.template_id == version.template_id,
            WorkflowVersion.status == WorkflowVersionStatus.ACTIVE,
        )
    )
    if previous is not None:
        previous.status = WorkflowVersionStatus.DEPRECATED
        previous.deprecated_at = now
        # Индекс «одна действующая версия» проверяется сразу, поэтому сначала
        # снимаем статус с прежней.
        await session.flush()
    version.status = WorkflowVersionStatus.ACTIVE
    version.published_at = now
    await session.flush()
    if previous is not None:
        # Импорт здесь, чтобы не было циклической зависимости.
        from app.services.workflow import maybe_retire

        await maybe_retire(session, previous.id)
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
