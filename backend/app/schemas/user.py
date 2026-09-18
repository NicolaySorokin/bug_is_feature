"""Схемы пользователей и текущей сессии."""

import uuid

from app.schemas.common import ORMModel


class UserRead(ORMModel):
    id: uuid.UUID
    username: str
    full_name: str
    email: str | None
    is_active: bool


class MeRead(UserRead):
    """Профиль текущего пользователя вместе с ролями из токена."""

    roles: list[str]
