"""Обмен с LMS и сайтом по расписанию.

Интервал в часах задаёт администратор в «Настройках», 0 значит только вручную.
Процессов API несколько, поэтому обмен запускает тот, кто взял блокировку
в PostgreSQL. Пока источник отдаёт полный снимок, пропавшие из него записи
не удаляются.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionFactory, commit
from app.models.integration import IntegrationRun, IntegrationSource
from app.services import app_settings
from app.services.integrations import sync

logger = logging.getLogger(__name__)

# Как часто проверять, не пора ли обменяться. Точность расписания пять минут.
CHECK_EVERY_SECONDS = 300
# Ключ рекомендательной блокировки: одинаковый у всех процессов API.
LOCK_KEY = 20_260_924


async def due_sources(session: AsyncSession, now: datetime) -> list[str]:
    """Включённые источники, у которых с последнего обмена прошёл интервал.

    Считается любой последний запуск, в том числе ручной. Сначала LMS с программами,
    затем сайт с заявками на них.
    """
    hours = (await app_settings.load(session))["integration_sync_interval_hours"]
    if hours <= 0:
        return []
    last_run = (
        select(IntegrationRun.source_id, func.max(IntegrationRun.started_at).label("started"))
        .group_by(IntegrationRun.source_id)
        .subquery()
    )
    rows = await session.execute(
        select(IntegrationSource.code, last_run.c.started)
        .outerjoin(last_run, last_run.c.source_id == IntegrationSource.id)
        .where(IntegrationSource.is_enabled.is_(True))
    )
    since = now - timedelta(hours=hours)
    due = {code for code, started in rows if started is None or started <= since}
    return [code for code in sync.ADAPTERS if code in due]


async def tick(
    factory: Callable[[], AsyncSession] = SessionFactory, now: datetime | None = None
) -> list[str]:
    """Один проход: обмен по источникам, у которых подошёл срок.

    Возвращает коды источников. Пусто, если срок не подошёл или проверку делает
    другой процесс.
    """
    async with factory() as session:
        locked = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK_KEY}
        )
        if not locked:
            return []
        await sync.ensure_sources(session)
        codes = await due_sources(session, now or datetime.now(UTC))
        for code in codes:
            run = await sync.run_sync(session, code, None, trigger="schedule")
            logger.info("Обмен по расписанию с %s: %s", code, run.status)
        await commit(session)
        return codes


async def run_forever(every: float = CHECK_EVERY_SECONDS) -> None:
    """Цикл планировщика для процесса API. Сбой прохода не останавливает цикл."""
    while True:
        await asyncio.sleep(every)
        try:
            await tick()
        except Exception:  # noqa: BLE001 (сбой одного прохода не должен гасить цикл)
            logger.exception("Обмен по расписанию не выполнен")


@contextlib.asynccontextmanager
async def running():  # noqa: ANN201 (контекстный менеджер жизненного цикла)
    """Фоновая задача планировщика на время жизни приложения."""
    task = asyncio.create_task(run_forever(), name="integration-scheduler")
    try:
        yield task
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
