"""Взаимодействия с вузами: реестр, карточка, ход процесса, состав и договор.

Взаимодействие - экземпляр рабочего процесса (раздел 1 «Решений по
бизнес-модели»). Договор - необязательный блок внутри: не больше одного
на взаимодействие.

Права (раздел 12): менеджер заводит взаимодействие только в своей области
и сам становится ответственным; руководитель заводит и назначает
ответственного менеджера; администратор без бизнес-роли взаимодействий
не заводит и не меняет. Начатое взаимодействие не удаляется, а отменяется
с причиной.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import APIRouter, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentUserDep,
    InteractionDep,
    PaginationDep,
    PrincipalDep,
    SessionDep,
    WritableInteractionDep,
)
from app.core.errors import AppError, ConflictError, ErrorCode, ForbiddenError, NotFoundError
from app.core.security import Principal
from app.enums import (
    ContractStatus,
    DataScope,
    InteractionOutcome,
    InteractionSource,
    InteractionStatus,
    Role,
    UniversityStatus,
)
from app.models.content import Comment
from app.models.contract import Contract, License
from app.models.interaction import (
    InteractionContact,
    InteractionProduct,
    InteractionProgram,
)
from app.models.university import University, UniversityContact
from app.models.user import User
from app.models.workflow import WorkflowEvent, WorkflowInstance
from app.schemas.common import Page
from app.schemas.contract import ContractRead, ContractWrite
from app.schemas.interaction import (
    CancelRequest,
    InteractionContactRead,
    InteractionContactWrite,
    InteractionCreate,
    InteractionDetail,
    InteractionListItem,
    InteractionProductRead,
    InteractionProgramRead,
    InteractionUpdate,
    ProductAdd,
    ProductStatusUpdate,
    ProgramAdd,
    ProgramProductLinkWrite,
    ProgramStatusUpdate,
)
from app.schemas.license import LicenseCreate, LicenseRead
from app.schemas.workflow import BlockRequest, InstanceView, SkipRequest, TransitionRequest
from app.services import access, app_settings, interactions, licenses
from app.services import workflow as workflow_service
from app.services.access import Action
from app.services.labels import (
    PRODUCT_STATUS_LABELS,
    PROGRAM_STATUS_LABELS,
    label,
)
from app.services.workflow_view import build_view

router = APIRouter(prefix="/interactions", tags=["interactions"])


class InteractionOrder(StrEnum):
    UPDATED = "updated"  # сначала недавно изменённые
    CREATED = "created"  # сначала новые
    UNIVERSITY = "university"
    ATTENTION = "attention"  # заблокированные, затем по сроку этапа


def _conflict(exc: workflow_service.WorkflowError) -> ConflictError:
    """Нарушение правил процесса клиент отличает по коду workflow_rule_violated."""
    return ConflictError(str(exc), code=ErrorCode.WORKFLOW_RULE_VIOLATED, details=exc.details)


async def _default_sla(session: AsyncSession) -> int:
    return (await app_settings.load(session))["alert_default_sla_days"]


async def _assignable_manager(
    session: AsyncSession, principal: Principal, user: User, manager_id: uuid.UUID
) -> User:
    """Кого руководитель может назначить ответственным: менеджера своей
    команды (или любого - если его область «все»), либо себя, если он и сам
    менеджер."""
    manager = await session.get(User, manager_id)
    if manager is None or not manager.is_active:
        raise NotFoundError("Сотрудник для назначения ответственным не найден")
    if Role.MANAGER not in (manager.roles or []):
        raise ConflictError("Ответственным назначается сотрудник с ролью «Менеджер»")
    if manager.id == user.id:
        return manager
    scope = access.effective_scope(principal, user)
    if scope is not DataScope.ALL and manager.head_id != user.id:
        raise ForbiddenError("Назначать можно менеджеров своей команды")
    return manager


async def _rights(
    session: AsyncSession, instance: WorkflowInstance, principal: Principal, user: User
) -> dict[str, bool]:
    open_ = instance.status in workflow_service.OPEN
    work = access.can(principal, user, Action.WORK_INTERACTION)
    head = access.can(principal, user, Action.ASSIGN_RESPONSIBLE)
    cancel = access.can(principal, user, Action.CANCEL_INTERACTION) and (
        head or instance.manager_id == user.id
    )
    return {
        "can_edit": work,
        "can_assign": head and open_,
        "can_cancel": cancel and open_,
        "can_delete": (head or instance.created_by_id == user.id)
        and work
        and await interactions.deletable(session, instance),
    }


async def _detail(
    session: AsyncSession, interaction_id: uuid.UUID, principal: Principal, user: User
) -> InteractionDetail:
    instance = await interactions.load(session, interaction_id)
    missing: list[str] = []
    if instance.current_stage is not None and instance.status in (
        InteractionStatus.IN_PROGRESS,
        InteractionStatus.BLOCKED,
    ):
        missing = await workflow_service.missing_documents(
            session, instance, instance.current_stage
        )
    return await interactions.detail(
        session,
        instance,
        await _default_sla(session),
        missing,
        await _rights(session, instance, principal, user),
    )


def _order(statement: Select, order: InteractionOrder) -> Select:
    if order is InteractionOrder.CREATED:
        return statement.order_by(WorkflowInstance.created_at.desc(), WorkflowInstance.id)
    if order is InteractionOrder.UNIVERSITY:
        return statement.join(
            University, University.id == WorkflowInstance.university_id
        ).order_by(
            func.coalesce(University.short_name, University.name), WorkflowInstance.created_at
        )
    if order is InteractionOrder.ATTENTION:
        return statement.order_by(
            (WorkflowInstance.status != InteractionStatus.BLOCKED),
            WorkflowInstance.current_stage_started_at.asc().nullslast(),
            WorkflowInstance.id,
        )
    return statement.order_by(WorkflowInstance.updated_at.desc(), WorkflowInstance.id)


@router.get(
    "",
    response_model=Page[InteractionListItem],
    summary="Реестр взаимодействий",
    description=(
        "Видны взаимодействия в области данных сотрудника: свои (менеджер), "
        "команды (руководитель), все или никаких (администратор без "
        "бизнес-доступа). Номер договора - один из поисковых атрибутов."
    ),
)
async def list_interactions(
    session: SessionDep,
    pagination: PaginationDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
    university_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
    unassigned: bool = Query(default=False, description="Только без ответственного"),
    status_filter: list[InteractionStatus] = Query(default=[], alias="status"),
    outcome: InteractionOutcome | None = None,
    source: InteractionSource | None = None,
    direction_id: uuid.UUID | None = None,
    program_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    stage: str | None = Query(default=None, description="Название текущего этапа"),
    contract_status: ContractStatus | None = None,
    has_contract: bool | None = Query(default=None, description="Есть ли договор"),
    contract_id: uuid.UUID | None = None,
    overdue: bool = Query(default=False, description="Только с просроченным этапом"),
    search: str | None = Query(default=None, description="Название, вуз, номер договора"),
    order: InteractionOrder = InteractionOrder.UPDATED,
) -> Page[InteractionListItem]:
    default_sla = await _default_sla(session)
    filters = {
        "university_id": university_id,
        "manager_id": manager_id,
        "unassigned": unassigned,
        "statuses": [item.value for item in status_filter],
        "outcome": outcome,
        "source": source,
        "direction_id": direction_id,
        "program_id": program_id,
        "product_id": product_id,
        "stage_name": stage,
        "contract_status": contract_status,
        "has_contract": has_contract,
        "contract_id": contract_id,
        "overdue_only": overdue,
        "default_sla": default_sla,
        "search": search,
    }

    def scoped(statement: Select) -> Select:
        return access.apply_interaction_scope(
            interactions.apply_filters(statement, **filters), principal, user
        )

    total = await session.scalar(scoped(select(func.count()).select_from(WorkflowInstance)))
    rows = list(
        (
            await session.execute(
                _order(scoped(select(WorkflowInstance)), order)
                .options(*interactions.list_options())
                .limit(pagination.limit)
                .offset(pagination.offset)
            )
        ).scalars()
    )
    actions = await interactions.transitions_by_stage(
        session, {row.current_stage_id for row in rows if row.current_stage_id}
    )
    return Page(
        items=[interactions.list_item(row, actions, default_sla) for row in rows],
        total=total or 0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "",
    response_model=InteractionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Новое взаимодействие",
    description=(
        "Менеджер заводит взаимодействие по вузу своей области и становится "
        "ответственным. Руководитель может назначить ответственного менеджера. "
        "Без флага start взаимодействие остаётся черновиком без процесса."
    ),
)
async def create_interaction(
    payload: InteractionCreate,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> InteractionDetail:
    access.ensure(
        principal,
        user,
        Action.CREATE_INTERACTION,
        "Заводить взаимодействия может менеджер или руководитель",
    )
    university = await session.get(University, payload.university_id)
    if university is None:
        raise NotFoundError("Вуз не найден")
    if university.status != UniversityStatus.CONFIRMED:
        raise ConflictError(
            "Вуз ещё не подтверждён или в архиве: взаимодействие заводится "
            "только с подтверждённым вузом"
        )

    head = access.can(principal, user, Action.ASSIGN_RESPONSIBLE)
    manager_id: uuid.UUID | None = None
    if head:
        if payload.manager_id is not None:
            manager_id = (
                await _assignable_manager(session, principal, user, payload.manager_id)
            ).id
        elif university.manager_id is not None:
            # Менеджер по умолчанию - подсказка, а не требование: если этого
            # менеджера руководитель назначить не может (другая команда, нет
            # роли, отключён), взаимодействие уходит в очередь назначения.
            try:
                manager_id = (
                    await _assignable_manager(session, principal, user, university.manager_id)
                ).id
            except (ForbiddenError, ConflictError, NotFoundError):
                manager_id = None
    else:
        if payload.manager_id not in (None, user.id):
            raise ForbiddenError(
                "Назначить ответственным другого сотрудника может руководитель"
            )
        if not await access.can_see_university(session, university.id, principal, user):
            raise ForbiddenError(
                "Вуз вне вашей области данных: попросите руководителя завести "
                "взаимодействие или открыть вам доступ к вузу"
            )
        manager_id = user.id

    try:
        if payload.template_id is not None:
            version = await workflow_service.active_version(session, payload.template_id)
        else:
            template = await workflow_service.default_template(session)
            if template is None:
                raise workflow_service.WorkflowError(
                    "Нет шаблона процесса с действующей версией"
                )
            version = await workflow_service.active_version(session, template.id)
        instance = await workflow_service.create_interaction(
            session,
            university_id=university.id,
            version=version,
            user=user,
            manager_id=manager_id,
            title=payload.title,
            comment=payload.comment,
            source=InteractionSource.MANUAL,
        )
        for program_id in dict.fromkeys(payload.program_ids):
            await interactions.add_program(session, instance, program_id, "not_started")
        if payload.start:
            await workflow_service.start_instance(session, instance, user)
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc
    return await _detail(session, instance.id, principal, user)


@router.get(
    "/{interaction_id}", response_model=InteractionDetail, summary="Карточка взаимодействия"
)
async def read_interaction(
    interaction: InteractionDep,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> InteractionDetail:
    return await _detail(session, interaction.id, principal, user)


@router.patch(
    "/{interaction_id}",
    response_model=InteractionDetail,
    summary="Изменить взаимодействие",
    description="Сменить или снять ответственного (manager_id) может только руководитель.",
)
async def update_interaction(
    interaction: WritableInteractionDep,
    payload: InteractionUpdate,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> InteractionDetail:
    data = payload.model_dump(exclude_unset=True)
    if "manager_id" in data and data["manager_id"] != interaction.manager_id:
        access.ensure(
            principal,
            user,
            Action.ASSIGN_RESPONSIBLE,
            "Менять ответственного может только руководитель",
        )
        if interaction.status not in workflow_service.OPEN:
            raise ConflictError("Взаимодействие закрыто: ответственный уже не меняется")
        new_manager = (
            await _assignable_manager(session, principal, user, data["manager_id"])
            if data["manager_id"] is not None
            else None
        )
        previous = (
            await session.get(User, interaction.manager_id) if interaction.manager_id else None
        )
        await workflow_service.reassign(session, interaction, user, new_manager, previous)
    if "title" in data:
        interaction.title = data["title"]
    if "comment" in data:
        interaction.comment = data["comment"]
    await session.flush()
    return await _detail(session, interaction.id, principal, user)


@router.delete(
    "/{interaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить ошибочный черновик",
    description=(
        "Удаляется только черновик без договора, файлов, комментариев и движения "
        "по процессу. Начатое взаимодействие отменяют с причиной."
    ),
)
async def delete_interaction(
    interaction: WritableInteractionDep,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> None:
    rights = await _rights(session, interaction, principal, user)
    if not rights["can_delete"]:
        raise ConflictError(
            "Удалить можно только ошибочно заведённый черновик без зависимостей - "
            "начатое взаимодействие отмените с причиной"
        )
    await session.delete(interaction)


# --- Ход процесса ----------------------------------------------------------------


async def _view(session: AsyncSession, instance: WorkflowInstance) -> InstanceView:
    fresh = await workflow_service.get_instance(session, instance.id)
    assert fresh is not None  # noqa: S101 - взаимодействие только что прочитано
    return await build_view(session, fresh)


@router.get(
    "/{interaction_id}/workflow", response_model=InstanceView, summary="Схема и история"
)
async def read_workflow(interaction: InteractionDep, session: SessionDep) -> InstanceView:
    return await _view(session, interaction)


@router.post(
    "/{interaction_id}/start",
    response_model=InstanceView,
    summary="Запустить процесс",
    description="Черновик переходит в работу на стартовом этапе действующей версии шаблона.",
)
async def start(
    interaction: WritableInteractionDep, session: SessionDep, user: CurrentUserDep
) -> InstanceView:
    try:
        await workflow_service.start_instance(session, interaction, user)
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc
    return await _view(session, interaction)


@router.post(
    "/{interaction_id}/transition",
    response_model=InstanceView,
    summary="Перейти на разрешённый этап",
    description=(
        "С этапа, для которого в шаблоне заданы обязательные документы, вперёд "
        "не уйти, пока они не загружены (details.missing_documents). Переход на "
        "финальный этап без успеха (например, «Отказ») требует причину."
    ),
)
async def transition(
    interaction: WritableInteractionDep,
    payload: TransitionRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> InstanceView:
    try:
        version = await workflow_service.load_version(session, interaction.workflow_version_id)
        await workflow_service.move(
            session,
            interaction,
            version,
            payload.to_stage_id,
            user,
            comment=payload.comment,
            closure_reason=payload.closure_reason,
        )
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc
    return await _view(session, interaction)


@router.post(
    "/{interaction_id}/skip",
    response_model=InstanceView,
    summary="Пропустить этап",
    description=(
        "Менеджер пропускает только необязательный этап, руководитель - любой: "
        "это исключение, причина обязательна и остаётся в истории."
    ),
)
async def skip_stage(
    interaction: WritableInteractionDep,
    payload: SkipRequest,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> InstanceView:
    try:
        version = await workflow_service.load_version(session, interaction.workflow_version_id)
        await workflow_service.move(
            session,
            interaction,
            version,
            payload.to_stage_id,
            user,
            comment=payload.reason,
            skip=True,
            may_skip_required=access.can(principal, user, Action.SKIP_ANY_STAGE),
        )
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc
    return await _view(session, interaction)


@router.post("/{interaction_id}/block", response_model=InstanceView, summary="Заблокировать")
async def block(
    interaction: WritableInteractionDep,
    payload: BlockRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> InstanceView:
    try:
        await workflow_service.set_blocked(session, interaction, user, payload.reason, True)
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc
    return await _view(session, interaction)


@router.post(
    "/{interaction_id}/unblock", response_model=InstanceView, summary="Снять блокировку"
)
async def unblock(
    interaction: WritableInteractionDep,
    payload: BlockRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> InstanceView:
    try:
        await workflow_service.set_blocked(session, interaction, user, payload.reason, False)
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc
    return await _view(session, interaction)


@router.post(
    "/{interaction_id}/cancel",
    response_model=InstanceView,
    summary="Отменить взаимодействие",
    description=(
        "Досрочное прекращение с обязательной причиной. Менеджер отменяет свои "
        "взаимодействия, руководитель - любые в своей области."
    ),
)
async def cancel(
    interaction: WritableInteractionDep,
    payload: CancelRequest,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> InstanceView:
    if interaction.status not in workflow_service.OPEN:
        raise ConflictError("Взаимодействие уже закрыто")
    rights = await _rights(session, interaction, principal, user)
    if not rights["can_cancel"]:
        raise ForbiddenError(
            "Отменить взаимодействие может его ответственный или руководитель"
        )
    try:
        await workflow_service.cancel(
            session, interaction, user, payload.reason, payload.comment
        )
    except workflow_service.WorkflowError as exc:
        raise _conflict(exc) from exc
    return await _view(session, interaction)


# --- Программы и продукты ------------------------------------------------------------


async def _note(
    session: AsyncSession, instance: WorkflowInstance, user: User, text: str
) -> None:
    """Ручное изменение в обход процесса - комментарием в карточке и истории."""
    event_id = await session.scalar(
        select(WorkflowEvent.id)
        .where(WorkflowEvent.workflow_instance_id == instance.id)
        .order_by(WorkflowEvent.created_at.desc())
        .limit(1)
    )
    session.add(
        Comment(
            workflow_instance_id=instance.id,
            workflow_event_id=event_id,
            author_id=user.id,
            text=text,
        )
    )
    await session.flush()


@router.post(
    "/{interaction_id}/programs",
    response_model=InteractionProgramRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить ИТ-программу",
    description="Выбрать можно только активную программу справочника.",
)
async def add_program(
    interaction: WritableInteractionDep, payload: ProgramAdd, session: SessionDep
) -> InteractionProgramRead:
    link = await interactions.add_program(
        session, interaction, payload.program_id, payload.implementation_status
    )
    await session.refresh(link, ["program"])
    return InteractionProgramRead.model_validate(link)


@router.patch(
    "/{interaction_id}/programs/{link_id}",
    response_model=InteractionProgramRead,
    summary="Изменить статус внедрения программы вручную",
    description=(
        "Обычно статус ставит этап процесса. Ручное изменение - исключение: "
        "комментарий обязателен, он сохраняется в карточке, а изменение - в журнале."
    ),
)
async def update_program(
    interaction: WritableInteractionDep,
    link_id: uuid.UUID,
    payload: ProgramStatusUpdate,
    session: SessionDep,
    user: CurrentUserDep,
) -> InteractionProgramRead:
    link = await session.get(InteractionProgram, link_id)
    if link is None or link.workflow_instance_id != interaction.id:
        raise NotFoundError("Программа не найдена в составе взаимодействия")
    if payload.implementation_status != link.implementation_status:
        if not (payload.comment or "").strip():
            raise AppError(
                "Ручное изменение статуса - исключение: укажите причину",
                code=ErrorCode.VALIDATION_ERROR,
            )
        await session.refresh(link, ["program"])
        await _note(
            session,
            interaction,
            user,
            f"Статус программы «{link.program.name}»: "
            f"{label(PROGRAM_STATUS_LABELS, link.implementation_status)} → "
            f"{label(PROGRAM_STATUS_LABELS, payload.implementation_status)}. "
            f"Причина: {payload.comment}",
        )
        link.implementation_status = payload.implementation_status
        await session.flush()
    await session.refresh(link, ["program"])
    return InteractionProgramRead.model_validate(link)


@router.delete(
    "/{interaction_id}/programs/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Убрать программу",
    description="Программу со связанными продуктами убрать нельзя: сначала уберите связи.",
)
async def remove_program(
    interaction: WritableInteractionDep, link_id: uuid.UUID, session: SessionDep
) -> None:
    await interactions.remove_program(session, interaction, link_id)


@router.post(
    "/{interaction_id}/products",
    response_model=InteractionProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить ИТ-продукт в программы взаимодействия",
    description=(
        "Продукт добавляется сразу со связью хотя бы с одной программой "
        "взаимодействия. Связь вне справочного соответствия - исключение "
        "руководителя с комментарием."
    ),
)
async def add_product(
    interaction: WritableInteractionDep,
    payload: ProductAdd,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> InteractionProductRead:
    link = await interactions.add_product(
        session,
        interaction,
        payload.product_id,
        payload.program_link_ids,
        payload.transfer_status,
        exception_comment=payload.exception_comment,
        may_make_exception=access.can(principal, user, Action.PRODUCT_EXCEPTION),
        user=user,
    )
    await session.refresh(link, ["product", "licenses"])
    return InteractionProductRead.model_validate(link)


@router.patch(
    "/{interaction_id}/products/{link_id}",
    response_model=InteractionProductRead,
    summary="Изменить статус передачи продукта вручную",
)
async def update_product(
    interaction: WritableInteractionDep,
    link_id: uuid.UUID,
    payload: ProductStatusUpdate,
    session: SessionDep,
    user: CurrentUserDep,
) -> InteractionProductRead:
    link = await session.get(InteractionProduct, link_id)
    if link is None or link.workflow_instance_id != interaction.id:
        raise NotFoundError("Продукт не найден в составе взаимодействия")
    if payload.transfer_status != link.transfer_status:
        if not (payload.comment or "").strip():
            raise AppError(
                "Ручное изменение статуса - исключение: укажите причину",
                code=ErrorCode.VALIDATION_ERROR,
            )
        await session.refresh(link, ["product"])
        await _note(
            session,
            interaction,
            user,
            f"Статус передачи продукта «{link.product.name}»: "
            f"{label(PRODUCT_STATUS_LABELS, link.transfer_status)} → "
            f"{label(PRODUCT_STATUS_LABELS, payload.transfer_status)}. "
            f"Причина: {payload.comment}",
        )
        link.transfer_status = payload.transfer_status
        await session.flush()
    await session.refresh(link, ["product", "licenses"])
    return InteractionProductRead.model_validate(link)


@router.delete(
    "/{interaction_id}/products/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Убрать продукт",
    description=(
        "Вместе с продуктом уходят его связи с программами. Продукт с лицензиями не убрать."
    ),
)
async def remove_product(
    interaction: WritableInteractionDep, link_id: uuid.UUID, session: SessionDep
) -> None:
    await interactions.remove_product(session, interaction, link_id)


@router.put(
    "/{interaction_id}/links",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Связать продукт с программой взаимодействия",
)
async def put_link(
    interaction: WritableInteractionDep,
    payload: ProgramProductLinkWrite,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> None:
    product_link = await session.get(InteractionProduct, payload.product_link_id)
    if product_link is None or product_link.workflow_instance_id != interaction.id:
        raise NotFoundError("Продукт не найден в составе взаимодействия")
    program_link = await session.get(InteractionProgram, payload.program_link_id)
    if program_link is None or program_link.workflow_instance_id != interaction.id:
        raise NotFoundError("Программа не найдена в составе взаимодействия")
    await interactions.link_product(
        session,
        interaction,
        product_link,
        [program_link],
        exception_comment=payload.exception_comment,
        may_make_exception=access.can(principal, user, Action.PRODUCT_EXCEPTION),
        user=user,
    )


@router.delete(
    "/{interaction_id}/links",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Убрать связь продукта с программой",
    description="Продукт, у которого не осталось программ, уходит из состава.",
)
async def delete_link(
    interaction: WritableInteractionDep,
    session: SessionDep,
    program_link_id: uuid.UUID,
    product_link_id: uuid.UUID,
) -> None:
    await interactions.unlink(session, interaction, program_link_id, product_link_id)


# --- Ответственные от вуза ------------------------------------------------------------


@router.get(
    "/{interaction_id}/contacts",
    response_model=list[InteractionContactRead],
    summary="Ответственные от вуза по взаимодействию",
)
async def list_contacts(
    interaction: InteractionDep, session: SessionDep
) -> list[InteractionContactRead]:
    result = await session.execute(
        select(InteractionContact)
        .where(InteractionContact.workflow_instance_id == interaction.id)
        .options(selectinload(InteractionContact.contact))
    )
    items = [InteractionContactRead.model_validate(row) for row in result.scalars()]
    return sorted(items, key=lambda item: (not item.is_primary, item.contact.full_name))


@router.put(
    "/{interaction_id}/contacts",
    response_model=InteractionContactRead,
    summary="Назначить контакт вуза ответственным по взаимодействию",
    description=(
        "Контакт берётся из контактных лиц того же вуза: один человек не "
        "дублируется для каждого взаимодействия. Повторный вызов обновляет роль "
        "и признак основного контакта."
    ),
)
async def put_contact(
    interaction: WritableInteractionDep,
    payload: InteractionContactWrite,
    session: SessionDep,
) -> InteractionContactRead:
    contact = await session.get(UniversityContact, payload.contact_id)
    if contact is None or contact.university_id != interaction.university_id:
        raise NotFoundError("Контактное лицо не найдено у вуза этого взаимодействия")
    if not contact.is_active:
        raise ConflictError("Контакт в архиве: назначить его нельзя")
    if payload.is_primary:
        others = await session.execute(
            select(InteractionContact).where(
                InteractionContact.workflow_instance_id == interaction.id,
                InteractionContact.contact_id != contact.id,
                InteractionContact.is_primary.is_(True),
            )
        )
        for other in others.scalars():
            other.is_primary = False
    link = await session.get(InteractionContact, (interaction.id, contact.id))
    if link is None:
        link = InteractionContact(workflow_instance_id=interaction.id, contact_id=contact.id)
        session.add(link)
    link.role = payload.role
    link.is_primary = payload.is_primary
    await session.flush()
    await session.refresh(link, ["contact"])
    return InteractionContactRead.model_validate(link)


@router.delete(
    "/{interaction_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Снять ответственного от вуза",
)
async def remove_contact(
    interaction: WritableInteractionDep, contact_id: uuid.UUID, session: SessionDep
) -> None:
    link = await session.get(InteractionContact, (interaction.id, contact_id))
    if link is None:
        raise NotFoundError("Этот контакт не назначен по взаимодействию")
    await session.delete(link)


# --- Договор и лицензии --------------------------------------------------------------


@router.get(
    "/{interaction_id}/contract",
    response_model=ContractRead | None,
    summary="Договор взаимодействия",
    description="null - договора пока нет: до подписания его может не быть.",
)
async def read_contract(
    interaction: InteractionDep, session: SessionDep
) -> ContractRead | None:
    contract = await session.scalar(
        select(Contract).where(Contract.workflow_instance_id == interaction.id)
    )
    return ContractRead.model_validate(contract) if contract else None


@router.put(
    "/{interaction_id}/contract",
    response_model=ContractRead,
    summary="Завести или изменить договор",
    description=(
        "У взаимодействия не больше одного договора. Проверяются даты (срок, "
        "подписание) и статусы: действующий договор подписан, закрытый - с причиной, "
        "подписанный не отменяют, а закрывают."
    ),
)
async def put_contract(
    interaction: WritableInteractionDep, payload: ContractWrite, session: SessionDep
) -> ContractRead:
    contract = await session.scalar(
        select(Contract).where(Contract.workflow_instance_id == interaction.id)
    )
    if contract is None:
        if interaction.status == InteractionStatus.CANCELLED:
            raise ConflictError("Взаимодействие отменено: договор по нему не заводится")
        contract = Contract(workflow_instance_id=interaction.id)
        session.add(contract)
    for field, value in payload.model_dump().items():
        setattr(contract, field, value)
    interaction.updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(contract)
    return ContractRead.model_validate(contract)


@router.delete(
    "/{interaction_id}/contract",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить ошибочный черновик договора",
    description=(
        "Подписанный договор не удаляют, а закрывают. Договор с лицензиями не удалить."
    ),
)
async def delete_contract(interaction: WritableInteractionDep, session: SessionDep) -> None:
    contract = await session.scalar(
        select(Contract).where(Contract.workflow_instance_id == interaction.id)
    )
    if contract is None:
        raise NotFoundError("Договора нет")
    if contract.status != ContractStatus.DRAFT or contract.signed_at is not None:
        raise ConflictError("Удалить можно только черновик договора - остальные закрывают")
    licenses_count = await session.scalar(
        select(func.count()).select_from(License).where(License.contract_id == contract.id)
    )
    if licenses_count:
        raise ConflictError("По договору оформлены лицензии")
    await session.delete(contract)


@router.get(
    "/{interaction_id}/licenses",
    response_model=list[LicenseRead],
    summary="Лицензии взаимодействия",
)
async def list_interaction_licenses(
    interaction: InteractionDep, session: SessionDep
) -> list[LicenseRead]:
    await licenses.expire_overdue(session)
    result = await session.execute(
        select(License)
        .join(InteractionProduct, InteractionProduct.id == License.interaction_product_id)
        .where(InteractionProduct.workflow_instance_id == interaction.id)
        .order_by(License.valid_to.asc().nullslast())
    )
    return [LicenseRead.model_validate(row) for row in result.scalars()]


@router.post(
    "/{interaction_id}/products/{link_id}/licenses",
    response_model=LicenseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить лицензию на продукт",
    description=(
        "Лицензия оформляется по договору взаимодействия - без договора её не добавить."
    ),
)
async def create_license(
    interaction: WritableInteractionDep,
    link_id: uuid.UUID,
    payload: LicenseCreate,
    session: SessionDep,
) -> LicenseRead:
    link = await session.get(InteractionProduct, link_id)
    if link is None or link.workflow_instance_id != interaction.id:
        raise NotFoundError("Продукт не найден в составе взаимодействия")
    contract = await session.scalar(
        select(Contract).where(Contract.workflow_instance_id == interaction.id)
    )
    if contract is None:
        raise ConflictError("Сначала заведите договор: лицензия оформляется по нему")
    license_ = License(
        contract_id=contract.id, interaction_product_id=link.id, **payload.model_dump()
    )
    licenses.normalize_status(license_)
    session.add(license_)
    await session.flush()
    return LicenseRead.model_validate(license_)
