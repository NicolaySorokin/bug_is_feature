"""Справочники: ИТ-направления, ИТ-программы, вендоры, ИТ-продукты.

Чтение доступно всем авторизованным, изменение - администратору.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep, require_roles
from app.enums import Role
from app.models.catalog import ItDirection, ItProduct, ItProgram, Vendor
from app.schemas.catalog import (
    ItDirectionRead,
    ItProductCreate,
    ItProductRead,
    ItProgramCreate,
    ItProgramRead,
    NamedCreate,
    VendorRead,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])
admin_only = [Depends(require_roles(Role.ADMIN))]


@router.get("/directions", response_model=list[ItDirectionRead], summary="ИТ-направления")
async def list_directions(session: SessionDep, _: CurrentUserDep) -> list[ItDirectionRead]:
    result = await session.execute(select(ItDirection).order_by(ItDirection.name))
    return [ItDirectionRead.model_validate(row) for row in result.scalars()]


@router.post(
    "/directions",
    response_model=ItDirectionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin_only,
    summary="Добавить ИТ-направление",
)
async def create_direction(payload: NamedCreate, session: SessionDep) -> ItDirectionRead:
    direction = ItDirection(**payload.model_dump())
    session.add(direction)
    await session.flush()
    return ItDirectionRead.model_validate(direction)


@router.get("/programs", response_model=list[ItProgramRead], summary="ИТ-программы")
async def list_programs(session: SessionDep, _: CurrentUserDep) -> list[ItProgramRead]:
    result = await session.execute(select(ItProgram).order_by(ItProgram.name))
    return [ItProgramRead.model_validate(row) for row in result.scalars()]


@router.post(
    "/programs",
    response_model=ItProgramRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin_only,
    summary="Добавить ИТ-программу",
)
async def create_program(payload: ItProgramCreate, session: SessionDep) -> ItProgramRead:
    program = ItProgram(**payload.model_dump())
    session.add(program)
    await session.flush()
    return ItProgramRead.model_validate(program)


@router.get("/vendors", response_model=list[VendorRead], summary="Вендоры")
async def list_vendors(session: SessionDep, _: CurrentUserDep) -> list[VendorRead]:
    result = await session.execute(select(Vendor).order_by(Vendor.name))
    return [VendorRead.model_validate(row) for row in result.scalars()]


@router.post(
    "/vendors",
    response_model=VendorRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin_only,
    summary="Добавить вендора",
)
async def create_vendor(payload: NamedCreate, session: SessionDep) -> VendorRead:
    vendor = Vendor(**payload.model_dump())
    session.add(vendor)
    await session.flush()
    return VendorRead.model_validate(vendor)


@router.get("/products", response_model=list[ItProductRead], summary="ИТ-продукты")
async def list_products(session: SessionDep, _: CurrentUserDep) -> list[ItProductRead]:
    result = await session.execute(select(ItProduct).order_by(ItProduct.name))
    return [ItProductRead.model_validate(row) for row in result.scalars()]


@router.post(
    "/products",
    response_model=ItProductRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin_only,
    summary="Добавить ИТ-продукт",
)
async def create_product(payload: ItProductCreate, session: SessionDep) -> ItProductRead:
    product = ItProduct(**payload.model_dump())
    session.add(product)
    await session.flush()
    return ItProductRead.model_validate(product)
