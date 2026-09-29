"""Сборка файлов выгрузки так, чтобы интерфейс не ждал.

Каждый процесс API собирает не больше EXPORT_CONCURRENCY файлов сразу,
остальные ждут в очереди. Файл собирается в отдельном процессе с пониженным
приоритетом: в потоке API сборка держала бы GIL и тормозила интерфейс.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import weakref
from collections.abc import Callable
from typing import Any, TypeVar

import anyio
import anyio.to_process

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


def _in_background(function: Callable[..., T], *args: Any) -> T:
    # Процесс служит только выгрузкам, приоритет не возвращаем.
    with contextlib.suppress(AttributeError, OSError):
        os.setpriority(os.PRIO_PROCESS, 0, NICE)
    return function(*args)


async def run(function: Callable[..., T], *args: Any) -> T:
    """Собирает файл в отдельном процессе с очередью и низким приоритетом.

    Функция и аргументы уходят в процесс через pickle, поэтому функция
    объявлена на уровне модуля.
    """
    return await anyio.to_process.run_sync(_in_background, function, *args, limiter=_limiter())
