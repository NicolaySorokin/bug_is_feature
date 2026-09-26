"""Точечный доступ к вузу сверх области данных сотрудника.

Менеджер видит свои взаимодействия. Чтобы открыть ему другой вуз - на время
отпуска коллеги или для совместной работы - администратор или руководитель
выдаёт доступ: со сроком, основанием и отметкой, кто выдал. Отзыв не удаляет
запись, а помечает её: так видно, кто и когда закрыл доступ. Каждое
изменение попадает и в журнал изменений.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
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
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Пусто - бессрочно.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
