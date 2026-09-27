"""Лицензии на ИТ-продукты взаимодействий.

Лицензия принадлежит продукту конкретного взаимодействия и оформляется по
его договору. Реестр с фильтром «заканчивается через N дней» нужен для
контроля проблемных процессов из раздела 7 концепции. Просроченные
действующие лицензии истекают автоматически.
"""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserDep, PaginationDep, PrincipalDep, SessionDep
from app.core.errors import AppError, ErrorCode, NotFoundError
from app.enums import LicenseStatus
from app.models.catalog import ItProduct
from app.models.contract import Contract, License
from app.models.interaction import InteractionProduct
from app.models.university import University
from app.models.workflow import WorkflowInstance
from app.schemas.common import Page
from app.schemas.license import LicenseListItem, LicenseRead, LicenseUpdate
from app.schemas.university import UniversityBrief
from app.services import access, licenses

router = APIRouter(prefix="/licenses", tags=["licenses"])


def _days_left(valid_to: date | None) -> int | None:
    return None if valid_to is None else (valid_to - date.today()).days


def _registry(statement: Select) -> Select:
    return (
        statement.join(
            InteractionProduct, InteractionProduct.id == License.interaction_product_id
        )
        .join(WorkflowInstance, WorkflowInstance.id == InteractionProduct.workflow_instance_id)
        .join(Contract, Contract.id == License.contract_id)
        .join(University, University.id == WorkflowInstance.university_id)
        .join(ItProduct, ItProduct.id == InteractionProduct.product_id)
    )


async def _get_license(session: SessionDep, license_id: uuid.UUID) -> License:
    statement = (
        select(License)
        .where(License.id == license_id)
        .options(
            selectinload(License.interaction_product).selectinload(
                InteractionProduct.interaction
            )
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
    await licenses.expire_overdue(session)
    conditions = []
    if university_id is not None:
        conditions.append(WorkflowInstance.university_id == university_id)
    if product_id is not None:
        conditions.append(InteractionProduct.product_id == product_id)
    if license_status is not None:
        conditions.append(License.status == license_status)
    if expiring_in_days is not None:
        conditions.append(License.valid_to.is_not(None))
        conditions.append(License.valid_to <= date.today() + timedelta(days=expiring_in_days))

    statement = access.apply_interaction_scope(
        _registry(select(License, Contract, University, ItProduct, WorkflowInstance.id)).where(
            *conditions
        ),
        principal,
        user,
    )
    total_statement = access.apply_interaction_scope(
        _registry(select(func.count()).select_from(License)).where(*conditions),
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
            interaction_id=interaction_id,
            contract_number=contract.number,
            university=UniversityBrief.of(university),
            product_id=product.id,
            product_name=product.name,
            days_left=_days_left(license_.valid_to),
        )
        for license_, contract, university, product, interaction_id in rows.all()
    ]
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.patch("/{license_id}", response_model=LicenseRead, summary="Изменить лицензию")
async def update_license(
    license_id: uuid.UUID,
    payload: LicenseUpdate,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> LicenseRead:
    license_ = await _get_license(session, license_id)
    await access.ensure_interaction_write(
        session, license_.interaction_product.interaction, principal, user
    )
    data = payload.model_dump(exclude_unset=True)
    # Статус обязателен: пустое значение - «не менять», а не сбой базы.
    if data.get("status") is None:
        data.pop("status", None)
    for field, value in data.items():
        setattr(license_, field, value)
    if license_.valid_from and license_.valid_to and license_.valid_from > license_.valid_to:
        raise AppError(
            "Срок лицензии начинается позже, чем заканчивается",
            code=ErrorCode.VALIDATION_ERROR,
        )
    licenses.normalize_status(license_)
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
    await access.ensure_interaction_write(
        session, license_.interaction_product.interaction, principal, user
    )
    await session.delete(license_)
