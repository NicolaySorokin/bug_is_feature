"""Прочитанные уведомления колокольчика.

«Прочитано» только снимает уведомление со счётчика, проблема остаётся на
главной, пока её не решат. Отметка помнит важность: стала проблема серьёзнее,
и уведомление снова новое. Отметки пишутся мимо ORM, чтобы не сбрасывать кэш.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AlertSeverity
from app.models.system import AlertMark
from app.models.user import User
from app.services.alerts import SEVERITY_ORDER, Alert


def still_read(marked: str, current: AlertSeverity) -> bool:
    """Прочитанное остаётся прочитанным, пока проблема не стала серьёзнее."""
    try:
        was = AlertSeverity(marked)
    except ValueError:
        return False
    return SEVERITY_ORDER[current] >= SEVERITY_ORDER[was]


async def read_keys(
    session: AsyncSession, user: User, alerts: list[Alert], *, prune: bool = False
) -> set[str]:
    """Ключи уведомлений, которые сотрудник уже прочитал.

    prune заодно удаляет отметки о решённых проблемах, поэтому нужен полный
    список уведомлений, а не отобранный по видам.
    """
    rows = await session.execute(
        select(AlertMark.alert_key, AlertMark.severity).where(AlertMark.user_id == user.id)
    )
    marks = dict(rows.tuples().all())
    current = {alert.key: alert for alert in alerts}
    if prune:
        gone = [key for key in marks if key not in current]
        if gone:
            await session.execute(
                delete(AlertMark).where(
                    AlertMark.user_id == user.id, AlertMark.alert_key.in_(gone)
                )
            )
    return {
        key
        for key, severity in marks.items()
        if key in current and still_read(severity, current[key].severity)
    }


async def mark_read(
    session: AsyncSession, user: User, alerts: list[Alert], keys: set[str] | None = None
) -> int:
    """Отмечает прочитанными уведомления с этими ключами, без ключей все.

    Возвращает, сколько уведомлений отмечено.
    """
    chosen = {alert.key: alert for alert in alerts if keys is None or alert.key in keys}
    if not chosen:
        return 0
    now = datetime.now(UTC)
    statement = insert(AlertMark).values(
        [
            {
                "user_id": user.id,
                "alert_key": key,
                "severity": alert.severity.value,
                "read_at": now,
            }
            for key, alert in chosen.items()
        ]
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[AlertMark.user_id, AlertMark.alert_key],
            set_={"severity": statement.excluded.severity, "read_at": now},
        )
    )
    return len(chosen)
