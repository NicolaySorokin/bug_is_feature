"""Текущий пользователь, сотрудники и управление их правами.

ТЗ, ролевая модель: администратор управляет правами пользователей
и ограничениями по видимой информации. Роли живут в Keycloak - их CRM
меняет через Admin API (app.services.keycloak_admin); доступ к данным
(область видимости договоров, открытые вузы, отключение учётной записи)
хранится у нас.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import delete, func, or_, select

from app.api.deps import (
    AccessTokenDep,
    CurrentUserDep,
    PaginationDep,
    PrincipalDep,
    SessionDep,
    require_roles,
)
from app.core.config import settings
from app.core.errors import AppError, ConflictError, ErrorCode, ForbiddenError, NotFoundError
from app.db.session import mark_changed
from app.enums import Role
from app.models.access import UserUniversityAccess
from app.models.contract import Contract
from app.models.university import University
from app.models.user import User
from app.schemas.common import Page
from app.schemas.user import (
    MeRead,
    PasswordReset,
    RoleSyncResult,
    UserCreate,
    UserDetail,
    UserRead,
    UserUpdate,
)
from app.services import access
from app.services.keycloak_admin import KeycloakAdmin, split_full_name

router = APIRouter(tags=["users"])
admin_only = [Depends(require_roles(Role.ADMIN))]


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


async def _get_user(session: SessionDep, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    return user


async def _detail(session: SessionDep, user: User) -> UserDetail:
    granted = list(
        (
            await session.execute(
                select(UserUniversityAccess.university_id).where(
                    UserUniversityAccess.user_id == user.id
                )
            )
        ).scalars()
    )
    managed = list(
        (
            await session.execute(
                select(University.id).where(University.manager_id == user.id)
            )
        ).scalars()
    )
    contracts = await session.scalar(
        select(func.count()).select_from(Contract).where(Contract.manager_id == user.id)
    )
    detail = UserDetail.model_validate(user)
    detail.university_ids = granted
    detail.managed_university_ids = managed
    detail.contracts_count = contracts or 0
    return detail


async def _replace_grants(
    session: SessionDep, user: User, university_ids: list[uuid.UUID]
) -> None:
    unique = list(dict.fromkeys(university_ids))
    if unique:
        found = set(
            (
                await session.execute(select(University.id).where(University.id.in_(unique)))
            ).scalars()
        )
        missing = [str(item) for item in unique if item not in found]
        if missing:
            raise NotFoundError(f"Вузы не найдены: {', '.join(missing)}")
    await session.execute(
        delete(UserUniversityAccess).where(UserUniversityAccess.user_id == user.id)
    )
    # Доступ к данным поменялся - закэшированные сводки пользователя устарели.
    mark_changed(session)
    for university_id in unique:
        session.add(UserUniversityAccess(user_id=user.id, university_id=university_id))
    await session.flush()


@router.get("/me", response_model=MeRead, summary="Профиль текущего пользователя")
async def read_me(user: CurrentUserDep, principal: PrincipalDep) -> MeRead:
    me = MeRead.model_validate(user)
    # Роли - из токена этого запроса, а не из снимка: они точнее.
    me.roles = sorted(role for role in principal.roles if role in {r.value for r in Role})
    me.sees_all_contracts = access.sees_all_contracts(principal, user)
    return me


@router.get("/users", response_model=Page[UserRead], summary="Сотрудники ИТ Школы")
async def list_users(
    session: SessionDep,
    pagination: PaginationDep,
    _: CurrentUserDep,
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
    if user_id != current.id and not principal.has_role(Role.ADMIN):
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
        "в CRM - карточка с ФИО и доступом к данным. Без Keycloak (режим "
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
        data_scope=payload.data_scope,
    )
    session.add(user)
    await session.flush()
    await _replace_grants(session, user, payload.university_ids)
    return await _detail(session, user)


@router.patch(
    "/users/{user_id}",
    response_model=UserDetail,
    dependencies=admin_only,
    summary="Изменить права и доступ пользователя",
    description=(
        "Роли меняются в Keycloak (без Keycloak - только в карточке). Отключённый "
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
        # Защита от того, чтобы администратор сам себя запер снаружи.
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

    if payload.data_scope is not None:
        user.data_scope = payload.data_scope
    if payload.university_ids is not None:
        await _replace_grants(session, user, payload.university_ids)

    await session.flush()
    return await _detail(session, user)


@router.post(
    "/users/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=admin_only,
    summary="Задать пароль",
    description=(
        "Пароль пишется в Keycloak. Временный (по умолчанию) Keycloak попросит "
        "сменить при первом входе, постоянный остаётся как есть."
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
    await _keycloak(token).reset_password(
        user.keycloak_id, payload.password, temporary=payload.temporary
    )


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
    await session.flush()
    return RoleSyncResult(
        users_total=len(roles_by_user), users_created=created, users_updated=updated
    )
