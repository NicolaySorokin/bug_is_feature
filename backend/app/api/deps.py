"""Общие зависимости FastAPI: сессия, текущий пользователь, проверка ролей."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, ErrorCode, ForbiddenError, NotFoundError
from app.core.security import AuthBackend, Principal, bearer_token
from app.db.session import get_session
from app.enums import Role
from app.models.contract import Contract
from app.models.user import User
from app.services import access, audit

# scope="function": транзакция фиксируется до отправки ответа, см. get_session.
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]

# Роли, которые понимает система. Остальные роли токена (служебные роли
# Keycloak вроде offline_access) в снимок профиля не попадают.
KNOWN_ROLES = frozenset(role.value for role in Role)


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

    ФИО берётся из токена только при первом входе: дальше им распоряжается
    CRM (администратор, импорт каталога), потому что в Keycloak хранятся
    лишь имя и фамилия, а в отчётах и при импорте нужно полное ФИО.
    Почта, логин и снимок ролей обновляются при каждом обращении.
    Отметка о последнем обращении пишется не чаще раза в пять минут.
    """
    roles = sorted(KNOWN_ROLES.intersection(principal.roles))
    updates: dict[str, object] = {
        "username": principal.username,
        "roles": roles,
        "last_seen_at": case(
            (
                (User.last_seen_at.is_(None))
                | (User.last_seen_at < func.now() - func.make_interval(0, 0, 0, 0, 0, 5)),
                func.now(),
            ),
            else_=User.last_seen_at,
        ),
    }
    if principal.profile_is_authoritative and principal.email:
        updates["email"] = principal.email

    statement = (
        pg_insert(User)
        .values(
            keycloak_id=principal.subject,
            username=principal.username,
            full_name=principal.full_name,
            email=principal.email,
            roles=roles,
            last_seen_at=func.now(),
        )
        .on_conflict_do_update(index_elements=[User.keycloak_id], set_=updates)
        .returning(User)
        # Строка могла быть в сессии от прошлого чтения - берём свежую.
        .execution_options(populate_existing=True)
    )
    result = await session.execute(statement)
    user = result.scalar_one()
    if not user.is_active:
        raise AppError(
            "Учётная запись отключена администратором CRM",
            code=ErrorCode.ACCOUNT_DISABLED,
            status_code=403,
        )
    # Дальше любое изменение данных в этом запросе попадёт в журнал от его имени.
    audit.set_actor(user.id)
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def get_access_token(request: Request) -> str | None:
    """Токен текущего запроса - для вызовов Admin API Keycloak от имени пользователя."""
    return bearer_token(request)


AccessTokenDep = Annotated[str | None, Depends(get_access_token)]


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
    await access.ensure_contract_access(session, contract, principal, user)
    return contract


ContractDep = Annotated[Contract, Depends(get_accessible_contract)]


class Pagination:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[Pagination, Depends(Pagination)]
