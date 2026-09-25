"""Справочники: ИТ-направления, ИТ-программы, вендоры, ИТ-продукты.

Чтение доступно всем авторизованным, изменение - администратору.
Записи, на которые ссылаются договоры, не удаляются, а выключаются
(is_active): история договоров должна оставаться читаемой.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserDep, SessionDep, require_roles
from app.core.errors import ConflictError, NotFoundError
from app.db.session import mark_changed
from app.enums import Role
from app.models.catalog import (
    ItDirection,
    ItProduct,
    ItProgram,
    ProgramProduct,
    Vendor,
    VendorContact,
)
from app.schemas.catalog import (
    ItDirectionRead,
    ItProductCreate,
    ItProductRead,
    ItProductUpdate,
    ItProgramCreate,
    ItProgramRead,
    ItProgramUpdate,
    NamedCreate,
    NamedUpdate,
    ProgramProductLink,
    ProgramProductsWrite,
    VendorContactCreate,
    VendorContactRead,
    VendorContactUpdate,
    VendorRead,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])
admin_only = [Depends(require_roles(Role.ADMIN))]


async def _get(session: SessionDep, model, item_id: uuid.UUID, title: str):  # noqa: ANN001
    item = await session.get(model, item_id)
    if item is None:
        raise NotFoundError(f"{title} не найден(о) в справочнике")
    return item


async def _check_unique_name(
    session: SessionDep, model, name: str, exclude_id: uuid.UUID | None = None  # noqa: ANN001
) -> None:
    statement = select(func.count()).select_from(model).where(
        func.lower(model.name) == name.lower()
    )
    if exclude_id is not None:
        statement = statement.where(model.id != exclude_id)
    if await session.scalar(statement):
        raise ConflictError(f"Запись «{name}» уже есть в справочнике")


async def _update(session: SessionDep, item, data: dict) -> None:  # noqa: ANN001
    if data.get("name"):
        await _check_unique_name(session, type(item), data["name"], item.id)
    for field, value in data.items():
        if field == "name" and value is None:
            continue
        setattr(item, field, value)
    await session.flush()


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
    await _check_unique_name(session, ItDirection, payload.name)
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
    await _check_unique_name(session, ItProgram, payload.name)
    program = ItProgram(**payload.model_dump())
    session.add(program)
    await session.flush()
    return ItProgramRead.model_validate(program)


@router.get("/vendors", response_model=list[VendorRead], summary="Вендоры")
async def list_vendors(session: SessionDep, _: CurrentUserDep) -> list[VendorRead]:
    result = await session.execute(
        select(Vendor).options(selectinload(Vendor.contacts)).order_by(Vendor.name)
    )
    return [VendorRead.model_validate(row) for row in result.scalars()]


@router.post(
    "/vendors",
    response_model=VendorRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin_only,
    summary="Добавить вендора",
)
async def create_vendor(payload: NamedCreate, session: SessionDep) -> VendorRead:
    await _check_unique_name(session, Vendor, payload.name)
    vendor = Vendor(**payload.model_dump())
    session.add(vendor)
    await session.flush()
    await session.refresh(vendor, ["contacts"])
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
    await _check_unique_name(session, ItProduct, payload.name)
    product = ItProduct(**payload.model_dump())
    session.add(product)
    await session.flush()
    return ItProductRead.model_validate(product)


# --- Правка справочников ------------------------------------------------------


@router.patch(
    "/directions/{item_id}",
    response_model=ItDirectionRead,
    dependencies=admin_only,
    summary="Изменить ИТ-направление",
)
async def update_direction(
    item_id: uuid.UUID, payload: NamedUpdate, session: SessionDep
) -> ItDirectionRead:
    item = await _get(session, ItDirection, item_id, "ИТ-направление")
    await _update(session, item, payload.model_dump(exclude_unset=True))
    return ItDirectionRead.model_validate(item)


@router.patch(
    "/programs/{item_id}",
    response_model=ItProgramRead,
    dependencies=admin_only,
    summary="Изменить ИТ-программу",
)
async def update_program(
    item_id: uuid.UUID, payload: ItProgramUpdate, session: SessionDep
) -> ItProgramRead:
    item = await _get(session, ItProgram, item_id, "ИТ-программа")
    data = payload.model_dump(exclude_unset=True)
    if data.get("direction_id") is not None:
        await _get(session, ItDirection, data["direction_id"], "ИТ-направление")
    await _update(session, item, data)
    return ItProgramRead.model_validate(item)


@router.patch(
    "/vendors/{item_id}",
    response_model=VendorRead,
    dependencies=admin_only,
    summary="Изменить вендора",
)
async def update_vendor(
    item_id: uuid.UUID, payload: NamedUpdate, session: SessionDep
) -> VendorRead:
    item = await _get(session, Vendor, item_id, "Вендор")
    await _update(session, item, payload.model_dump(exclude_unset=True))
    await session.refresh(item, ["contacts"])
    return VendorRead.model_validate(item)


@router.patch(
    "/products/{item_id}",
    response_model=ItProductRead,
    dependencies=admin_only,
    summary="Изменить ИТ-продукт",
)
async def update_product(
    item_id: uuid.UUID, payload: ItProductUpdate, session: SessionDep
) -> ItProductRead:
    item = await _get(session, ItProduct, item_id, "ИТ-продукт")
    data = payload.model_dump(exclude_unset=True)
    if data.get("vendor_id") is not None:
        await _get(session, Vendor, data["vendor_id"], "Вендор")
    if data.get("contact_id") is not None:
        await _get(session, VendorContact, data["contact_id"], "Контакт вендора")
    await _update(session, item, data)
    return ItProductRead.model_validate(item)


# --- Продукты программ ----------------------------------------------------------


@router.get(
    "/program-products",
    response_model=list[ProgramProductLink],
    summary="Какие ИТ-продукты используются в программах",
)
async def list_program_products(
    session: SessionDep, _: CurrentUserDep
) -> list[ProgramProductLink]:
    result = await session.execute(select(ProgramProduct))
    return [
        ProgramProductLink(program_id=row.program_id, product_id=row.product_id)
        for row in result.scalars()
    ]


@router.put(
    "/programs/{item_id}/products",
    response_model=list[ProgramProductLink],
    dependencies=admin_only,
    summary="Задать ИТ-продукты программы",
)
async def set_program_products(
    item_id: uuid.UUID, payload: ProgramProductsWrite, session: SessionDep
) -> list[ProgramProductLink]:
    await _get(session, ItProgram, item_id, "ИТ-программа")
    product_ids = list(dict.fromkeys(payload.product_ids))
    for product_id in product_ids:
        await _get(session, ItProduct, product_id, "ИТ-продукт")
    await session.execute(delete(ProgramProduct).where(ProgramProduct.program_id == item_id))
    mark_changed(session)
    for product_id in product_ids:
        session.add(ProgramProduct(program_id=item_id, product_id=product_id))
    await session.flush()
    return [
        ProgramProductLink(program_id=item_id, product_id=product_id)
        for product_id in product_ids
    ]


# --- Контакты вендоров ----------------------------------------------------------


@router.post(
    "/vendors/{vendor_id}/contacts",
    response_model=VendorContactRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin_only,
    summary="Добавить контакт вендора",
)
async def create_vendor_contact(
    vendor_id: uuid.UUID, payload: VendorContactCreate, session: SessionDep
) -> VendorContactRead:
    await _get(session, Vendor, vendor_id, "Вендор")
    contact = VendorContact(vendor_id=vendor_id, **payload.model_dump())
    session.add(contact)
    await session.flush()
    return VendorContactRead.model_validate(contact)


@router.patch(
    "/vendor-contacts/{contact_id}",
    response_model=VendorContactRead,
    dependencies=admin_only,
    summary="Изменить контакт вендора",
)
async def update_vendor_contact(
    contact_id: uuid.UUID, payload: VendorContactUpdate, session: SessionDep
) -> VendorContactRead:
    contact = await _get(session, VendorContact, contact_id, "Контакт вендора")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "full_name" and value is None:
            continue
        setattr(contact, field, value)
    await session.flush()
    return VendorContactRead.model_validate(contact)


@router.delete(
    "/vendor-contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=admin_only,
    summary="Удалить контакт вендора",
    description="С продуктов, за которые он отвечал, контакт снимается.",
)
async def delete_vendor_contact(contact_id: uuid.UUID, session: SessionDep) -> None:
    await session.delete(await _get(session, VendorContact, contact_id, "Контакт вендора"))
