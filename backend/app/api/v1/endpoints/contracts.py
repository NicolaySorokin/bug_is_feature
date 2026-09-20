"""Реестр договоров и карточка договора."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import Select, func, select
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
from app.models.contract import Contract, ContractProduct, ContractProgram
from app.models.workflow import WorkflowInstance
from app.schemas.common import Page
from app.schemas.contract import (
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
)
from app.services import access
from app.services import workflow as workflow_service

router = APIRouter(prefix="/contracts", tags=["contracts"])


def _detail_options() -> list:
    return [
        selectinload(Contract.university),
        selectinload(Contract.programs).selectinload(ContractProgram.program),
        selectinload(Contract.products).selectinload(ContractProduct.product),
    ]


async def _load_detail(session: SessionDep, contract_id: uuid.UUID) -> Contract:
    """Карточка договора со всем составом. Права проверяются отдельно."""
    statement = (
        select(Contract).where(Contract.id == contract_id).options(*_detail_options())
    )
    contract = (await session.execute(statement)).scalar_one_or_none()
    if contract is None:
        raise NotFoundError("Договор не найден")
    return contract


def _apply_filters(
    statement: Select,
    *,
    university_id: uuid.UUID | None,
    manager_id: uuid.UUID | None,
    contract_status: ContractStatus | None,
    program_id: uuid.UUID | None,
    product_id: uuid.UUID | None,
    stage_id: uuid.UUID | None,
    search: str | None,
) -> Select:
    if university_id is not None:
        statement = statement.where(Contract.university_id == university_id)
    if manager_id is not None:
        statement = statement.where(Contract.manager_id == manager_id)
    if contract_status is not None:
        statement = statement.where(Contract.status == contract_status)
    if search:
        statement = statement.where(Contract.number.ilike(f"%{search}%"))
    if program_id is not None:
        statement = statement.where(
            Contract.id.in_(
                select(ContractProgram.contract_id).where(
                    ContractProgram.program_id == program_id
                )
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
    return statement


@router.get(
    "",
    response_model=Page[ContractListItem],
    summary="Реестр договоров",
    description=(
        "Менеджер видит договоры, где он ответственный или закреплён за вузом; "
        "руководитель и администратор - все."
    ),
)
async def list_contracts(
    session: SessionDep,
    pagination: PaginationDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
    university_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
    contract_status: ContractStatus | None = Query(default=None, alias="status"),
    program_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = Query(default=None, description="Текущий этап процесса"),
    search: str | None = Query(default=None, description="Поиск по номеру договора"),
) -> Page[ContractListItem]:
    filters = {
        "university_id": university_id,
        "manager_id": manager_id,
        "contract_status": contract_status,
        "program_id": program_id,
        "product_id": product_id,
        "stage_id": stage_id,
        "search": search,
    }
    def scoped(statement: Select) -> Select:
        return access.apply_contract_scope(
            _apply_filters(statement, **filters), principal, user
        )

    total = (
        await session.scalar(scoped(select(func.count()).select_from(Contract))) or 0
    )
    result = await session.execute(
        scoped(select(Contract))
        .options(selectinload(Contract.university))
        .order_by(Contract.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    return Page(
        items=[ContractListItem.model_validate(row) for row in result.scalars()],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "",
    response_model=ContractDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Создать договор",
)
async def create_contract(
    payload: ContractCreate,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> ContractDetail:
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

    return ContractDetail.model_validate(await _load_detail(session, contract.id))


@router.get("/{contract_id}", response_model=ContractDetail, summary="Карточка договора")
async def read_contract(contract: ContractDep, session: SessionDep) -> ContractDetail:
    return ContractDetail.model_validate(await _load_detail(session, contract.id))


@router.patch("/{contract_id}", response_model=ContractDetail, summary="Изменить договор")
async def update_contract(
    contract: ContractDep,
    payload: ContractUpdate,
    session: SessionDep,
    principal: PrincipalDep,
) -> ContractDetail:
    data = payload.model_dump(exclude_unset=True)
    # Менять ответственного за вуз может только руководитель (раздел 8 ТЗ).
    if "manager_id" in data and not principal.has_role(Role.HEAD, Role.ADMIN):
        raise ForbiddenError("Менять ответственного может только руководитель")

    for field, value in data.items():
        setattr(contract, field, value)
    await session.flush()
    return ContractDetail.model_validate(await _load_detail(session, contract.id))


@router.delete(
    "/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(Role.ADMIN))],
    summary="Удалить договор",
)
async def delete_contract(contract: ContractDep, session: SessionDep) -> None:
    await session.delete(contract)


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
    link = ContractProduct(contract_id=contract.id, **payload.model_dump())
    session.add(link)
    await session.flush()
    await session.refresh(link, ["product"])
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
    await session.refresh(link, ["product"])
    return ContractProductRead.model_validate(link)
