"""Системные настройки и служебное состояние.

app_settings: нормы, которые администратор меняет в интерфейсе.
alert_marks: прочитанные уведомления.
data_version: счётчик изменений данных для кэша выборок.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class DataVersion(Base):
    __tablename__ = "data_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AlertMark(Base):
    """Отметка «прочитано» у уведомления.

    Уведомление вычисляется заново, поэтому отмечается ключ проблемы вместе
    с её важностью. Стала проблема серьёзнее, и уведомление снова новое.
    """

    __tablename__ = "alert_marks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    alert_key: Mapped[str] = mapped_column(String(300), primary_key=True)
    severity: Mapped[str] = mapped_column(String(16))
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
