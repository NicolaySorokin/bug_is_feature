"""Схемы пользователей, текущей сессии и прав на данные."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.enums import DataScope, Permission, Role
from app.schemas.common import ORMModel

# Политика паролей реалма Keycloak (deploy/keycloak/realm-export.json):
# короче пароль Keycloak не примет, поэтому и API сразу его не пропускает.
PASSWORD_MIN_LENGTH = 12


class UserBrief(ORMModel):
    """Сотрудник в компактном виде: без почты и ролей (минимум данных)."""

    id: uuid.UUID
    full_name: str
    username: str = ""


class UserRead(ORMModel):
    """Сотрудник для администратора: почта и роли видны только ему."""

    id: uuid.UUID
    username: str
    full_name: str
    email: str | None
    is_active: bool
    # Снимок ролей с последнего входа (или последней синхронизации с Keycloak).
    roles: list[str] = []
    permissions: list[str] = []
    head_id: uuid.UUID | None = None
    data_scope: DataScope = DataScope.DEFAULT


class MeRead(UserRead):
    """Профиль текущего пользователя: роли из токена и готовые права."""

    # Действующая область данных (с учётом срока временной области).
    effective_scope: DataScope = DataScope.NONE
    data_scope_reason: str | None = None
    data_scope_expires_at: datetime | None = None
    # Действия, доступные сотруднику: клиент по ним показывает кнопки.
    actions: list[str] = []
    head: UserBrief | None = None


class AccessGrantRead(BaseModel):
    """Точечный доступ к вузу."""

    university_id: uuid.UUID
    university_name: str
    reason: str | None
    granted_by: UserBrief | None = None
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    revoked_by: UserBrief | None = None
    is_active: bool


class AccessGrantWrite(BaseModel):
    university_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=1000)
    expires_at: datetime | None = None


class UserDetail(UserRead):
    """Карточка пользователя для администратора: права и доступ к данным."""

    keycloak_id: str
    data_scope_reason: str | None = None
    data_scope_expires_at: datetime | None = None
    effective_scope: DataScope = DataScope.NONE
    last_seen_at: datetime | None
    created_at: datetime
    head: UserBrief | None = None
    grants: list[AccessGrantRead] = []
    # Вузы, где сотрудник - менеджер по умолчанию.
    managed_university_ids: list[uuid.UUID] = []
    interactions_count: int = 0
    team: list[UserBrief] = []


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    roles: list[Role] | None = None
    permissions: list[Permission] | None = None
    head_id: uuid.UUID | None = None
    data_scope: DataScope | None = None
    # Основание и срок области, отличной от ролевой: обязательно, если
    # область шире, чем даёт роль (например, «все» для менеджера).
    data_scope_reason: str | None = Field(default=None, max_length=1000)
    data_scope_expires_at: datetime | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    # Временный пароль: Keycloak попросит сменить его при первом входе.
    password: str | None = Field(default=None, min_length=PASSWORD_MIN_LENGTH, max_length=128)
    roles: list[Role] = Field(default_factory=lambda: [Role.MANAGER])
    permissions: list[Permission] = Field(default_factory=list)
    head_id: uuid.UUID | None = None
    data_scope: DataScope = DataScope.DEFAULT
    data_scope_reason: str | None = Field(default=None, max_length=1000)
    data_scope_expires_at: datetime | None = None

    @model_validator(mode="after")
    def _check_roles(self) -> "UserCreate":
        self.roles = list(dict.fromkeys(self.roles))
        return self


class PasswordReset(BaseModel):
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)


class RoleSyncResult(BaseModel):
    users_total: int
    users_created: int
    users_updated: int
