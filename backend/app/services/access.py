"""Роли, права и область данных.

Раздел 12 «Решений по бизнес-модели» и пункты 6-9 перечня исправлений:
роль, функциональные права и область данных разделены.

* **Роль -> действия.** Роли не наследуются: руководитель не получает права
  менеджера, администратор - права руководителя. Сотруднику, который
  совмещает функции, назначают несколько ролей явно.
* **Дополнительные права** (запуск обмена, журнал обмена, персональные
  данные студентов, представление схемы процесса) выдаёт администратор
  отдельно - из роли руководителя они не следуют.
* **Область данных -> какие взаимодействия и вузы видны:** ``own`` - свои
  взаимодействия, вузы, где сотрудник менеджер по умолчанию, и явно
  открытые вузы; ``team`` - плюс взаимодействия менеджеров своей команды
  и взаимодействия без ответственного (очередь назначения); ``all`` - всё;
  ``none`` - только административные функции. По умолчанию область
  следует из ролей; администратор может задать её явно, в том числе
  временно - со сроком и основанием.
* **Точечный доступ** к вузу - со сроком, основанием и отметкой, кто выдал;
  отозванный или истёкший доступ не действует.

Сервер решает всё; клиент получает готовый список действий в /me
и только прячет кнопки, которые роль всё равно не применит.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import ColumnElement, CompoundSelect, Select, false, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.core.security import Principal
from app.enums import DataScope, Permission, Role
from app.models.access import UserUniversityAccess
from app.models.university import University
from app.models.user import User
from app.models.workflow import WorkflowInstance


class Action(StrEnum):
    """Функциональные действия. Набор у каждой роли свой, без наследования."""

    # Бизнес-работа со взаимодействиями
    CREATE_INTERACTION = "create_interaction"
    WORK_INTERACTION = "work_interaction"  # этапы, состав, договор, файлы, комментарии
    ASSIGN_RESPONSIBLE = "assign_responsible"
    SKIP_ANY_STAGE = "skip_any_stage"  # исключение: пропуск обязательного этапа
    CANCEL_INTERACTION = "cancel_interaction"
    PRODUCT_EXCEPTION = "product_exception"  # продукт вне справочного соответствия
    EDIT_PROGRAM_PRODUCTS = "edit_program_products"  # бизнес-связи программ и продуктов
    VIEW_REPORTS = "view_reports"
    VIEW_STATISTICS = "view_statistics"
    EDIT_UNIVERSITY_CONTACTS = "edit_university_contacts"
    PROPOSE_UNIVERSITY = "propose_university"  # завести вуз «на проверку»
    MANAGE_UNIVERSITIES = "manage_universities"  # подтвердить, объединить, архивировать
    # Администрирование
    MANAGE_USERS = "manage_users"
    EDIT_CATALOG = "edit_catalog"
    IMPORT = "import"
    EDIT_TEMPLATES = "edit_templates"
    EDIT_WORKFLOW_PRESENTATION = "edit_workflow_presentation"
    VIEW_AUDIT = "view_audit"
    EDIT_SETTINGS = "edit_settings"
    SYNC_INTEGRATIONS = "sync_integrations"
    VIEW_INTEGRATION_LOG = "view_integration_log"
    RESOLVE_MAPPINGS = "resolve_mappings"
    VIEW_PERSONAL_DATA = "view_personal_data"


ROLE_ACTIONS: dict[Role, frozenset[Action]] = {
    Role.MANAGER: frozenset(
        {
            Action.CREATE_INTERACTION,
            Action.WORK_INTERACTION,
            Action.CANCEL_INTERACTION,
            Action.VIEW_REPORTS,
            Action.VIEW_STATISTICS,
            Action.EDIT_UNIVERSITY_CONTACTS,
            Action.PROPOSE_UNIVERSITY,
        }
    ),
    Role.HEAD: frozenset(
        {
            Action.CREATE_INTERACTION,
            Action.WORK_INTERACTION,
            Action.ASSIGN_RESPONSIBLE,
            Action.SKIP_ANY_STAGE,
            Action.CANCEL_INTERACTION,
            Action.PRODUCT_EXCEPTION,
            Action.EDIT_PROGRAM_PRODUCTS,
            Action.VIEW_REPORTS,
            Action.VIEW_STATISTICS,
            Action.EDIT_UNIVERSITY_CONTACTS,
            Action.MANAGE_UNIVERSITIES,
        }
    ),
    Role.ADMIN: frozenset(
        {
            Action.MANAGE_USERS,
            Action.EDIT_CATALOG,
            Action.IMPORT,
            Action.EDIT_TEMPLATES,
            Action.EDIT_WORKFLOW_PRESENTATION,
            Action.VIEW_AUDIT,
            Action.EDIT_SETTINGS,
            Action.SYNC_INTEGRATIONS,
            Action.VIEW_INTEGRATION_LOG,
            Action.RESOLVE_MAPPINGS,
            Action.MANAGE_UNIVERSITIES,
        }
    ),
}

# Дополнительные права сверх роли - какие действия они открывают.
PERMISSION_ACTIONS: dict[Permission, frozenset[Action]] = {
    Permission.SYNC_INTEGRATIONS: frozenset(
        {Action.SYNC_INTEGRATIONS, Action.VIEW_INTEGRATION_LOG}
    ),
    Permission.VIEW_INTEGRATION_LOG: frozenset({Action.VIEW_INTEGRATION_LOG}),
    Permission.VIEW_PERSONAL_DATA: frozenset({Action.VIEW_PERSONAL_DATA}),
    Permission.EDIT_WORKFLOW_PRESENTATION: frozenset({Action.EDIT_WORKFLOW_PRESENTATION}),
}

BUSINESS_ROLES = frozenset({Role.MANAGER, Role.HEAD})

# Где на объекте пользователя запоминаются вычисленные множества: запрос
# делается один раз на обработку запроса, а не на каждую проверку.
_UNIVERSITIES_CACHE = "_scope_university_ids"
_TEAM_CACHE = "_team_member_ids"


def _roles(principal: Principal) -> set[Role]:
    return {Role(role) for role in principal.roles if role in Role._value2member_map_}


def actions(principal: Principal, user: User) -> set[Action]:
    """Все действия сотрудника: по ролям и по выданным правам."""
    result: set[Action] = set()
    for role in _roles(principal):
        result |= ROLE_ACTIONS[role]
    for permission in user.permissions or []:
        if permission in Permission._value2member_map_:
            result |= PERMISSION_ACTIONS[Permission(permission)]
    return result


def can(principal: Principal, user: User, action: Action) -> bool:
    return action in actions(principal, user)


def ensure(principal: Principal, user: User, action: Action, message: str) -> None:
    if not can(principal, user, action):
        raise ForbiddenError(message)


def has_business_role(principal: Principal) -> bool:
    return bool(_roles(principal) & BUSINESS_ROLES)


def role_scope(principal: Principal) -> DataScope:
    """Область данных по ролям - если явно не задано иное."""
    roles = _roles(principal)
    if Role.HEAD in roles:
        return DataScope.TEAM
    if Role.MANAGER in roles:
        return DataScope.OWN
    return DataScope.NONE


def scope_is_temporary_and_expired(user: User, now: datetime | None = None) -> bool:
    expires = user.data_scope_expires_at
    return expires is not None and expires <= (now or datetime.now(UTC))


def effective_scope(principal: Principal, user: User) -> DataScope:
    """Действующая область данных сотрудника."""
    stored = DataScope(user.data_scope) if user.data_scope else DataScope.DEFAULT
    if stored is DataScope.DEFAULT or scope_is_temporary_and_expired(user):
        return role_scope(principal)
    return stored


def sees_all(principal: Principal, user: User) -> bool:
    return effective_scope(principal, user) is DataScope.ALL


# --- Команда и вузы в области -------------------------------------------------


def _active_grants(user_id: uuid.UUID) -> Select:
    now = datetime.now(UTC)
    return select(UserUniversityAccess.university_id).where(
        UserUniversityAccess.user_id == user_id,
        UserUniversityAccess.revoked_at.is_(None),
        or_(UserUniversityAccess.expires_at.is_(None), UserUniversityAccess.expires_at > now),
    )


def team_members(user: User) -> Select:
    """Сотрудники, у которых руководитель - этот пользователь."""
    return select(User.id).where(User.head_id == user.id)


def own_universities(user: User) -> CompoundSelect:
    """Вузы сотрудника: он менеджер по умолчанию, у него там взаимодействие
    или ему открыт доступ."""
    return union(*_own_university_parts(user))


def _own_university_parts(user: User) -> list[Select]:
    return [
        select(University.id).where(University.manager_id == user.id),
        _active_grants(user.id),
        select(WorkflowInstance.university_id).where(WorkflowInstance.manager_id == user.id),
    ]


def team_universities(user: User) -> CompoundSelect:
    """Вузы команды: свои, вузы менеджеров команды и вузы без менеджера."""
    members = team_members(user)
    return union(
        *_own_university_parts(user),
        select(University.id).where(University.manager_id.in_(members)),
        select(University.id).where(University.manager_id.is_(None)),
        select(WorkflowInstance.university_id).where(WorkflowInstance.manager_id.in_(members)),
    )


def university_scope(principal: Principal, user: User) -> ColumnElement[bool] | None:
    """Условие видимости вуза с бизнес-данными (контакты, взаимодействия).

    ``None`` - ограничений нет.
    """
    scope = effective_scope(principal, user)
    if scope is DataScope.ALL:
        return None
    if scope is DataScope.NONE:
        return false()
    if scope is DataScope.TEAM:
        return University.id.in_(team_universities(user))
    return University.id.in_(own_universities(user))


def interaction_scope(principal: Principal, user: User) -> ColumnElement[bool] | None:
    """Условие видимости взаимодействий. ``None`` - ограничений нет."""
    scope = effective_scope(principal, user)
    if scope is DataScope.ALL:
        return None
    if scope is DataScope.NONE:
        return false()
    own = or_(
        WorkflowInstance.manager_id == user.id,
        WorkflowInstance.university_id.in_(
            select(University.id).where(University.manager_id == user.id)
        ),
        WorkflowInstance.university_id.in_(_active_grants(user.id)),
    )
    if scope is DataScope.OWN:
        return own
    return or_(
        own,
        WorkflowInstance.manager_id.in_(team_members(user)),
        # Взаимодействия без ответственного - очередь назначения руководителя.
        WorkflowInstance.manager_id.is_(None),
    )


def apply_interaction_scope(statement: Select, principal: Principal, user: User) -> Select:
    """Добавляет к запросу по взаимодействиям ограничение видимости."""
    condition = interaction_scope(principal, user)
    return statement if condition is None else statement.where(condition)


def apply_university_scope(statement: Select, principal: Principal, user: User) -> Select:
    condition = university_scope(principal, user)
    return statement if condition is None else statement.where(condition)


async def team_member_ids(session: AsyncSession, user: User) -> set[uuid.UUID]:
    cached = user.__dict__.get(_TEAM_CACHE)
    if cached is None:
        cached = set((await session.execute(team_members(user))).scalars())
        # Прямая запись в __dict__: это не колонка, SQLAlchemy её не отслеживает.
        user.__dict__[_TEAM_CACHE] = cached
    return cached


async def scope_university_ids(
    session: AsyncSession, principal: Principal, user: User
) -> set[uuid.UUID] | None:
    """Вузы в области сотрудника. ``None`` - все вузы."""
    condition = university_scope(principal, user)
    if condition is None:
        return None
    cached = user.__dict__.get(_UNIVERSITIES_CACHE)
    if cached is None:
        cached = set((await session.execute(select(University.id).where(condition))).scalars())
        user.__dict__[_UNIVERSITIES_CACHE] = cached
    return cached


# --- Проверки на конкретных записях -------------------------------------------


async def can_read_interaction(
    session: AsyncSession, interaction: WorkflowInstance, principal: Principal, user: User
) -> bool:
    scope = effective_scope(principal, user)
    if scope is DataScope.ALL:
        return True
    if scope is DataScope.NONE:
        return False
    if interaction.manager_id == user.id:
        return True
    condition = interaction_scope(principal, user)
    found = await session.scalar(
        select(WorkflowInstance.id).where(WorkflowInstance.id == interaction.id, condition)
    )
    return found is not None


async def ensure_interaction_read(
    session: AsyncSession, interaction: WorkflowInstance, principal: Principal, user: User
) -> None:
    """403, если взаимодействие вне области данных сотрудника."""
    if not await can_read_interaction(session, interaction, principal, user):
        raise ForbiddenError("Взаимодействие не входит в вашу область данных")


async def ensure_interaction_write(
    session: AsyncSession, interaction: WorkflowInstance, principal: Principal, user: User
) -> None:
    """Менять взаимодействие может менеджер или руководитель, в чьей области
    оно находится. Администратор без бизнес-роли только читает (если ему
    временно открыта область)."""
    await ensure_interaction_read(session, interaction, principal, user)
    ensure(
        principal,
        user,
        Action.WORK_INTERACTION,
        "Менять ход взаимодействия может менеджер или руководитель",
    )


async def can_see_university(
    session: AsyncSession, university_id: uuid.UUID, principal: Principal, user: User
) -> bool:
    ids = await scope_university_ids(session, principal, user)
    return ids is None or university_id in ids


def can_manage_university(principal: Principal, user: User, university: University) -> bool:
    """Контакты вуза правит его менеджер по умолчанию и руководитель."""
    if university.manager_id == user.id and can(
        principal, user, Action.EDIT_UNIVERSITY_CONTACTS
    ):
        return True
    return Role.HEAD in _roles(principal)
