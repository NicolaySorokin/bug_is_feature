"""Сборка файлов выгрузки так, чтобы интерфейс не ждал.

PDF, диаграммы и таблицы Excel собираются процессором сотни миллисекунд.
Если десять человек одновременно выгружают отчёты (нефункциональное
требование 7 ТЗ), такие сборки занимают весь процессор, и обычные
запросы интерфейса - переход по этапу, фильтр реестра - ждут их
(требование 1: не дольше секунды). Поэтому:

- в одном рабочем процессе API одновременно собирается не больше
  ``EXPORT_CONCURRENCY`` файлов, остальные выгрузки ждут очереди - они
  всё равно выполнятся, просто по порядку;
- поток сборки работает с пониженным приоритетом: когда процессор
  нужен и запросу интерфейса, и выгрузке, система отдаёт его запросу.
"""

from __future__ import annotations

import asyncio
import os
import threading
import weakref
from collections.abc import Callable
from typing import Any, TypeVar

import anyio

from app.core.config import settings

T = TypeVar("T")

# Очередь выгрузок своя у каждого цикла событий (в тестах их много).
_limiters: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, anyio.CapacityLimiter] = (
    weakref.WeakKeyDictionary()
)

NICE = 10


def _limiter() -> anyio.CapacityLimiter:
    loop = asyncio.get_running_loop()
    limiter = _limiters.get(loop)
    if limiter is None:
        limiter = anyio.CapacityLimiter(max(1, settings.export_concurrency))
        _limiters[loop] = limiter
    return limiter


def _set_thread_priority(value: int) -> bool:
    # В Linux приоритет задаётся каждому потоку отдельно (поток - задача ядра).
    try:
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), value)
    except (AttributeError, OSError):
        return False
    return True


def _in_background(function: Callable[..., T], *args: Any) -> T:
    lowered = _set_thread_priority(NICE)
    try:
        return function(*args)
    finally:
        # Поток вернётся в общий пул - возвращаем обычный приоритет (если
        # процессу это разрешено; без прав поток так и останется фоновым).
        if lowered:
            _set_thread_priority(0)


async def run(function: Callable[..., T], *args: Any) -> T:
    """Выполнить сборку файла в фоновом потоке с очередью и низким приоритетом."""
    return await anyio.to_thread.run_sync(_in_background, function, *args, limiter=_limiter())
