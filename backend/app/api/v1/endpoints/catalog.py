"""Справочники: ИТ-направления, ИТ-программы, вендоры, ИТ-продукты.

Читают все, меняет администратор. Используемые записи не удаляются, а уходят
в архив. Связи программ и продуктов ведёт руководитель.
"""

import uuid

from fastapi import APIRouter, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserDep, SessionDep, require_action
from app.core.errors import ConflictError, NotFoundError
from app.db.session import mark_changed
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
from app.services.access import Action

router = APIRouter(prefix="/catalog", tags=["catalog"])
admin_only = [require_action(Action.EDIT_CATALOG, "Справочники ведёт администратор")]
head_only = [
    require_action(
        Action.EDIT_PROGRAM_PRODUCTS, "Соответствие программ и продуктов ведёт руководитель"
    )
]


async def _get(session: SessionDep, model, item_id: uuid.UUID, title: str):  # noqa: ANN001
    item = await session.get(model, item_id)
    if item is None:
        raise NotFoundError(f"{title} не найден(о) в справочнике")
    return item


async def _check_unique_name(
    session: SessionDep,
    model,
    name: str,
    exclude_id: uuid.UUID | None = None,  # noqa: ANN001
) -> None:
    statement = (
        select(func.count()).select_from(model).where(func.lower(model.name) == name.lower())
    )
    if exclude_id is not None:
        statement = statement.where(model.id != exclude_id)
    if await session.scalar(statement):
        raise ConflictError(f"Запись «{name}» уже есть в справочнике")


async def _active(session: SessionDep, model, item_id: uuid.UUID, title: str):  # noqa: ANN001
    """Запись справочника для новой связи: архивную выбрать нельзя."""
    item = await _get(session, model, item_id, title)
    if not item.is_active:
        raise ConflictError(f"{title} «{item.name}» в архиве - выберите действующую запись")
    return item


async def _update(session: SessionDep, item, data: dict) -> None:  # noqa: ANN001
    if data.get("name"):
        await _check_unique_name(session, type(item), data["name"], item.id)
    for field, value in data.items():
        # Название и признак активности обязательны: пустое значение значит «не менять».
        if field in ("name", "is_active") and value is None:
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
    if payload.direction_id is not None:
        await _active(session, ItDirection, payload.direction_id, "ИТ-направление")
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


async def _check_product_contact(
    session: SessionDep, vendor_id: uuid.UUID | None, contact_id: uuid.UUID | None
) -> None:
    """Ответственный за продукт должен быть контактом того же вендора."""
    if contact_id is None:
        return
    contact = await _get(session, VendorContact, contact_id, "Контакт вендора")
    if vendor_id is None or contact.vendor_id != vendor_id:
        raise ConflictError("Контакт должен принадлежать вендору этого продукта")
    if not contact.is_active:
        raise ConflictError("Контакт вендора в архиве")


@router.post(
    "/products",
    response_model=ItProductRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin_only,
    summary="Добавить ИТ-продукт",
)
async def create_product(payload: ItProductCreate, session: SessionDep) -> ItProductRead:
    await _check_unique_name(session, ItProduct, payload.name)
    if payload.vendor_id is not None:
        await _active(session, Vendor, payload.vendor_id, "Вендор")
    await _check_product_contact(session, payload.vendor_id, payload.contact_id)
    product = ItProduct(**payload.model_dump())
    session.add(product)
    await session.flush()
    return ItProductRead.model_validate(product)


# Правка справочников


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
    # Новая связь только с действующим направлением, прежняя архивная остаётся.
    if data.get("direction_id") is not None and data["direction_id"] != item.direction_id:
        await _active(session, ItDirection, data["direction_id"], "ИТ-направление")
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
    if data.get("vendor_id") is not None and data["vendor_id"] != item.vendor_id:
        await _active(session, Vendor, data["vendor_id"], "Вендор")
    vendor_id = data.get("vendor_id", item.vendor_id)
    contact_id = data.get("contact_id", item.contact_id)
    if "vendor_id" in data and "contact_id" not in data and contact_id is not None:
        # Сменили вендора, и прежний контакт другой компании больше не подходит.
        contact = await session.get(VendorContact, contact_id)
        if contact is not None and contact.vendor_id != vendor_id:
            data["contact_id"] = None
            contact_id = None
    await _check_product_contact(session, vendor_id, contact_id)
    await _update(session, item, data)
    return ItProductRead.model_validate(item)


# Продукты программ


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
    dependencies=head_only,
    summary="Задать ИТ-продукты программы",
    description=(
        "Справочное соответствие: по нему интерфейс предлагает продукты при "
        "добавлении программы во взаимодействие. Ведёт руководитель."
    ),
)
async def set_program_products(
    item_id: uuid.UUID, payload: ProgramProductsWrite, session: SessionDep
) -> list[ProgramProductLink]:
    await _get(session, ItProgram, item_id, "ИТ-программа")
    product_ids = list(dict.fromkeys(payload.product_ids))
    current = set(
        (
            await session.execute(
                select(ProgramProduct.product_id).where(ProgramProduct.program_id == item_id)
            )
        ).scalars()
    )
    for product_id in product_ids:
        # Архивный продукт остаётся в прежнем соответствии, но заново не добавляется.
        if product_id in current:
            await _get(session, ItProduct, product_id, "ИТ-продукт")
        else:
            await _active(session, ItProduct, product_id, "ИТ-продукт")
    await session.execute(delete(ProgramProduct).where(ProgramProduct.program_id == item_id))
    mark_changed(session)
    for product_id in product_ids:
        session.add(ProgramProduct(program_id=item_id, product_id=product_id))
    await session.flush()
    return [
        ProgramProductLink(program_id=item_id, product_id=product_id)
        for product_id in product_ids
    ]


# Контакты вендоров


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
