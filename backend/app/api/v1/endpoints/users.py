"""Текущий пользователь, сотрудники и их права.

Роли меняются в Keycloak через Admin API, права на данные хранятся у нас.
Область шире ролевой выдаётся с основанием. Список сотрудников с почтой
и ролями видит только администратор.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AccessTokenDep,
    CurrentUserDep,
    PaginationDep,
    PrincipalDep,
    SessionDep,
    require_action,
)
from app.core.config import settings
from app.core.errors import AppError, ConflictError, ErrorCode, ForbiddenError, NotFoundError
from app.core.security import Principal
from app.enums import DataScope, Role
from app.models.access import UserUniversityAccess
from app.models.university import University
from app.models.user import User
from app.models.workflow import WorkflowInstance
from app.schemas.common import Page
from app.schemas.user import (
    AccessGrantRead,
    AccessGrantWrite,
    MeRead,
    PasswordReset,
    RoleSyncResult,
    UserBrief,
    UserCreate,
    UserDetail,
    UserRead,
    UserUpdate,
)
from app.services import access
from app.services.access import Action
from app.services.keycloak_admin import KeycloakAdmin, split_full_name

router = APIRouter(tags=["users"])
admin_only = [require_action(Action.MANAGE_USERS, "Пользователями управляет администратор")]

# Насколько широка область: шире ролевой только с основанием.
_SCOPE_RANK = {DataScope.NONE: 0, DataScope.OWN: 1, DataScope.TEAM: 2, DataScope.ALL: 3}


def _keycloak_mode() -> bool:
    return settings.auth_backend == "keycloak"


def _keycloak(token: str | None) -> KeycloakAdmin:
    if not token:
        raise AppError(
            "Для управления учётными записями нужен токен Keycloak",
            code=ErrorCode.UNAUTHORIZED,
            status_code=401,
        )
    return KeycloakAdmin(token)


async def _get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    return user


def _role_principal(user: User) -> Principal:
    """Сотрудник с ролями из снимка, для расчёта области по ролям."""
    return Principal(
        subject=user.keycloak_id,
        username=user.username,
        full_name=user.full_name,
        roles=frozenset(user.roles or []),
    )


async def _grants(session: AsyncSession, user: User) -> list[AccessGrantRead]:
    rows = await session.execute(
        select(UserUniversityAccess, University)
        .join(University, University.id == UserUniversityAccess.university_id)
        .where(UserUniversityAccess.user_id == user.id)
        .order_by(UserUniversityAccess.created_at.desc())
    )
    people_ids = set()
    items = list(rows.all())
    for grant, _ in items:
        people_ids.update(filter(None, (grant.granted_by_id, grant.revoked_by_id)))
    people = {
        person.id: UserBrief.model_validate(person)
        for person in (
            await session.execute(select(User).where(User.id.in_(people_ids)))
        ).scalars()
    }
    now = datetime.now(UTC)
    return [
        AccessGrantRead(
            university_id=university.id,
            university_name=university.short_name or university.name,
            reason=grant.reason,
            granted_by=people.get(grant.granted_by_id),
            created_at=grant.created_at,
            expires_at=grant.expires_at,
            revoked_at=grant.revoked_at,
            revoked_by=people.get(grant.revoked_by_id),
            is_active=grant.revoked_at is None
            and (grant.expires_at is None or grant.expires_at > now),
        )
        for grant, university in items
    ]


async def _detail(session: AsyncSession, user: User) -> UserDetail:
    managed = list(
        (
            await session.execute(
                select(University.id).where(University.manager_id == user.id)
            )
        ).scalars()
    )
    interactions = await session.scalar(
        select(func.count())
        .select_from(WorkflowInstance)
        .where(WorkflowInstance.manager_id == user.id)
    )
    team = (
        await session.execute(
            select(User).where(User.head_id == user.id).order_by(User.full_name)
        )
    ).scalars()
    head = await session.get(User, user.head_id) if user.head_id else None
    detail = UserDetail.model_validate(user)
    detail.effective_scope = access.effective_scope(_role_principal(user), user)
    detail.head = UserBrief.model_validate(head) if head else None
    detail.grants = await _grants(session, user)
    detail.managed_university_ids = managed
    detail.interactions_count = interactions or 0
    detail.team = [UserBrief.model_validate(member) for member in team]
    return detail


async def _check_head(session: AsyncSession, user: User, head_id: uuid.UUID | None) -> None:
    if head_id is None:
        return
    if head_id == user.id:
        raise ConflictError("Сотрудник не может быть руководителем самому себе")
    head = await session.get(User, head_id)
    if head is None:
        raise NotFoundError("Руководитель не найден")
    if Role.HEAD not in (head.roles or []):
        raise ConflictError(
            "Руководителем команды назначается сотрудник с ролью «Руководитель»"
        )


def _apply_scope(user: User, scope: DataScope, reason: str | None, expires_at) -> None:  # noqa: ANN001
    """Область шире ролевой выдаётся только с основанием."""
    role_scope = access.role_scope(_role_principal(user))
    wider = scope is not DataScope.DEFAULT and _SCOPE_RANK[scope] > _SCOPE_RANK[role_scope]
    if wider and not (reason or "").strip():
        raise AppError(
            "Область данных шире, чем даёт роль: укажите основание "
            "(и срок, если доступ временный)",
            code=ErrorCode.VALIDATION_ERROR,
        )
    if expires_at is not None and expires_at <= datetime.now(UTC):
        raise AppError("Срок области данных уже прошёл", code=ErrorCode.VALIDATION_ERROR)
    user.data_scope = scope
    user.data_scope_reason = reason if scope is not DataScope.DEFAULT else None
    user.data_scope_expires_at = expires_at if scope is not DataScope.DEFAULT else None


@router.get("/me", response_model=MeRead, summary="Профиль текущего пользователя")
async def read_me(
    user: CurrentUserDep, principal: PrincipalDep, session: SessionDep
) -> MeRead:
    me = MeRead.model_validate(user)
    # Роли берём из токена этого запроса, а не из снимка: они точнее.
    me.roles = sorted(role for role in principal.roles if role in {r.value for r in Role})
    me.effective_scope = access.effective_scope(principal, user)
    me.actions = sorted(action.value for action in access.actions(principal, user))
    head = await session.get(User, user.head_id) if user.head_id else None
    me.head = UserBrief.model_validate(head) if head else None
    return me


@router.get(
    "/users/directory",
    response_model=list[UserBrief],
    summary="Справочник сотрудников для назначения и фильтров",
    description=(
        "Менеджеры, которых сотрудник может назначить ответственными или "
        "выбрать в фильтре: руководителю - менеджеры его команды (или все - при "
        "области «все»), менеджеру - он сам. Без почты и ролей."
    ),
)
async def directory(
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
    role: Role = Role.MANAGER,
) -> list[UserBrief]:
    scope = access.effective_scope(principal, user)
    statement = select(User).where(User.is_active.is_(True), User.roles.any(role.value))
    if access.can(principal, user, Action.MANAGE_USERS) or scope is DataScope.ALL:
        pass
    elif scope is DataScope.TEAM:
        statement = statement.where(or_(User.head_id == user.id, User.id == user.id))
    else:
        statement = statement.where(User.id == user.id)
    result = await session.execute(statement.order_by(User.full_name))
    return [UserBrief.model_validate(row) for row in result.scalars()]


@router.get(
    "/users",
    response_model=Page[UserRead],
    dependencies=admin_only,
    summary="Сотрудники ИТ Школы",
)
async def list_users(
    session: SessionDep,
    pagination: PaginationDep,
    search: str | None = Query(default=None, description="ФИО, логин или почта"),
    role: Role | None = Query(default=None, description="Только с этой ролью"),
    is_active: bool | None = None,
) -> Page[UserRead]:
    conditions = []
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                User.full_name.ilike(pattern),
                User.username.ilike(pattern),
                User.email.ilike(pattern),
            )
        )
    if role is not None:
        conditions.append(User.roles.any(role.value))
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))

    total = await session.scalar(select(func.count()).select_from(User).where(*conditions))
    result = await session.execute(
        select(User)
        .where(*conditions)
        .order_by(User.full_name)
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    return Page(
        items=[UserRead.model_validate(row) for row in result.scalars()],
        total=total or 0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/users/{user_id}",
    response_model=UserDetail,
    summary="Карточка пользователя",
    description="Администратор видит любого сотрудника, остальные - только себя.",
)
async def read_user(
    user_id: uuid.UUID,
    session: SessionDep,
    current: CurrentUserDep,
    principal: PrincipalDep,
) -> UserDetail:
    if user_id != current.id and not access.can(principal, current, Action.MANAGE_USERS):
        raise ForbiddenError("Карточки других пользователей доступны администратору")
    return await _detail(session, await _get_user(session, user_id))


@router.post(
    "/users",
    response_model=UserDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin_only,
    summary="Завести пользователя",
    description=(
        "С Keycloak учётная запись создаётся в реалме с временным паролем и ролями, "
        "в CRM - карточка с ФИО и правами на данные. Без Keycloak (режим "
        "разработки) заводится только карточка: войти можно заголовком X-Dev-User."
    ),
)
async def create_user(
    payload: UserCreate,
    session: SessionDep,
    token: AccessTokenDep,
) -> UserDetail:
    exists = await session.scalar(
        select(func.count()).select_from(User).where(User.username == payload.username)
    )
    if exists:
        raise ConflictError(f"Пользователь с логином «{payload.username}» уже есть")

    roles = sorted({role.value for role in payload.roles})
    if _keycloak_mode():
        if not payload.password:
            raise AppError(
                "Укажите временный пароль: Keycloak попросит сменить его при первом входе",
                code=ErrorCode.VALIDATION_ERROR,
            )
        first_name, last_name = split_full_name(payload.full_name)
        keycloak_id = await _keycloak(token).create_user(
            username=payload.username,
            first_name=first_name,
            last_name=last_name,
            email=payload.email,
            password=payload.password,
            roles=set(roles),
        )
    else:
        keycloak_id = f"dev:{payload.username}"

    user = User(
        keycloak_id=keycloak_id,
        username=payload.username,
        full_name=payload.full_name,
        email=payload.email,
        roles=roles,
        permissions=sorted({item.value for item in payload.permissions}),
    )
    await _check_head(session, user, payload.head_id)
    user.head_id = payload.head_id
    _apply_scope(
        user, payload.data_scope, payload.data_scope_reason, payload.data_scope_expires_at
    )
    session.add(user)
    await session.flush()
    return await _detail(session, user)


@router.patch(
    "/users/{user_id}",
    response_model=UserDetail,
    dependencies=admin_only,
    summary="Изменить роли, права и область данных",
    description=(
        "Роли меняются в Keycloak (без Keycloak - только в карточке). Область данных "
        "шире ролевой требует основания; можно задать срок. Отключённый "
        "пользователь не проходит в CRM даже с действующим токеном."
    ),
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    session: SessionDep,
    current: CurrentUserDep,
    token: AccessTokenDep,
) -> UserDetail:
    user = await _get_user(session, user_id)
    data = payload.model_dump(exclude_unset=True)

    if user.id == current.id:
        # Администратор не должен закрыть вход самому себе.
        if data.get("is_active") is False:
            raise ConflictError("Нельзя отключить собственную учётную запись")
        if "roles" in data and Role.ADMIN not in (payload.roles or []):
            raise ConflictError("Нельзя снять с себя роль администратора")

    # Учётные записи, заведённые без Keycloak (dev:...), в реалме не существуют.
    in_keycloak = _keycloak_mode() and not user.keycloak_id.startswith("dev:")
    keycloak = _keycloak(token) if in_keycloak else None

    if payload.roles is not None:
        roles = sorted({role.value for role in payload.roles})
        if keycloak is not None:
            await keycloak.set_roles(user.keycloak_id, set(roles))
        user.roles = roles

    if payload.permissions is not None:
        user.permissions = sorted({item.value for item in payload.permissions})

    if "head_id" in data:
        await _check_head(session, user, data["head_id"])
        user.head_id = data["head_id"]

    if payload.is_active is not None:
        if keycloak is not None:
            await keycloak.set_enabled(user.keycloak_id, payload.is_active)
        user.is_active = payload.is_active

    if payload.full_name is not None or "email" in data:
        if payload.full_name is not None:
            user.full_name = payload.full_name
        if "email" in data:
            user.email = payload.email
        if keycloak is not None:
            first_name, last_name = split_full_name(user.full_name)
            await keycloak.update_profile(
                user.keycloak_id, first_name=first_name, last_name=last_name, email=user.email
            )

    if "data_scope" in data or "data_scope_reason" in data or "data_scope_expires_at" in data:
        _apply_scope(
            user,
            DataScope(data.get("data_scope", user.data_scope)),
            data.get("data_scope_reason", user.data_scope_reason),
            data.get("data_scope_expires_at", user.data_scope_expires_at),
        )

    await session.flush()
    return await _detail(session, user)


# Точечный доступ к вузам


@router.put(
    "/users/{user_id}/grants",
    response_model=UserDetail,
    dependencies=admin_only,
    summary="Открыть сотруднику вуз",
    description=(
        "Точечный доступ сверх области данных: основание обязательно, срок - если "
        "доступ временный (например, на время отпуска коллеги). Повторный вызов "
        "продлевает или восстанавливает доступ."
    ),
)
async def grant_access(
    user_id: uuid.UUID,
    payload: AccessGrantWrite,
    session: SessionDep,
    current: CurrentUserDep,
) -> UserDetail:
    user = await _get_user(session, user_id)
    if await session.get(University, payload.university_id) is None:
        raise NotFoundError("Вуз не найден")
    if payload.expires_at is not None and payload.expires_at <= datetime.now(UTC):
        raise AppError("Срок доступа уже прошёл", code=ErrorCode.VALIDATION_ERROR)
    grant = await session.get(UserUniversityAccess, (user.id, payload.university_id))
    if grant is None:
        grant = UserUniversityAccess(user_id=user.id, university_id=payload.university_id)
        session.add(grant)
    grant.reason = payload.reason
    grant.expires_at = payload.expires_at
    grant.granted_by_id = current.id
    grant.revoked_at = None
    grant.revoked_by_id = None
    await session.flush()
    return await _detail(session, user)


@router.delete(
    "/users/{user_id}/grants/{university_id}",
    response_model=UserDetail,
    dependencies=admin_only,
    summary="Отозвать доступ к вузу",
    description="Запись не удаляется: отмечаются время отзыва и кто отозвал.",
)
async def revoke_access(
    user_id: uuid.UUID,
    university_id: uuid.UUID,
    session: SessionDep,
    current: CurrentUserDep,
) -> UserDetail:
    user = await _get_user(session, user_id)
    grant = await session.get(UserUniversityAccess, (user.id, university_id))
    if grant is None or grant.revoked_at is not None:
        raise NotFoundError("Действующего доступа к этому вузу нет")
    grant.revoked_at = datetime.now(UTC)
    grant.revoked_by_id = current.id
    await session.flush()
    return await _detail(session, user)


@router.post(
    "/users/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=admin_only,
    summary="Выдать временный пароль",
    description=(
        "Пароль пишется в Keycloak временным: при первом входе Keycloak попросит "
        "сотрудника придумать свой. Постоянный пароль знает только сам сотрудник - "
        "администратор его не задаёт."
    ),
)
async def reset_password(
    user_id: uuid.UUID,
    payload: PasswordReset,
    session: SessionDep,
    token: AccessTokenDep,
) -> None:
    user = await _get_user(session, user_id)
    if not _keycloak_mode() or user.keycloak_id.startswith("dev:"):
        raise ConflictError("Пароли хранятся в Keycloak, а он в этом режиме не подключён")
    await _keycloak(token).reset_password(user.keycloak_id, payload.password)


@router.post(
    "/users/sync-roles",
    response_model=RoleSyncResult,
    dependencies=admin_only,
    summary="Сверить роли с Keycloak",
    description=(
        "Обновляет снимок ролей в CRM по данным Keycloak и заводит карточки "
        "тем, кто получил роль, но ещё ни разу не входил: их можно сразу "
        "назначать ответственными."
    ),
)
async def sync_roles(session: SessionDep, token: AccessTokenDep) -> RoleSyncResult:
    if not _keycloak_mode():
        total = await session.scalar(select(func.count()).select_from(User)) or 0
        return RoleSyncResult(users_total=total, users_created=0, users_updated=0)

    keycloak = _keycloak(token)
    members = await keycloak.role_members()
    roles_by_user: dict[str, set[str]] = {}
    for role, user_ids in members.items():
        for keycloak_id in user_ids:
            roles_by_user.setdefault(keycloak_id, set()).add(role)

    existing = {
        user.keycloak_id: user
        for user in (
            await session.execute(select(User).where(User.keycloak_id.in_(roles_by_user)))
        ).scalars()
    }
    created = updated = 0
    for keycloak_id, roles in roles_by_user.items():
        user = existing.get(keycloak_id)
        if user is None:
            profile = await keycloak.get_user(keycloak_id)
            full_name = " ".join(
                part for part in (profile.last_name, profile.first_name) if part
            )
            session.add(
                User(
                    keycloak_id=keycloak_id,
                    username=profile.username,
                    full_name=full_name or profile.username,
                    email=profile.email,
                    roles=sorted(roles),
                    is_active=profile.enabled,
                )
            )
            created += 1
        elif set(user.roles or []) != roles:
            user.roles = sorted(roles)
            updated += 1
    # Если в Keycloak сняли все роли системы, убираем их и из снимка, иначе
    # сотрудника предлагали бы ответственным до следующего входа.
    stale = (
        await session.execute(
            select(User).where(
                User.keycloak_id.not_in(list(roles_by_user)),
                User.keycloak_id.not_like("dev:%"),
                func.cardinality(User.roles) > 0,
            )
        )
    ).scalars()
    for user in stale:
        user.roles = []
        updated += 1
    await session.flush()
    return RoleSyncResult(
        users_total=len(roles_by_user), users_created=created, users_updated=updated
    )
