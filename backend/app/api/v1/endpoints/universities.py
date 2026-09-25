"""Вузы и их контактные лица.

Права:

* список и карточки вузов видны всем: без них менеджер не заведёт договор;
* заводить и править вуз - руководитель и администратор (это справочник);
* ответственного за вуз назначает, меняет и снимает руководитель - прямое
  требование ролевой модели ТЗ (администратор тоже может);
* контакты вуза правит закреплённый за ним менеджер, руководитель
  и администратор - именно менеджер первым узнаёт о смене людей в вузе.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentUserDep,
    PaginationDep,
    PrincipalDep,
    SessionDep,
    require_roles,
)
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.enums import ContractStatus, Role
from app.models.contract import Contract
from app.models.university import University, UniversityContact
from app.models.user import User
from app.schemas.common import Page
from app.schemas.university import (
    UniversityContactCreate,
    UniversityContactRead,
    UniversityContactUpdate,
    UniversityCreate,
    UniversityDetail,
    UniversityListItem,
    UniversityUpdate,
)
from app.services import access

router = APIRouter(prefix="/universities", tags=["universities"])
staff_only = [Depends(require_roles(Role.HEAD, Role.ADMIN))]


def _contract_counts():
    """Подзапрос: сколько у вуза договоров всего и сколько действующих."""
    return (
        select(
            Contract.university_id.label("university_id"),
            func.count().label("total"),
            func.count(case((Contract.status == ContractStatus.ACTIVE, 1))).label("active"),
        )
        .group_by(Contract.university_id)
        .subquery()
    )


async def _get_university(session: SessionDep, university_id: uuid.UUID) -> University:
    statement = (
        select(University)
        .where(University.id == university_id)
        .options(selectinload(University.contacts), selectinload(University.manager))
    )
    university = (await session.execute(statement)).scalar_one_or_none()
    if university is None:
        raise NotFoundError("Вуз не найден")
    return university


async def _detail(session: SessionDep, university: University) -> UniversityDetail:
    counts = (
        await session.execute(
            select(
                func.count(),
                func.count(case((Contract.status == ContractStatus.ACTIVE, 1))),
            ).where(Contract.university_id == university.id)
        )
    ).one()
    # Связи могли поменяться в этом же запросе - перечитываем их.
    await session.refresh(university, ["contacts", "manager"])
    detail = UniversityDetail.model_validate(university)
    detail.contracts_count, detail.active_contracts_count = counts
    return detail


async def _check_manager(session: SessionDep, manager_id: uuid.UUID | None) -> None:
    if manager_id is not None and await session.get(User, manager_id) is None:
        raise NotFoundError("Сотрудник для назначения ответственным не найден")


@router.get("", response_model=Page[UniversityListItem], summary="Реестр вузов")
async def list_universities(
    session: SessionDep,
    pagination: PaginationDep,
    _: CurrentUserDep,
    search: str | None = Query(default=None, description="Поиск по названию и сокращению"),
    manager_id: uuid.UUID | None = None,
    unassigned: bool = Query(default=False, description="Только без ответственного"),
    is_active: bool | None = None,
) -> Page[UniversityListItem]:
    conditions = []
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                University.name.ilike(pattern),
                University.short_name.ilike(pattern),
                University.city.ilike(pattern),
            )
        )
    if manager_id is not None:
        conditions.append(University.manager_id == manager_id)
    if unassigned:
        conditions.append(University.manager_id.is_(None))
    if is_active is not None:
        conditions.append(University.is_active.is_(is_active))

    total = (
        await session.scalar(select(func.count()).select_from(University).where(*conditions))
        or 0
    )
    counts = _contract_counts()
    result = await session.execute(
        select(University, counts.c.total, counts.c.active)
        .outerjoin(counts, counts.c.university_id == University.id)
        .where(*conditions)
        .options(selectinload(University.manager))
        .order_by(University.name)
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    items = []
    for university, contracts_total, contracts_active in result.all():
        item = UniversityListItem.model_validate(university)
        item.contracts_count = contracts_total or 0
        item.active_contracts_count = contracts_active or 0
        items.append(item)
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post(
    "",
    response_model=UniversityDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=staff_only,
    summary="Добавить вуз",
)
async def create_university(
    payload: UniversityCreate, session: SessionDep
) -> UniversityDetail:
    await _check_manager(session, payload.manager_id)
    duplicate = await session.scalar(
        select(func.count())
        .select_from(University)
        .where(func.lower(University.name) == payload.name.lower())
    )
    if duplicate:
        raise ConflictError(f"Вуз «{payload.name}» уже есть в справочнике")
    university = University(**payload.model_dump())
    session.add(university)
    await session.flush()
    return await _detail(session, university)


@router.get("/{university_id}", response_model=UniversityDetail, summary="Карточка вуза")
async def read_university(
    university_id: uuid.UUID,
    session: SessionDep,
    _: CurrentUserDep,
) -> UniversityDetail:
    return await _detail(session, await _get_university(session, university_id))


@router.patch(
    "/{university_id}",
    response_model=UniversityDetail,
    dependencies=staff_only,
    summary="Изменить вуз и ответственного за него",
    description=(
        "Ответственного (manager_id) назначает, меняет и снимает руководитель: "
        "передайте id сотрудника или null."
    ),
)
async def update_university(
    university_id: uuid.UUID,
    payload: UniversityUpdate,
    session: SessionDep,
) -> UniversityDetail:
    university = await _get_university(session, university_id)
    data = payload.model_dump(exclude_unset=True)
    if "manager_id" in data:
        await _check_manager(session, data["manager_id"])
    for field, value in data.items():
        setattr(university, field, value)
    await session.flush()
    return await _detail(session, university)


@router.delete(
    "/{university_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(Role.ADMIN))],
    summary="Удалить вуз",
    description="Вуз с договорами удалить нельзя - его можно перевести в архив (is_active).",
)
async def delete_university(university_id: uuid.UUID, session: SessionDep) -> None:
    university = await _get_university(session, university_id)
    contracts = await session.scalar(
        select(func.count())
        .select_from(Contract)
        .where(Contract.university_id == university.id)
    )
    if contracts:
        raise ConflictError(
            f"У вуза {contracts} договор(ов): удалить нельзя, переведите вуз в архив"
        )
    await session.delete(university)


# --- Контактные лица ----------------------------------------------------------


async def _managed_university(
    session: SessionDep,
    university_id: uuid.UUID,
    principal: PrincipalDep,
    user: CurrentUserDep,
) -> University:
    university = await _get_university(session, university_id)
    if not access.can_manage_university(principal, user, university):
        raise ForbiddenError(
            "Контакты вуза правит закреплённый за ним менеджер или руководитель"
        )
    return university


async def _get_contact(
    session: SessionDep, university: University, contact_id: uuid.UUID
) -> UniversityContact:
    contact = await session.get(UniversityContact, contact_id)
    if contact is None or contact.university_id != university.id:
        raise NotFoundError("Контактное лицо не найдено у этого вуза")
    return contact


@router.post(
    "/{university_id}/contacts",
    response_model=UniversityContactRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить контактное лицо вуза",
)
async def create_contact(
    university_id: uuid.UUID,
    payload: UniversityContactCreate,
    session: SessionDep,
    principal: PrincipalDep,
    user: CurrentUserDep,
) -> UniversityContactRead:
    await _managed_university(session, university_id, principal, user)
    contact = UniversityContact(university_id=university_id, **payload.model_dump())
    session.add(contact)
    await session.flush()
    return UniversityContactRead.model_validate(contact)


@router.patch(
    "/{university_id}/contacts/{contact_id}",
    response_model=UniversityContactRead,
    summary="Изменить контактное лицо вуза",
)
async def update_contact(
    university_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: UniversityContactUpdate,
    session: SessionDep,
    principal: PrincipalDep,
    user: CurrentUserDep,
) -> UniversityContactRead:
    university = await _managed_university(session, university_id, principal, user)
    contact = await _get_contact(session, university, contact_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await session.flush()
    return UniversityContactRead.model_validate(contact)


@router.delete(
    "/{university_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить контактное лицо вуза",
    description="Контакт снимается и со всех договоров, где он был ответственным от вуза.",
)
async def delete_contact(
    university_id: uuid.UUID,
    contact_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep,
    user: CurrentUserDep,
) -> None:
    university = await _managed_university(session, university_id, principal, user)
    await session.delete(await _get_contact(session, university, contact_id))
