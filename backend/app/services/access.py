"""Права на уровне записей.

ТЗ, раздел про ролевую модель: администратор разграничивает пользователей
по доступу к данным. Правило одинаковое во всех разделах:

* руководитель и администратор видят все договоры;
* менеджер видит договоры, где он ответственный или закреплён за вузом,
  плюс договоры вузов, к которым ему открыл доступ администратор;
* администратор может открыть менеджеру все договоры (область «все»)
  или, наоборот, отключить учётную запись целиком (см. app.api.deps).

Справочники и вузы видны всем авторизованным: без списка вузов менеджер
не сможет завести договор. Ограничение касается договоров и всего, что
к ним привязано, - процессов, комментариев, файлов, лицензий и отчётов.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.core.security import Principal
from app.enums import DataScope, Role
from app.models.access import UserUniversityAccess
from app.models.contract import Contract
from app.models.university import University
from app.models.user import User

# Где на объекте пользователя запоминаются выданные ему вузы: запрос
# делается один раз на обработку запроса, а не на каждую проверку.
_GRANTS_CACHE = "_granted_university_ids"


def sees_all_contracts(principal: Principal, user: User) -> bool:
    return principal.has_role(Role.HEAD, Role.ADMIN) or user.data_scope == DataScope.ALL


def managed_universities(user: User) -> Select:
    """Вузы, за которыми закреплён пользователь или к которым ему дали доступ."""
    return (
        select(University.id)
        .where(University.manager_id == user.id)
        .union(
            select(UserUniversityAccess.university_id).where(
                UserUniversityAccess.user_id == user.id
            )
        )
    )


def contract_scope(principal: Principal, user: User) -> ColumnElement[bool] | None:
    """Условие видимости договоров. ``None`` - ограничений нет."""
    if sees_all_contracts(principal, user):
        return None
    return or_(
        Contract.manager_id == user.id,
        Contract.university_id.in_(managed_universities(user)),
    )


def apply_contract_scope(statement: Select, principal: Principal, user: User) -> Select:
    """Добавляет к запросу по договорам ограничение видимости."""
    condition = contract_scope(principal, user)
    return statement if condition is None else statement.where(condition)


async def granted_university_ids(session: AsyncSession, user: User) -> set[uuid.UUID]:
    cached = user.__dict__.get(_GRANTS_CACHE)
    if cached is None:
        cached = set((await session.execute(managed_universities(user))).scalars())
        # Прямая запись в __dict__: это не колонка, SQLAlchemy её не отслеживает.
        user.__dict__[_GRANTS_CACHE] = cached
    return cached


async def can_read_contract(
    session: AsyncSession, contract: Contract, principal: Principal, user: User
) -> bool:
    if sees_all_contracts(principal, user) or contract.manager_id == user.id:
        return True
    return contract.university_id in await granted_university_ids(session, user)


async def ensure_contract_access(
    session: AsyncSession, contract: Contract, principal: Principal, user: User
) -> None:
    """Бросает 403, если договор не входит в зону ответственности пользователя."""
    if not await can_read_contract(session, contract, principal, user):
        raise ForbiddenError("Договор не входит в зону вашей ответственности")


def can_manage_university(principal: Principal, user: User, university: University) -> bool:
    """Контакты вуза правит закреплённый за ним менеджер, руководитель и администратор."""
    return principal.has_role(Role.HEAD, Role.ADMIN) or university.manager_id == user.id
