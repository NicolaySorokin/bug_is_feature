"""Кэш тяжёлых выборок - требование 13 ТЗ «кэш работы действий пользователя».

Главная, тревоги и отчёты собираются из всех видимых пользователю
взаимодействий с процессами, составом и договорами. Пересчитывать это
на каждый заход дорого, а данные меняются куда реже, чем их смотрят.
Поэтому результат кладётся в кэш рабочего процесса API.

Согласованность обеспечивает счётчик изменений ``data_version``: любое
сохранение предметных данных увеличивает его в той же транзакции
(см. ``app.db.session``). Ключ кэша включает номер версии, поэтому после
изменения старые записи просто перестают совпадать - ни один процесс API
не отдаст данные, устаревшие относительно базы. Проверка версии - один
запрос по первичному ключу вместо пересборки выборки.

Срок жизни записи ограничен (``CACHE_TTL_SECONDS``): часть значений зависит
от текущего времени, например «дней на этапе».
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.system import DataVersion

T = TypeVar("T")

MAX_ENTRIES = 512
_VERSION_ROW = 1

_entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_stats = {"hits": 0, "misses": 0}


async def current_version(session: AsyncSession) -> int:
    version = await session.scalar(
        select(DataVersion.version).where(DataVersion.id == _VERSION_ROW)
    )
    return int(version or 0)


async def bump_version(session: AsyncSession) -> None:
    """Отмечает, что данные изменились. Вызывается перед фиксацией транзакции."""
    statement = pg_insert(DataVersion).values(id=_VERSION_ROW, version=1)
    statement = statement.on_conflict_do_update(
        index_elements=[DataVersion.id],
        set_={"version": DataVersion.version + 1, "updated_at": func.now()},
    )
    await session.execute(statement)


def make_key(namespace: str, *parts: Any) -> str:
    """Ключ из произвольных частей: пользователь, роли, фильтры запроса."""
    raw = json.dumps(parts, default=str, sort_keys=True, ensure_ascii=False)
    return f"{namespace}:{hashlib.sha256(raw.encode()).hexdigest()}"


async def cached(
    session: AsyncSession,
    key: str,
    build: Callable[[], Awaitable[T]],
) -> T:
    """Возвращает значение из кэша или строит его и запоминает."""
    ttl = settings.cache_ttl_seconds
    if ttl <= 0:
        return await build()

    full_key = f"{await current_version(session)}:{key}"
    now = time.monotonic()
    entry = _entries.get(full_key)
    if entry is not None and entry[0] > now:
        _entries.move_to_end(full_key)
        _stats["hits"] += 1
        return entry[1]

    _stats["misses"] += 1
    value = await build()
    _entries[full_key] = (now + ttl, value)
    _entries.move_to_end(full_key)
    while len(_entries) > MAX_ENTRIES:
        _entries.popitem(last=False)
    return value


def clear() -> None:
    _entries.clear()
    _stats.update(hits=0, misses=0)


def stats() -> dict[str, int]:
    return {"entries": len(_entries), **_stats}
