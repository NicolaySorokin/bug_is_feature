"""Вузы и их контактные лица."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserDep, PaginationDep, SessionDep, require_roles
from app.enums import Role
from app.models.university import University, UniversityContact
from app.schemas.common import Page
from app.schemas.university import (
    UniversityContactCreate,
    UniversityContactRead,
    UniversityCreate,
    UniversityDetail,
    UniversityRead,
    UniversityUpdate,
)

router = APIRouter(prefix="/universities", tags=["universities"])


async def _get_university(session: SessionDep, university_id: uuid.UUID) -> University:
    statement = (
        select(University)
        .where(University.id == university_id)
        .options(selectinload(University.contacts))
    )
    university = (await session.execute(statement)).scalar_one_or_none()
    if university is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вуз не найден")
    return university


@router.get("", response_model=Page[UniversityRead], summary="Реестр вузов")
async def list_universities(
    session: SessionDep,
    pagination: PaginationDep,
    _: CurrentUserDep,
    search: str | None = Query(default=None, description="Поиск по названию"),
    manager_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> Page[UniversityRead]:
    conditions = []
    if search:
        conditions.append(University.name.ilike(f"%{search}%"))
    if manager_id is not None:
        conditions.append(University.manager_id == manager_id)
    if is_active is not None:
        conditions.append(University.is_active.is_(is_active))

    total = (
        await session.scalar(select(func.count()).select_from(University).where(*conditions))
        or 0
    )
    result = await session.execute(
        select(University)
        .where(*conditions)
        .order_by(University.name)
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    return Page(
        items=[UniversityRead.model_validate(row) for row in result.scalars()],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "",
    response_model=UniversityDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить вуз",
)
async def create_university(
    payload: UniversityCreate,
    session: SessionDep,
    _: CurrentUserDep,
) -> UniversityDetail:
    university = University(**payload.model_dump())
    session.add(university)
    await session.flush()
    await session.refresh(university, ["contacts"])
    return UniversityDetail.model_validate(university)


@router.get("/{university_id}", response_model=UniversityDetail, summary="Карточка вуза")
async def read_university(
    university_id: uuid.UUID,
    session: SessionDep,
    _: CurrentUserDep,
) -> UniversityDetail:
    return UniversityDetail.model_validate(await _get_university(session, university_id))


@router.patch("/{university_id}", response_model=UniversityDetail, summary="Изменить вуз")
async def update_university(
    university_id: uuid.UUID,
    payload: UniversityUpdate,
    session: SessionDep,
    _: CurrentUserDep,
) -> UniversityDetail:
    university = await _get_university(session, university_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(university, field, value)
    await session.flush()
    return UniversityDetail.model_validate(university)


@router.delete(
    "/{university_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(Role.ADMIN))],
    summary="Удалить вуз",
)
async def delete_university(university_id: uuid.UUID, session: SessionDep) -> None:
    university = await _get_university(session, university_id)
    await session.delete(university)


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
    _: CurrentUserDep,
) -> UniversityContactRead:
    await _get_university(session, university_id)
    contact = UniversityContact(university_id=university_id, **payload.model_dump())
    session.add(contact)
    await session.flush()
    return UniversityContactRead.model_validate(contact)
