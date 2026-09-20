"""Права на уровне записей.

ТЗ, раздел про ролевую модель: администратор разграничивает пользователей
по доступу к данным. Правило простое и одинаковое во всех разделах:

* менеджер видит договоры, где он ответственный или закреплён за вузом;
* руководитель и администратор видят все договоры.

Справочники и вузы видны всем авторизованным: без списка вузов менеджер
не сможет завести договор. Ограничение касается договоров и всего, что
к ним привязано, - процессов, комментариев, файлов, лицензий и отчётов.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, Select, or_, select

from app.core.errors import ForbiddenError
from app.core.security import Principal
from app.enums import Role
from app.models.contract import Contract
from app.models.university import University
from app.models.user import User


def sees_all_contracts(principal: Principal) -> bool:
    return principal.has_role(Role.HEAD, Role.ADMIN)


def contract_scope(principal: Principal, user: User) -> ColumnElement[bool] | None:
    """Условие видимости договоров. ``None`` - ограничений нет."""
    if sees_all_contracts(principal):
        return None
    return or_(
        Contract.manager_id == user.id,
        Contract.university_id.in_(
            select(University.id).where(University.manager_id == user.id)
        ),
    )


def apply_contract_scope(statement: Select, principal: Principal, user: User) -> Select:
    """Добавляет к запросу по договорам ограничение видимости."""
    condition = contract_scope(principal, user)
    return statement if condition is None else statement.where(condition)


def can_read_contract(contract: Contract, principal: Principal, user: User) -> bool:
    if sees_all_contracts(principal):
        return True
    return contract.manager_id == user.id or _is_university_manager(contract, user)


def ensure_contract_access(contract: Contract, principal: Principal, user: User) -> None:
    """Бросает 403, если договор не входит в зону ответственности пользователя."""
    if not can_read_contract(contract, principal, user):
        raise ForbiddenError("Договор не входит в зону вашей ответственности")


def _is_university_manager(contract: Contract, user: User) -> bool:
    # Связь может быть не подгружена - тогда судим только по ответственному.
    university = contract.__dict__.get("university")
    return university is not None and university.manager_id == user.id
