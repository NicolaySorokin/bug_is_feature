"""Схемы пользователей, текущей сессии и настроек доступа."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.enums import DataScope, Role
from app.schemas.common import ORMModel

# Политика паролей реалма Keycloak (deploy/keycloak/realm-export.json):
# короче пароль Keycloak не примет, поэтому и API сразу его не пропускает.
PASSWORD_MIN_LENGTH = 12


class UserRead(ORMModel):
    id: uuid.UUID
    username: str
    full_name: str
    email: str | None
    is_active: bool
    # Снимок ролей с последнего входа (или последней синхронизации с Keycloak).
    roles: list[str] = []


class MeRead(UserRead):
    """Профиль текущего пользователя вместе с ролями из токена."""

    data_scope: DataScope = DataScope.DEFAULT
    # Видит ли пользователь все договоры - по роли или по решению администратора.
    sees_all_contracts: bool = False


class UserDetail(UserRead):
    """Карточка пользователя для администратора: права и доступ к данным."""

    keycloak_id: str
    data_scope: DataScope
    last_seen_at: datetime | None
    created_at: datetime
    # Вузы, открытые администратором сверх закреплённых за пользователем.
    university_ids: list[uuid.UUID] = []
    # Вузы, за которыми пользователь закреплён ответственным.
    managed_university_ids: list[uuid.UUID] = []
    contracts_count: int = 0


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    data_scope: DataScope | None = None
    university_ids: list[uuid.UUID] | None = None
    roles: list[Role] | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    # Временный пароль: Keycloak попросит сменить его при первом входе.
    password: str | None = Field(default=None, min_length=PASSWORD_MIN_LENGTH, max_length=128)
    roles: list[Role] = Field(default_factory=lambda: [Role.MANAGER])
    data_scope: DataScope = DataScope.DEFAULT
    university_ids: list[uuid.UUID] = Field(default_factory=list)


class PasswordReset(BaseModel):
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)
    # Временный пароль Keycloak попросит сменить при первом входе. Постоянный -
    # например, общая учётная запись для показа, которую нельзя «угнать» сменой.
    temporary: bool = True


class RoleSyncResult(BaseModel):
    users_total: int
    users_created: int
    users_updated: int
