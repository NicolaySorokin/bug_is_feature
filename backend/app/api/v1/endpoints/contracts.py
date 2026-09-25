"""Реестр договоров и карточка договора."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    ContractDep,
    CurrentUserDep,
    PaginationDep,
    PrincipalDep,
    SessionDep,
    require_roles,
)
from app.core.errors import ConflictError, ErrorCode, ForbiddenError, NotFoundError
from app.enums import ContractStatus, Role
from app.models.catalog import ItProduct, ItProgram
from app.models.contract import (
    Contract,
    ContractContact,
    ContractProduct,
    ContractProgram,
)
from app.models.university import University, UniversityContact
from app.models.user import User
from app.models.workflow import WorkflowInstance, WorkflowStage
from app.schemas.common import Page
from app.schemas.contract import (
    ContractContactCreate,
    ContractContactRead,
    ContractCreate,
    ContractDetail,
    ContractListItem,
    ContractProductCreate,
    ContractProductRead,
    ContractProductUpdate,
    ContractProgramCreate,
    ContractProgramRead,
    ContractProgramUpdate,
    ContractUpdate,
    ProcessSummary,
)
from app.services import access
from app.services import workflow as workflow_service

router = APIRouter(prefix="/contracts", tags=["contracts"])


class ContractOrder(StrEnum):
    """Сортировка реестра."""

    CREATED = "created"  # сначала новые
    UPDATED = "updated"  # сначала недавно изменённые
    NUMBER = "number"
    VALID_TO = "valid_to"  # сначала те, у кого срок кончается раньше
    UNIVERSITY = "university"


class ProcessFilter(StrEnum):
    """Фильтр реестра по состоянию рабочего процесса."""

    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    NONE = "none"  # процесс не запущен


def _process_summary(contract: Contract) -> ProcessSummary | None:
    """Текущий процесс договора для строки реестра (в первой версии он один)."""
    instances = contract.__dict__.get("workflow_instances")
    if not instances:
        return None
    instance = max(
        instances, key=lambda item: item.started_at or datetime.min.replace(tzinfo=UTC)
    )
    stage = instance.current_stage
    days = (
        (datetime.now(UTC) - instance.current_stage_started_at).days
        if instance.current_stage_started_at
        else None
    )
    return ProcessSummary(
        instance_id=instance.id,
        status=instance.status,
        stage_id=stage.id if stage else None,
        stage_name=stage.name if stage else None,
        days_on_stage=days,
        sla_days=stage.sla_days if stage else None,
    )


def _list_item(contract: Contract) -> ContractListItem:
    item = ContractListItem.model_validate(contract)
    item.process = _process_summary(contract)
    return item


def _detail_options() -> list:
    return [
        selectinload(Contract.university),
        selectinload(Contract.manager),
        selectinload(Contract.programs).selectinload(ContractProgram.program),
        selectinload(Contract.products).selectinload(ContractProduct.product),
        selectinload(Contract.products).selectinload(ContractProduct.licenses),
        selectinload(Contract.contacts).selectinload(ContractContact.contact),
        selectinload(Contract.workflow_instances).selectinload(WorkflowInstance.current_stage),
    ]


async def _load_detail(session: SessionDep, contract_id: uuid.UUID) -> ContractDetail:
    """Карточка договора со всем составом. Права проверяются отдельно."""
    statement = (
        select(Contract)
        .where(Contract.id == contract_id)
        .options(*_detail_options())
        # Состав мог измениться в этом же запросе: берём свежие данные.
        .execution_options(populate_existing=True)
    )
    contract = (await session.execute(statement)).scalar_one_or_none()
    if contract is None:
        raise NotFoundError("Договор не найден")
    detail = ContractDetail.model_validate(contract)
    detail.process = _process_summary(contract)
    detail.contacts.sort(key=lambda item: (not item.is_primary, item.contact.full_name))
    return detail


def _apply_filters(
    statement: Select,
    *,
    university_id: uuid.UUID | None,
    manager_id: uuid.UUID | None,
    unassigned: bool,
    contract_status: ContractStatus | None,
    direction_id: uuid.UUID | None,
    program_id: uuid.UUID | None,
    product_id: uuid.UUID | None,
    stage_id: uuid.UUID | None,
    stage_name: str | None,
    search: str | None,
    process: ProcessFilter | None = None,
) -> Select:
    if university_id is not None:
        statement = statement.where(Contract.university_id == university_id)
    if manager_id is not None:
        statement = statement.where(Contract.manager_id == manager_id)
    if unassigned:
        statement = statement.where(Contract.manager_id.is_(None))
    if contract_status is not None:
        statement = statement.where(Contract.status == contract_status)
    if search:
        search_value = f"%{search}%"
        statement = statement.where(
            or_(
                Contract.number.ilike(search_value),
                Contract.title.ilike(search_value),
                Contract.university.has(University.name.ilike(search_value)),
                Contract.university.has(University.short_name.ilike(search_value)),
            )
        )
    if program_id is not None:
        statement = statement.where(
            Contract.id.in_(
                select(ContractProgram.contract_id).where(
                    ContractProgram.program_id == program_id
                )
            )
        )
    if direction_id is not None:
        statement = statement.where(
            Contract.id.in_(
                select(ContractProgram.contract_id)
                .join(ItProgram, ItProgram.id == ContractProgram.program_id)
                .where(ItProgram.direction_id == direction_id)
            )
        )
    if product_id is not None:
        statement = statement.where(
            Contract.id.in_(
                select(ContractProduct.contract_id).where(
                    ContractProduct.product_id == product_id
                )
            )
        )
    if stage_id is not None:
        statement = statement.where(
            Contract.id.in_(
                select(WorkflowInstance.contract_id).where(
                    WorkflowInstance.current_stage_id == stage_id
                )
            )
        )
    if stage_name:
        # Этапы разных версий шаблона - разные записи с одним названием,
        # поэтому фильтр «по этапу» в реестре удобнее вести по названию.
        statement = statement.where(
            Contract.id.in_(
                select(WorkflowInstance.contract_id)
                .join(WorkflowStage, WorkflowStage.id == WorkflowInstance.current_stage_id)
                .where(WorkflowStage.name == stage_name)
            )
        )
    if process is ProcessFilter.NONE:
        statement = statement.where(
            Contract.id.not_in(select(WorkflowInstance.contract_id))
        )
    elif process is not None:
        statement = statement.where(
            Contract.id.in_(
                select(WorkflowInstance.contract_id).where(
                    WorkflowInstance.status == process.value
                )
            )
        )
    return statement


def _order(statement: Select, order: ContractOrder) -> Select:
    if order is ContractOrder.UPDATED:
        return statement.order_by(Contract.updated_at.desc(), Contract.id)
    if order is ContractOrder.NUMBER:
        return statement.order_by(Contract.number, Contract.id)
    if order is ContractOrder.VALID_TO:
        return statement.order_by(Contract.valid_to.asc().nullslast(), Contract.id)
    if order is ContractOrder.UNIVERSITY:
        return statement.join(University, University.id == Contract.university_id).order_by(
            University.name, Contract.number
        )
    return statement.order_by(Contract.created_at.desc(), Contract.id)


@router.get(
    "",
    response_model=Page[ContractListItem],
    summary="Реестр договоров",
    description=(
        "Менеджер видит договоры, где он ответственный или закреплён за вузом, "
        "и договоры вузов, открытых ему администратором; руководитель "
        "и администратор - все. В строке - текущий этап процесса."
    ),
)
async def list_contracts(
    session: SessionDep,
    pagination: PaginationDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
    university_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
    unassigned: bool = Query(default=False, description="Только без ответственного"),
    contract_status: ContractStatus | None = Query(default=None, alias="status"),
    direction_id: uuid.UUID | None = None,
    program_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = Query(default=None, description="Текущий этап процесса"),
    stage: str | None = Query(default=None, description="Название текущего этапа"),
    process: ProcessFilter | None = Query(
        default=None, description="Состояние процесса; none - процесс не запущен"
    ),
    search: str | None = Query(default=None, description="Номер, название, вуз"),
    order: ContractOrder = ContractOrder.CREATED,
) -> Page[ContractListItem]:
    filters = {
        "university_id": university_id,
        "manager_id": manager_id,
        "unassigned": unassigned,
        "contract_status": contract_status,
        "direction_id": direction_id,
        "program_id": program_id,
        "product_id": product_id,
        "stage_id": stage_id,
        "stage_name": stage,
        "search": search,
        "process": process,
    }

    def scoped(statement: Select) -> Select:
        return access.apply_contract_scope(
            _apply_filters(statement, **filters), principal, user
        )

    total = (
        await session.scalar(scoped(select(func.count()).select_from(Contract))) or 0
    )
    result = await session.execute(
        _order(scoped(select(Contract)), order)
        .options(
            selectinload(Contract.university),
            selectinload(Contract.manager),
            selectinload(Contract.workflow_instances).selectinload(
                WorkflowInstance.current_stage
            ),
        )
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    return Page(
        items=[_list_item(row) for row in result.scalars()],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "",
    response_model=ContractDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Создать договор",
    description=(
        "Менеджер заводит договор на себя; назначить другого ответственного "
        "может руководитель. Можно сразу задать состав и запустить процесс."
    ),
)
async def create_contract(
    payload: ContractCreate,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> ContractDetail:
    if await session.get(University, payload.university_id) is None:
        raise NotFoundError("Вуз не найден")
    privileged = principal.has_role(Role.HEAD, Role.ADMIN)
    if payload.manager_id not in (None, user.id) and not privileged:
        raise ForbiddenError("Назначать ответственным другого сотрудника может руководитель")
    if payload.manager_id is not None and await session.get(User, payload.manager_id) is None:
        raise NotFoundError("Сотрудник для назначения ответственным не найден")

    data = payload.model_dump(exclude={"program_ids", "product_ids", "workflow_template_id"})
    contract = Contract(**data)
    if contract.manager_id is None:
        contract.manager_id = user.id
    session.add(contract)
    await session.flush()

    for program_id in dict.fromkeys(payload.program_ids):
        session.add(ContractProgram(contract_id=contract.id, program_id=program_id))
    for product_id in dict.fromkeys(payload.product_ids):
        session.add(ContractProduct(contract_id=contract.id, product_id=product_id))
    await session.flush()

    if payload.workflow_template_id is not None:
        try:
            version = await workflow_service.latest_published_version(
                session, payload.workflow_template_id
            )
            await workflow_service.start_instance(session, contract.id, version, user)
        except workflow_service.WorkflowError as exc:
            raise ConflictError(str(exc), code=ErrorCode.WORKFLOW_RULE_VIOLATED) from exc

    return await _load_detail(session, contract.id)


@router.get("/{contract_id}", response_model=ContractDetail, summary="Карточка договора")
async def read_contract(contract: ContractDep, session: SessionDep) -> ContractDetail:
    return await _load_detail(session, contract.id)


@router.patch(
    "/{contract_id}",
    response_model=ContractDetail,
    summary="Изменить договор",
    description="Сменить или снять ответственного (manager_id) может только руководитель.",
)
async def update_contract(
    contract: ContractDep,
    payload: ContractUpdate,
    session: SessionDep,
    principal: PrincipalDep,
) -> ContractDetail:
    data = payload.model_dump(exclude_unset=True)
    # Менять ответственного за вуз может только руководитель (раздел 8 ТЗ).
    if "manager_id" in data and data["manager_id"] != contract.manager_id:
        if not principal.has_role(Role.HEAD, Role.ADMIN):
            raise ForbiddenError("Менять ответственного может только руководитель")
        new_manager = data["manager_id"]
        if new_manager is not None and await session.get(User, new_manager) is None:
            raise NotFoundError("Сотрудник для назначения ответственным не найден")

    for field, value in data.items():
        setattr(contract, field, value)
    await session.flush()
    return await _load_detail(session, contract.id)


@router.delete(
    "/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(Role.ADMIN))],
    summary="Удалить договор",
)
async def delete_contract(contract: ContractDep, session: SessionDep) -> None:
    await session.delete(contract)


# --- Состав договора ------------------------------------------------------------


@router.post(
    "/{contract_id}/programs",
    response_model=ContractProgramRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить программу в договор",
)
async def add_program(
    contract: ContractDep,
    payload: ContractProgramCreate,
    session: SessionDep,
) -> ContractProgramRead:
    if await session.get(ItProgram, payload.program_id) is None:
        raise NotFoundError("Программа не найдена в справочнике")
    exists = await session.scalar(
        select(func.count())
        .select_from(ContractProgram)
        .where(
            ContractProgram.contract_id == contract.id,
            ContractProgram.program_id == payload.program_id,
        )
    )
    if exists:
        raise ConflictError("Эта программа уже есть в составе договора")
    link = ContractProgram(contract_id=contract.id, **payload.model_dump())
    session.add(link)
    await session.flush()
    await session.refresh(link, ["program"])
    return ContractProgramRead.model_validate(link)


@router.post(
    "/{contract_id}/products",
    response_model=ContractProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить ИТ-продукт в договор",
)
async def add_product(
    contract: ContractDep,
    payload: ContractProductCreate,
    session: SessionDep,
) -> ContractProductRead:
    if await session.get(ItProduct, payload.product_id) is None:
        raise NotFoundError("Продукт не найден в справочнике")
    exists = await session.scalar(
        select(func.count())
        .select_from(ContractProduct)
        .where(
            ContractProduct.contract_id == contract.id,
            ContractProduct.product_id == payload.product_id,
        )
    )
    if exists:
        raise ConflictError("Этот продукт уже есть в составе договора")
    link = ContractProduct(contract_id=contract.id, **payload.model_dump())
    session.add(link)
    await session.flush()
    await session.refresh(link, ["product", "licenses"])
    return ContractProductRead.model_validate(link)


@router.patch(
    "/{contract_id}/programs/{link_id}",
    response_model=ContractProgramRead,
    summary="Изменить статус внедрения программы",
)
async def update_program(
    contract: ContractDep,
    link_id: uuid.UUID,
    payload: ContractProgramUpdate,
    session: SessionDep,
) -> ContractProgramRead:
    link = await session.get(ContractProgram, link_id)
    if link is None or link.contract_id != contract.id:
        raise NotFoundError("Программа не найдена в составе договора")
    link.implementation_status = payload.implementation_status
    await session.flush()
    await session.refresh(link, ["program"])
    return ContractProgramRead.model_validate(link)


@router.patch(
    "/{contract_id}/products/{link_id}",
    response_model=ContractProductRead,
    summary="Изменить статус передачи продукта",
)
async def update_product(
    contract: ContractDep,
    link_id: uuid.UUID,
    payload: ContractProductUpdate,
    session: SessionDep,
) -> ContractProductRead:
    link = await session.get(ContractProduct, link_id)
    if link is None or link.contract_id != contract.id:
        raise NotFoundError("Продукт не найден в составе договора")
    link.transfer_status = payload.transfer_status
    await session.flush()
    await session.refresh(link, ["product", "licenses"])
    return ContractProductRead.model_validate(link)


@router.delete(
    "/{contract_id}/programs/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Убрать программу из договора",
)
async def remove_program(
    contract: ContractDep, link_id: uuid.UUID, session: SessionDep
) -> None:
    link = await session.get(ContractProgram, link_id)
    if link is None or link.contract_id != contract.id:
        raise NotFoundError("Программа не найдена в составе договора")
    await session.delete(link)


@router.delete(
    "/{contract_id}/products/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Убрать продукт из договора",
    description="Вместе с продуктом удаляются и его лицензии по этому договору.",
)
async def remove_product(
    contract: ContractDep, link_id: uuid.UUID, session: SessionDep
) -> None:
    link = await session.get(ContractProduct, link_id)
    if link is None or link.contract_id != contract.id:
        raise NotFoundError("Продукт не найден в составе договора")
    await session.delete(link)


# --- Ответственные от вуза ------------------------------------------------------


@router.get(
    "/{contract_id}/contacts",
    response_model=list[ContractContactRead],
    summary="Ответственные от вуза по договору",
)
async def list_contract_contacts(
    contract: ContractDep, session: SessionDep
) -> list[ContractContactRead]:
    result = await session.execute(
        select(ContractContact)
        .where(ContractContact.contract_id == contract.id)
        .options(selectinload(ContractContact.contact))
    )
    items = [ContractContactRead.model_validate(row) for row in result.scalars()]
    return sorted(items, key=lambda item: (not item.is_primary, item.contact.full_name))


@router.put(
    "/{contract_id}/contacts",
    response_model=ContractContactRead,
    summary="Назначить контакт вуза ответственным по договору",
    description=(
        "Контакт берётся из контактных лиц того же вуза: один человек не "
        "дублируется для каждого договора (раздел 9.2 концепции). Повторный "
        "вызов обновляет роль и признак основного контакта."
    ),
)
async def put_contract_contact(
    contract: ContractDep,
    payload: ContractContactCreate,
    session: SessionDep,
) -> ContractContactRead:
    contact = await session.get(UniversityContact, payload.contact_id)
    if contact is None or contact.university_id != contract.university_id:
        raise NotFoundError("Контактное лицо не найдено у вуза этого договора")

    if payload.is_primary:
        # Основной контакт у договора один.
        others = await session.execute(
            select(ContractContact).where(
                ContractContact.contract_id == contract.id,
                ContractContact.contact_id != contact.id,
                ContractContact.is_primary.is_(True),
            )
        )
        for other in others.scalars():
            other.is_primary = False

    link = await session.get(ContractContact, (contract.id, contact.id))
    if link is None:
        link = ContractContact(contract_id=contract.id, contact_id=contact.id)
        session.add(link)
    link.role = payload.role
    link.is_primary = payload.is_primary
    await session.flush()
    await session.refresh(link, ["contact"])
    return ContractContactRead.model_validate(link)


@router.delete(
    "/{contract_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Снять ответственного от вуза с договора",
)
async def remove_contract_contact(
    contract: ContractDep, contact_id: uuid.UUID, session: SessionDep
) -> None:
    link = await session.get(ContractContact, (contract.id, contact_id))
    if link is None:
        raise NotFoundError("Этот контакт не назначен по договору")
    await session.delete(link)
