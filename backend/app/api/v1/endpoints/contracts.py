"""Реестр договоров и карточка договора."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserDep, PaginationDep, PrincipalDep, SessionDep, require_roles
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
    ContractProgramCreate,
    ContractProgramRead,
    ContractUpdate,
)
from app.services import workflow as workflow_service

router = APIRouter(prefix="/contracts", tags=["contracts"])


def _detail_options() -> list:
    return [
        selectinload(Contract.university),
        selectinload(Contract.programs).selectinload(ContractProgram.program),
        selectinload(Contract.products).selectinload(ContractProduct.product),
    ]


async def _get_contract(session: SessionDep, contract_id: uuid.UUID) -> Contract:
    statement = (
        select(Contract).where(Contract.id == contract_id).options(*_detail_options())
    )
    contract = (await session.execute(statement)).scalar_one_or_none()
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Договор не найден")
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


@router.get("", response_model=Page[ContractListItem], summary="Реестр договоров")
async def list_contracts(
    session: SessionDep,
    pagination: PaginationDep,
    _: CurrentUserDep,
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
    total = (
        await session.scalar(
            _apply_filters(select(func.count()).select_from(Contract), **filters)
        )
        or 0
    )
    result = await session.execute(
        _apply_filters(select(Contract), **filters)
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
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return ContractDetail.model_validate(await _get_contract(session, contract.id))


@router.get("/{contract_id}", response_model=ContractDetail, summary="Карточка договора")
async def read_contract(
    contract_id: uuid.UUID, session: SessionDep, _: CurrentUserDep
) -> ContractDetail:
    return ContractDetail.model_validate(await _get_contract(session, contract_id))


@router.patch("/{contract_id}", response_model=ContractDetail, summary="Изменить договор")
async def update_contract(
    contract_id: uuid.UUID,
    payload: ContractUpdate,
    session: SessionDep,
    _: CurrentUserDep,
) -> ContractDetail:
    contract = await _get_contract(session, contract_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contract, field, value)
    await session.flush()
    return ContractDetail.model_validate(contract)


@router.delete(
    "/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(Role.ADMIN))],
    summary="Удалить договор",
)
async def delete_contract(contract_id: uuid.UUID, session: SessionDep) -> None:
    contract = await _get_contract(session, contract_id)
    await session.delete(contract)


@router.post(
    "/{contract_id}/programs",
    response_model=ContractProgramRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить программу в договор",
)
async def add_program(
    contract_id: uuid.UUID,
    payload: ContractProgramCreate,
    session: SessionDep,
    _: CurrentUserDep,
) -> ContractProgramRead:
    await _get_contract(session, contract_id)
    link = ContractProgram(contract_id=contract_id, **payload.model_dump())
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
    contract_id: uuid.UUID,
    payload: ContractProductCreate,
    session: SessionDep,
    _: CurrentUserDep,
) -> ContractProductRead:
    await _get_contract(session, contract_id)
    link = ContractProduct(contract_id=contract_id, **payload.model_dump())
    session.add(link)
    await session.flush()
    await session.refresh(link, ["product"])
    return ContractProductRead.model_validate(link)
