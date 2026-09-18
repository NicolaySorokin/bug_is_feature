"""Текущий пользователь и список сотрудников."""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, PaginationDep, PrincipalDep, SessionDep
from app.models.user import User
from app.schemas.common import Page
from app.schemas.user import MeRead, UserRead

router = APIRouter(tags=["users"])


@router.get("/me", response_model=MeRead, summary="Профиль текущего пользователя")
async def read_me(user: CurrentUserDep, principal: PrincipalDep) -> MeRead:
    return MeRead(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        is_active=user.is_active,
        roles=sorted(principal.roles),
    )


@router.get("/users", response_model=Page[UserRead], summary="Сотрудники ИТ Школы")
async def list_users(
    session: SessionDep,
    pagination: PaginationDep,
    _: CurrentUserDep,
) -> Page[UserRead]:
    total = await session.scalar(select(func.count()).select_from(User)) or 0
    result = await session.execute(
        select(User)
        .order_by(User.full_name)
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    return Page(
        items=[UserRead.model_validate(row) for row in result.scalars()],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )
