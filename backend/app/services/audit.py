"""Журнал изменений предметных данных.

Записи не расставлены руками по обработчикам, а собираются на уровне сессии:
перед сохранением SQLAlchemy сообщает, какие объекты добавлены, изменены
и удалены, и по каждому из них пишется строка в ``audit_log``. Поэтому
новый обработчик API попадает в журнал сам, без дополнительного кода.

Кто именно менял данные, берётся из ``current_actor_id`` - переменная
контекста выставляется зависимостью ``get_current_user`` на время запроса.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.enums import AuditAction
from app.models.audit import AuditLog
from app.models.catalog import ItDirection, ItProduct, ItProgram, Vendor
from app.models.contract import (
    Contract,
    ContractContact,
    ContractProduct,
    ContractProgram,
    License,
)
from app.models.integration import IntegrationSource
from app.models.university import University, UniversityContact
from app.models.workflow import (
    WorkflowStage,
    WorkflowTemplate,
    WorkflowTransition,
    WorkflowVersion,
)

current_actor_id: ContextVar[uuid.UUID | None] = ContextVar("current_actor_id", default=None)

# Что попадает в журнал. История рабочего процесса, комментарии и файлы
# сами по себе являются записями о событиях, поэтому не дублируются здесь.
AUDITED_MODELS: tuple[type, ...] = (
    Contract,
    ContractProgram,
    ContractProduct,
    ContractContact,
    License,
    University,
    UniversityContact,
    ItDirection,
    ItProgram,
    Vendor,
    ItProduct,
    WorkflowTemplate,
    WorkflowVersion,
    WorkflowStage,
    WorkflowTransition,
    IntegrationSource,
)

# Поля, которые не несут смысла в журнале.
SKIPPED_FIELDS = frozenset({"created_at", "updated_at"})


def set_actor(user_id: uuid.UUID | None) -> None:
    current_actor_id.set(user_id)


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _entity_type(obj: object) -> str:
    return type(obj).__tablename__  # type: ignore[attr-defined]


def _entity_id(obj: object) -> uuid.UUID | None:
    value = getattr(obj, "id", None)
    return value if isinstance(value, uuid.UUID) else None


def _column_values(obj: object) -> dict[str, Any]:
    mapper = inspect(type(obj))
    return {
        attr.key: _jsonable(getattr(obj, attr.key))
        for attr in mapper.column_attrs
        if attr.key not in SKIPPED_FIELDS
    }


def _changed_values(obj: object) -> tuple[dict[str, Any], dict[str, Any]]:
    """Значения изменившихся полей: до и после."""
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    state = inspect(obj)
    for attr in inspect(type(obj)).column_attrs:
        if attr.key in SKIPPED_FIELDS:
            continue
        history = state.attrs[attr.key].history
        if not history.has_changes():
            continue
        before[attr.key] = _jsonable(history.deleted[0]) if history.deleted else None
        after[attr.key] = _jsonable(history.added[0]) if history.added else None
    return before, after


def _record(
    session: Session,
    obj: object,
    action: AuditAction,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    session.add(
        AuditLog(
            user_id=current_actor_id.get(),
            entity_type=_entity_type(obj),
            entity_id=_entity_id(obj),
            action=action,
            before_data=before,
            after_data=after,
        )
    )


@event.listens_for(Session, "before_flush")
def _write_audit_log(session: Session, _flush_context: Any, _instances: Any) -> None:
    for obj in session.new:
        if not isinstance(obj, AUDITED_MODELS):
            continue
        # Первичный ключ по умолчанию проставляется при сохранении, а журналу
        # идентификатор нужен уже сейчас - задаём его сами. У таблиц-связок
        # (contract_contacts) отдельного id нет, там проставлять нечего.
        if "id" in inspect(type(obj)).columns and getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()  # type: ignore[attr-defined]
        _record(session, obj, AuditAction.CREATE, None, _column_values(obj))

    for obj in session.dirty:
        if not isinstance(obj, AUDITED_MODELS):
            continue
        if not session.is_modified(obj, include_collections=False):
            continue
        before, after = _changed_values(obj)
        if after:
            _record(session, obj, AuditAction.UPDATE, before, after)

    for obj in session.deleted:
        if not isinstance(obj, AUDITED_MODELS):
            continue
        _record(session, obj, AuditAction.DELETE, _column_values(obj), None)
