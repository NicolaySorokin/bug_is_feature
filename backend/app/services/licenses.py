"""Лицензии: автоматическое истечение срока.

Пункт 22 перечня исправлений: «действующая» лицензия с прошедшим сроком -
противоречие. Статус истекает сам: при каждом чтении реестра, сводки
и отчётов просроченные действующие лицензии переводятся в «Истекла» одним
запросом, а при сохранении лицензии статус сразу приводится к датам.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import mark_changed
from app.enums import LicenseStatus
from app.models.contract import License


def normalize_status(license_: License) -> None:
    """Действующая лицензия с прошедшим сроком сразу считается истёкшей."""
    if (
        license_.status == LicenseStatus.ACTIVE
        and license_.valid_to is not None
        and license_.valid_to < date.today()
    ):
        license_.status = LicenseStatus.EXPIRED


async def expire_overdue(session: AsyncSession) -> int:
    """Переводит в «Истекла» все действующие лицензии с прошедшим сроком."""
    result = await session.execute(
        update(License)
        .where(License.status == LicenseStatus.ACTIVE, License.valid_to < date.today())
        .values(status=LicenseStatus.EXPIRED)
    )
    if result.rowcount:
        mark_changed(session)
    return result.rowcount or 0
