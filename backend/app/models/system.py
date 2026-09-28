"""Системные настройки и служебное состояние.

``app_settings`` - параметры, которые администратор меняет из интерфейса,
а не через переменные окружения: нормы для контроля проблемных процессов.

``alert_marks`` - какие уведомления колокольчика сотрудник прочитал.

``data_version`` - счётчик изменений предметных данных. Каждое сохранение
увеличивает его в той же транзакции, а кэш тяжёлых выборок (главная,
тревоги, отчёты) хранит результат вместе с номером версии. Так кэш
согласован между всеми рабочими процессами API без отдельного сервиса:
версия читается одним запросом по первичному ключу.
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
    """Отметка «прочитано» у уведомления колокольчика.

    Уведомление - не запись в базе, а текущая проблема: его заново вычисляют
    правила app/services/alerts.py. Поэтому прочитанной отмечается проблема
    по её ключу, а отметка помнит, какой важности проблема была: стала
    серьёзнее (лицензия истекла) - уведомление снова новое. Отметки о
    проблемах, которых больше нет, удаляются: вернётся проблема - вернётся
    и уведомление (app/services/alert_marks.py).
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
