"""Вузы и их контактные лица.

Раздел 10 списка исправлений: вуз заводят вручную, загрузкой из Excel
и обменом с сайтом, поэтому у записи единый жизненный цикл: ``pending``
(заведён не руководителем - ждёт проверки) -> ``confirmed`` -> ``archived``.
Стабильный бизнес-ключ - ИНН организации; дубли объединяются процедурой
слияния, а поглощённая запись остаётся в архиве со ссылкой на итоговую.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.enums import UniversityStatus
from app.models.user import User


class University(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "universities"

    name: Mapped[str] = mapped_column(String(500), index=True)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # ИНН - стабильный ключ: по нему вуз узнаётся в любом источнике.
    inn: Mapped[str | None] = mapped_column(String(12), nullable=True, unique=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Реквизиты для договора так, как их пишут в договоре: юридический адрес,
    # КПП, ОГРН, банковские реквизиты. Одним текстом - форматы у вузов разные.
    requisites: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Менеджер по умолчанию: правило, кого назначать ответственным за новые
    # взаимодействия этого вуза. Ответственный конкретного процесса хранится
    # на взаимодействии.
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default=UniversityStatus.CONFIRMED,
        server_default=UniversityStatus.CONFIRMED,
        index=True,
    )
    # Откуда запись: manual, import, site, lms - для очереди проверки.
    origin: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Запись поглощена при объединении дублей - ссылка на итоговую.
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("universities.id", ondelete="SET NULL"), nullable=True
    )

    manager: Mapped[User | None] = relationship(foreign_keys=[manager_id])
    contacts: Mapped[list["UniversityContact"]] = relationship(
        back_populates="university",
        cascade="all, delete-orphan",
        order_by="UniversityContact.full_name",
    )

    @property
    def is_active(self) -> bool:
        return self.status != UniversityStatus.ARCHIVED

    @property
    def display_name(self) -> str:
        """Краткое название для компактных мест, полное - если краткого нет."""
        return self.short_name or self.name


class UniversityContact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Контактное лицо хранится на уровне вуза.

    Связь с конкретным взаимодействием задаётся через interaction_contacts,
    поэтому один человек не дублируется для каждого взаимодействия.
    """

    __tablename__ = "university_contacts"

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")

    university: Mapped[University] = relationship(back_populates="contacts")
