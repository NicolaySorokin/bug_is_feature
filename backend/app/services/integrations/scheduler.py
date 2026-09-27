"""Обмен с LMS и сайтом по расписанию (пункт 17 перечня исправлений).

Промышленный режим обмена:

* **транспорт** - API источника опрашивается по HTTPS (GET, токен в
  заголовке ``Authorization``); ответ - снимок данных источника;
* **расписание** - интервал в часах задаёт администратор в «Настройках»
  (``integration_sync_interval_hours``); 0 - только ручной запуск и
  загрузка ответа файлом;
* **идемпотентность** - связь ``external_links``: повторный обмен
  обновляет те же записи и не плодит дубли;
* **ошибки** - сбой сети, тайм-аут и ответ 5xx повторяются (три попытки
  с паузой); ошибка отдельной записи не роняет обмен: запуск получает
  статус «частично», запись - строку в журнале запуска;
* **мониторинг** - журнал запусков в разделе «LMS и сайт» и оповещение
  «Ошибка синхронизации» у администратора.

Курсор (выгрузка только изменений) и правила удаления зависят от контракта
API источника: пока источник отдаёт полный снимок, записи, которых в
снимке больше нет, не удаляются.

Рабочих процессов API несколько, а обмен по расписанию должен пройти один
раз: проверку выполняет тот процесс, который получил рекомендательную
блокировку PostgreSQL на время своей транзакции.
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

# Как часто процесс проверяет, не пора ли обменяться. Сам интервал обмена -
# в настройках, в часах; проверка раз в пять минут даёт точность до пяти минут.
CHECK_EVERY_SECONDS = 300
# Ключ рекомендательной блокировки: одинаковый у всех процессов API.
LOCK_KEY = 20_260_924


async def due_sources(session: AsyncSession, now: datetime) -> list[str]:
    """Включённые источники, у которых с последнего обмена прошёл интервал.

    Считается любой последний запуск - ручной, по расписанию или файлом:
    если сотрудник только что обменялся вручную, расписание подождёт.
    Порядок - как в ``sync.ADAPTERS``: сначала LMS с программами, затем
    сайт с заявками на них.
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
    """Один проход: запускает обмен по источникам, у которых подошёл срок.

    Возвращает коды источников, с которыми прошёл обмен (пусто - если срок
    не подошёл или проверку уже выполняет другой процесс).
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
        except Exception:  # noqa: BLE001 - ошибка одного прохода не должна гасить цикл
            logger.exception("Обмен по расписанию не выполнен")


@contextlib.asynccontextmanager
async def running():  # noqa: ANN201 - контекстный менеджер жизненного цикла
    """Фоновая задача планировщика на время жизни приложения."""
    task = asyncio.create_task(run_forever(), name="integration-scheduler")
    try:
        yield task
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
