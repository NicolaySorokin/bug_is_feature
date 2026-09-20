"""Лицензии на ИТ-продукты в составе договора.

Лицензия принадлежит строке состава договора (contract_products), а не вузу
и не продукту вообще: у одного продукта в разных договорах разные сроки
и условия. Отдельный реестр с фильтром «заканчивается через N дней» нужен
для контроля проблемных процессов из раздела 7 концепции.
"""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import ContractDep, CurrentUserDep, PaginationDep, PrincipalDep, SessionDep
from app.core.errors import NotFoundError
from app.enums import LicenseStatus
from app.models.catalog import ItProduct
from app.models.contract import Contract, ContractProduct, License
from app.models.university import University
from app.schemas.common import Page
from app.schemas.license import LicenseCreate, LicenseListItem, LicenseRead, LicenseUpdate
from app.services import access

router = APIRouter(prefix="/licenses", tags=["licenses"])
contract_router = APIRouter(prefix="/contracts", tags=["licenses"])


def _days_left(valid_to: date | None) -> int | None:
    return None if valid_to is None else (valid_to - date.today()).days


def _registry_statement() -> Select:
    """Лицензия вместе с договором, вузом и продуктом."""
    return (
        select(License, Contract, University, ItProduct)
        .join(ContractProduct, ContractProduct.id == License.contract_product_id)
        .join(Contract, Contract.id == ContractProduct.contract_id)
        .join(University, University.id == Contract.university_id)
        .join(ItProduct, ItProduct.id == ContractProduct.product_id)
    )


async def _get_license(session: SessionDep, license_id: uuid.UUID) -> License:
    statement = (
        select(License)
        .where(License.id == license_id)
        .options(
            selectinload(License.contract_product)
            .selectinload(ContractProduct.contract)
            .selectinload(Contract.university)
        )
    )
    license_ = (await session.execute(statement)).scalar_one_or_none()
    if license_ is None:
        raise NotFoundError("Лицензия не найдена")
    return license_


@router.get("", response_model=Page[LicenseListItem], summary="Реестр лицензий")
async def list_licenses(
    session: SessionDep,
    pagination: PaginationDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
    university_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    license_status: LicenseStatus | None = Query(default=None, alias="status"),
    expiring_in_days: int | None = Query(
        default=None,
        ge=0,
        description="Только лицензии, срок которых истекает в ближайшие N дней",
    ),
) -> Page[LicenseListItem]:
    conditions = []
    if university_id is not None:
        conditions.append(Contract.university_id == university_id)
    if product_id is not None:
        conditions.append(ContractProduct.product_id == product_id)
    if license_status is not None:
        conditions.append(License.status == license_status)
    if expiring_in_days is not None:
        conditions.append(License.valid_to.is_not(None))
        conditions.append(License.valid_to <= date.today() + timedelta(days=expiring_in_days))

    statement = access.apply_contract_scope(
        _registry_statement().where(*conditions), principal, user
    )
    total_statement = access.apply_contract_scope(
        select(func.count())
        .select_from(License)
        .join(ContractProduct, ContractProduct.id == License.contract_product_id)
        .join(Contract, Contract.id == ContractProduct.contract_id)
        .where(*conditions),
        principal,
        user,
    )

    total = await session.scalar(total_statement) or 0
    rows = await session.execute(
        statement.order_by(License.valid_to.asc().nullslast())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )

    items = [
        LicenseListItem(
            **LicenseRead.model_validate(license_).model_dump(),
            contract_id=contract.id,
            contract_number=contract.number,
            university_id=university.id,
            university_name=university.name,
            product_id=product.id,
            product_name=product.name,
            days_left=_days_left(license_.valid_to),
        )
        for license_, contract, university, product in rows.all()
    ]
    return Page(
        items=items, total=total, limit=pagination.limit, offset=pagination.offset
    )


@contract_router.get(
    "/{contract_id}/licenses",
    response_model=list[LicenseRead],
    summary="Лицензии по договору",
)
async def list_contract_licenses(
    contract: ContractDep, session: SessionDep
) -> list[LicenseRead]:
    statement = (
        select(License)
        .join(ContractProduct, ContractProduct.id == License.contract_product_id)
        .where(ContractProduct.contract_id == contract.id)
        .order_by(License.valid_to.asc().nullslast())
    )
    result = await session.execute(statement)
    return [LicenseRead.model_validate(row) for row in result.scalars()]


@contract_router.post(
    "/{contract_id}/products/{contract_product_id}/licenses",
    response_model=LicenseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить лицензию на продукт договора",
)
async def create_license(
    contract: ContractDep,
    contract_product_id: uuid.UUID,
    payload: LicenseCreate,
    session: SessionDep,
) -> LicenseRead:
    link = await session.get(ContractProduct, contract_product_id)
    if link is None or link.contract_id != contract.id:
        raise NotFoundError("Продукт не найден в составе договора")

    license_ = License(contract_product_id=contract_product_id, **payload.model_dump())
    session.add(license_)
    await session.flush()
    return LicenseRead.model_validate(license_)


@router.patch("/{license_id}", response_model=LicenseRead, summary="Изменить лицензию")
async def update_license(
    license_id: uuid.UUID,
    payload: LicenseUpdate,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> LicenseRead:
    license_ = await _get_license(session, license_id)
    access.ensure_contract_access(
        license_.contract_product.contract, principal, user
    )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(license_, field, value)
    await session.flush()
    return LicenseRead.model_validate(license_)


@router.delete(
    "/{license_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить лицензию"
)
async def delete_license(
    license_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> None:
    license_ = await _get_license(session, license_id)
    access.ensure_contract_access(license_.contract_product.contract, principal, user)
    await session.delete(license_)
