"""Настройки, которые администратор меняет из интерфейса.

ТЗ: администратор отвечает за «дополнительные настройки». Здесь собраны
параметры, от которых зависит поведение системы для всех пользователей, -
прежде всего нормы контроля проблемных процессов (раздел 7 концепции).
Значения по умолчанию берутся из переменных окружения, изменённые
администратором - из таблицы ``app_settings``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.models.system import AppSetting


@dataclass(frozen=True, slots=True)
class SettingSpec:
    key: str
    title: str
    description: str
    minimum: int
    maximum: int

    @property
    def default(self) -> int:
        return int(getattr(settings, self.key))


SPECS: tuple[SettingSpec, ...] = (
    SettingSpec(
        "alert_default_sla_days",
        "Норма этапа по умолчанию, дней",
        "Через сколько дней без движения этап считается задержанным, "
        "если у этапа в шаблоне не задан свой срок.",
        1,
        365,
    ),
    SettingSpec(
        "alert_expiring_days",
        "Предупреждать об окончании сроков, дней",
        "За сколько дней до окончания срока договора или лицензии "
        "взаимодействие попадает в список требующих внимания.",
        1,
        365,
    ),
    SettingSpec(
        "integration_sync_interval_hours",
        "Обмен с LMS и сайтом по расписанию, часов",
        "Раз в сколько часов система сама запускает обмен с включёнными "
        "источниками. 0 - только ручной запуск и загрузка ответа файлом.",
        0,
        168,
    ),
)
SPEC_BY_KEY = {spec.key: spec for spec in SPECS}


async def load(session: AsyncSession) -> dict[str, int]:
    """Текущие значения всех настроек: сохранённые или по умолчанию."""
    values = {spec.key: spec.default for spec in SPECS}
    rows = await session.execute(select(AppSetting).where(AppSetting.key.in_(SPEC_BY_KEY)))
    for row in rows.scalars():
        try:
            values[row.key] = int(row.value)
        except (TypeError, ValueError):  # pragma: no cover - руками испорченная запись
            continue
    return values


async def save(
    session: AsyncSession, changes: dict[str, Any], user_id: uuid.UUID
) -> dict[str, int]:
    for key, raw in changes.items():
        spec = SPEC_BY_KEY.get(key)
        if spec is None:
            raise AppError(f"Неизвестная настройка «{key}»", code=ErrorCode.VALIDATION_ERROR)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise AppError(
                f"«{spec.title}»: нужно целое число", code=ErrorCode.VALIDATION_ERROR
            ) from exc
        if not spec.minimum <= value <= spec.maximum:
            raise AppError(
                f"«{spec.title}»: допустимо от {spec.minimum} до {spec.maximum}",
                code=ErrorCode.VALIDATION_ERROR,
            )
        row = await session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=value, updated_by=user_id))
        else:
            row.value = value
            row.updated_by = user_id
    await session.flush()
    return await load(session)
