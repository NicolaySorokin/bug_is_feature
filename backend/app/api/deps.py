"""Общие зависимости FastAPI: сессия, текущий пользователь, проверка ролей."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import AuthBackend, Principal
from app.db.session import get_session
from app.models.contract import Contract
from app.models.user import User
from app.services import access, audit

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
    при каждом входе. Dev-заглушка настоящего имени не знает и сохранённый
    профиль не затирает.
    """
    updates: dict[str, str | None] = {"username": principal.username}
    if principal.profile_is_authoritative:
        updates |= {"full_name": principal.full_name, "email": principal.email}

    statement = (
        pg_insert(User)
        .values(
            keycloak_id=principal.subject,
            username=principal.username,
            full_name=principal.full_name,
            email=principal.email,
        )
        .on_conflict_do_update(index_elements=[User.keycloak_id], set_=updates)
        .returning(User)
    )
    result = await session.execute(statement)
    user = result.scalar_one()
    # Дальше любое изменение данных в этом запросе попадёт в журнал от его имени.
    audit.set_actor(user.id)
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str) -> Callable[[Principal], Awaitable[Principal]]:
    """Фабрика зависимостей для проверки ролей.

    Пример: ``dependencies=[Depends(require_roles(Role.ADMIN))]``.
    """

    async def dependency(principal: PrincipalDep) -> Principal:
        if not principal.has_role(*roles):
            raise ForbiddenError(
                f"Недостаточно прав. Требуется одна из ролей: {', '.join(roles)}"
            )
        return principal

    return dependency


async def get_accessible_contract(
    contract_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> Contract:
    """Договор из пути запроса с проверкой прав на него.

    Вуз подгружается сразу: по нему проверяется, закреплён ли менеджер
    за вузом, и он же нужен почти во всех ответах.
    """
    statement = (
        select(Contract)
        .where(Contract.id == contract_id)
        .options(selectinload(Contract.university))
    )
    contract = (await session.execute(statement)).scalar_one_or_none()
    if contract is None:
        raise NotFoundError("Договор не найден")
    access.ensure_contract_access(contract, principal, user)
    return contract


ContractDep = Annotated[Contract, Depends(get_accessible_contract)]


class Pagination:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[Pagination, Depends(Pagination)]
