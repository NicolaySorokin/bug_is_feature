"""Статистика обучения: заявки, потоки, обучающиеся и зачисления.

Заявка студента нужна только для статистики и взаимодействие не создаёт.
Поток опознаётся ключом источника и периодом. Паспорт, СНИЛС, адрес и диплом
не сохраняются (152-ФЗ).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.catalog import ItProgram
from app.models.integration import IntegrationSource


class LearningStream(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Поток обучения по программе."""

    __tablename__ = "learning_streams"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integration_sources.id", ondelete="SET NULL"), nullable=True
    )
    # Стабильный идентификатор потока в источнике. Если источник его не
    # передаёт, ключ собирается из программы, номера и периода набора.
    external_id: Mapped[str] = mapped_column(String(255))
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("it_programs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Период набора: год и полугодие, если дат потока нет.
    period: Mapped[str | None] = mapped_column(String(16), nullable=True)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    program: Mapped[ItProgram | None] = relationship()


class LearningApplication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Заявка студента на обучение, только для статистики."""

    __tablename__ = "learning_applications"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integration_sources.id", ondelete="SET NULL"), nullable=True
    )
    # «Номер заявки» из внешней системы.
    external_id: Mapped[str] = mapped_column(String(100))
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("it_programs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Название курса как пришло: по нему программа сопоставляется.
    course_name: Mapped[str] = mapped_column(String(500))
    stream_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_streams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Номер потока как пришёл, для показа. Поток опознаётся по stream_id.
    stream_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), default="")
    first_name: Mapped[str] = mapped_column(String(100), default="")
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Вуз заявителя, если источник его передал: разрез статистики по вузам.
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("universities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Дата подачи из номера заявки, иначе дата получения.
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    program: Mapped[ItProgram | None] = relationship()
    stream: Mapped[LearningStream | None] = relationship()
    source: Mapped[IntegrationSource | None] = relationship()


class Learner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Обучающийся по данным LMS, только нужное для статистики."""

    __tablename__ = "learners"

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integration_sources.id", ondelete="SET NULL"), nullable=True
    )
    # Идентификатор слушателя в LMS, если она его передаёт.
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), default="")
    first_name: Mapped[str] = mapped_column(String(100), default="")
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # Обезличиваемые признаки для разрезов статистики.
    gender: Mapped[str | None] = mapped_column(String(1), nullable=True)
    education: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Enrollment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Зачисление: обучающийся учится по программе в конкретном потоке."""

    __tablename__ = "enrollments"
    __table_args__ = (
        # Без потока зачисление на программу тоже одно: NULL здесь не «разные».
        UniqueConstraint(
            "learner_id", "program_id", "stream_id", postgresql_nulls_not_distinct=True
        ),
    )

    learner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("it_programs.id", ondelete="CASCADE"), index=True
    )
    stream_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_streams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Заявка, по которой человек пришёл, если связь найдена.
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_applications.id", ondelete="SET NULL"), nullable=True
    )
    # Как найдена связь: lms передала сама, contact по почте или телефону заявки.
    matched_by: Mapped[str] = mapped_column(String(16), default="lms", server_default="lms")

    learner: Mapped[Learner] = relationship()
    program: Mapped[ItProgram] = relationship()
    stream: Mapped[LearningStream | None] = relationship()
