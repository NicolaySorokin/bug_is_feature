"""Доступ к данным сверх того, что даёт роль.

Менеджер по умолчанию видит договоры, где он ответственный или закреплён
за вузом. Администратор может открыть ему договоры других вузов - например,
на время отпуска коллеги. Такой доступ - строка этой таблицы.
"""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class UserUniversityAccess(CreatedAtMixin, Base):
    __tablename__ = "user_university_access"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"), primary_key=True, index=True
    )
