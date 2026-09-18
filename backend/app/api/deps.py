"""Общие зависимости FastAPI: сессия, текущий пользователь, проверка ролей."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthBackend, Principal
from app.db.session import get_session
from app.models.user import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_auth_backend(request: Request) -> AuthBackend:
    return request.app.state.auth_backend


async def get_current_principal(
    request: Request,
    backend: Annotated[AuthBackend, Depends(get_auth_backend)],
) -> Principal:
    return await backend.authenticate(request)


PrincipalDep = Annotated[Principal, Depends(get_current_principal)]


async def get_current_user(principal: PrincipalDep, session: SessionDep) -> User:
    """Находит или заводит запись пользователя по его идентификатору в Keycloak.

    Профиль - источник истины в Keycloak, поэтому имя и почта обновляются
    при каждом входе.
    """
    statement = (
        pg_insert(User)
        .values(
            keycloak_id=principal.subject,
            username=principal.username,
            full_name=principal.full_name,
            email=principal.email,
        )
        .on_conflict_do_update(
            index_elements=[User.keycloak_id],
            set_={
                "username": principal.username,
                "full_name": principal.full_name,
                "email": principal.email,
            },
        )
        .returning(User)
    )
    result = await session.execute(statement)
    return result.scalar_one()


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    """Фабрика зависимостей для проверки ролей.

    Пример: ``dependencies=[Depends(require_roles(Role.ADMIN))]``.
    """

    async def dependency(principal: PrincipalDep) -> Principal:
        if not principal.has_role(*roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Недостаточно прав. Требуется одна из ролей: {', '.join(roles)}",
            )
        return principal

    return dependency


class Pagination:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[Pagination, Depends(Pagination)]
