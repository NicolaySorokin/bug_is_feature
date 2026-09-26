"""Системные настройки: читать может любой сотрудник, менять - администратор."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, SessionDep, require_roles
from app.enums import Role
from app.services import app_settings, cache

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingRead(BaseModel):
    key: str
    title: str
    description: str
    value: int
    default: int
    minimum: int
    maximum: int


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


def _read(values: dict[str, int]) -> list[SettingRead]:
    return [
        SettingRead(
            key=spec.key,
            title=spec.title,
            description=spec.description,
            value=values[spec.key],
            default=spec.default,
            minimum=spec.minimum,
            maximum=spec.maximum,
        )
        for spec in app_settings.SPECS
    ]


@router.get("", response_model=list[SettingRead], summary="Системные настройки")
async def read_settings(session: SessionDep, _: CurrentUserDep) -> list[SettingRead]:
    return _read(await app_settings.load(session))


@router.put(
    "",
    response_model=list[SettingRead],
    dependencies=[Depends(require_roles(Role.ADMIN))],
    summary="Изменить системные настройки",
)
async def update_settings(
    payload: SettingsUpdate, session: SessionDep, user: CurrentUserDep
) -> list[SettingRead]:
    return _read(await app_settings.save(session, payload.values, user.id))


@router.get(
    "/cache",
    dependencies=[Depends(require_roles(Role.ADMIN))],
    summary="Состояние кэша выборок",
    include_in_schema=False,
)
async def cache_state(session: SessionDep) -> dict[str, object]:
    """Версия данных и попадания в кэш рабочего процесса, ответившего на запрос."""
    return {"version": await cache.current_version(session), **cache.stats()}
