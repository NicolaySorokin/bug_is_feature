"""Сотрудники ИТ Школы.

Пароли здесь не хранятся: аутентификация живёт в Keycloak, в этой таблице
лежит keycloak_id и данные предметной части. Роли - тоже Keycloak, здесь
только их снимок с последнего входа: по нему администратор видит, кто есть
кто, а руководитель выбирает ответственных из менеджеров.

Права на данные - уже наши (раздел 12 «Решений по бизнес-модели»): роль
задаёт действия, а область данных и точечные доступы - какие
взаимодействия и вузы видны. Область можно поднять временно - со сроком
и основанием; по истечении срока действует область по ролям.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.enums import DataScope


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    keycloak_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Выключенный пользователь не проходит в систему, даже с годным токеном.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Снимок ролей из токена на момент последнего входа.
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default="{}"
    )
    # Дополнительные права сверх роли (enums.Permission).
    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(String(48)), default=list, server_default="{}"
    )
    # Руководитель сотрудника: по этой связи строится область «команда».
    head_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Область бизнес-данных; default - по ролям.
    data_scope: Mapped[str] = mapped_column(
        String(16), default=DataScope.DEFAULT, server_default=DataScope.DEFAULT
    )
    # Область выдана временно: основание и срок. После срока - область по ролям.
    data_scope_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_scope_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - удобство отладки
        return f"<User {self.username}>"
