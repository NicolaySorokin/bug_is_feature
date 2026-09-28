"""Сборка файлов выгрузки так, чтобы интерфейс не ждал.

Каждый процесс API собирает не больше EXPORT_CONCURRENCY файлов сразу,
остальные ждут в очереди. Поток сборки работает с пониженным приоритетом,
поэтому запросы интерфейса не тормозят даже при десяти отчётах сразу.
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
    # В Linux приоритет задаётся каждому потоку отдельно.
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
        # Поток вернётся в общий пул, поэтому возвращаем обычный приоритет. Без прав
        # на это поток так и останется фоновым.
        if lowered:
            _set_thread_priority(0)


async def run(function: Callable[..., T], *args: Any) -> T:
    """Собирает файл в фоновом потоке с очередью и низким приоритетом."""
    return await anyio.to_thread.run_sync(_in_background, function, *args, limiter=_limiter())
