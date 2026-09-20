"""Журнал изменений.

Записи создаются автоматически при сохранении данных (см.
``app.services.audit``). Здесь только чтение и только для администратора:
журнал нужен для разбора инцидентов и требований к регистрации событий
152-ФЗ и приказа ФСТЭК № 117.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import PaginationDep, SessionDep, require_roles
from app.enums import AuditAction, Role
from app.models.audit import AuditLog
from app.schemas.audit import AuditEntryRead
from app.schemas.common import Page

router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(require_roles(Role.ADMIN))],
)


@router.get("", response_model=Page[AuditEntryRead], summary="Журнал изменений")
async def list_entries(
    session: SessionDep,
    pagination: PaginationDep,
    entity_type: str | None = Query(
        default=None, description="Имя таблицы, например contracts"
    ),
    entity_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    action: AuditAction | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[AuditEntryRead]:
    conditions = []
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        conditions.append(AuditLog.entity_id == entity_id)
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if action is not None:
        conditions.append(AuditLog.action == action)
    if date_from is not None:
        conditions.append(cast(AuditLog.created_at, Date) >= date_from)
    if date_to is not None:
        conditions.append(cast(AuditLog.created_at, Date) <= date_to)

    total = (
        await session.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
        or 0
    )
    result = await session.execute(
        select(AuditLog)
        .where(*conditions)
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    return Page(
        items=[AuditEntryRead.from_model(row) for row in result.scalars()],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )
