"""Обмен с LMS и сайтом ИТ Школы.

Раздел «Интеграции» интерфейса: состояние источников, ручной запуск
синхронизации и журнал запусков с ошибками. Запуск доступен руководителю
и администратору - это действие меняет общие справочники.
"""

import json

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.deps import CurrentUserDep, PaginationDep, SessionDep, require_roles
from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.enums import Role
from app.models.integration import IntegrationSource
from app.schemas.integration import (
    IntegrationRunRead,
    IntegrationSourceRead,
    IntegrationSourceUpdate,
)
from app.services.integrations import sync

router = APIRouter(prefix="/integrations", tags=["integrations"])
staff_only = [Depends(require_roles(Role.HEAD, Role.ADMIN))]


def _to_source_read(source: IntegrationSource) -> IntegrationSourceRead:
    model = IntegrationSourceRead.model_validate(source)
    model.uses_fixture = not source.base_url
    return model


@router.get(
    "/sources",
    response_model=list[IntegrationSourceRead],
    summary="Источники данных",
    description=(
        "Если адрес источника не задан, адаптер отдаёт тестовые данные - "
        "контракты API LMS и сайта организаторы предоставляют в ходе работы."
    ),
)
async def list_sources(session: SessionDep, _: CurrentUserDep) -> list[IntegrationSourceRead]:
    sources = await sync.ensure_sources(session)
    return [_to_source_read(source) for source in sources]


@router.patch(
    "/sources/{code}",
    response_model=IntegrationSourceRead,
    dependencies=[Depends(require_roles(Role.ADMIN))],
    summary="Включить или выключить источник",
)
async def update_source(
    code: str, payload: IntegrationSourceUpdate, session: SessionDep
) -> IntegrationSourceRead:
    source = await sync.get_source(session, code)
    source.is_enabled = payload.is_enabled
    await session.flush()
    return _to_source_read(source)


@router.post(
    "/sources/{code}/sync",
    response_model=IntegrationRunRead,
    dependencies=staff_only,
    summary="Запустить синхронизацию",
    description=(
        "Обновляет справочники и вузы, а по новым заявкам заводит договор "
        "и запускает рабочий процесс. Повторный запуск дублей не создаёт."
    ),
)
async def run_sync(code: str, session: SessionDep, user: CurrentUserDep) -> IntegrationRunRead:
    run = await sync.run_sync(session, code, user)
    return IntegrationRunRead.from_model(run, code)


@router.post(
    "/sources/{code}/upload",
    response_model=IntegrationRunRead,
    dependencies=staff_only,
    summary="Загрузить ответ источника файлом JSON",
    description=(
        "Ответ API LMS или сайта, сохранённый в файл, разбирается тем же "
        "адаптером, что и ответ по сети: так проверяется выгрузка до того, "
        "как открыт сетевой доступ к источнику. Формат сайта - список заявок "
        "с полями «Номер заявки», «Курс», «Фамилия», «Имя», «Отчество», "
        "«Телефон», «Email», «Номер потока»."
    ),
)
async def upload_payload(
    code: str,
    session: SessionDep,
    user: CurrentUserDep,
    file: UploadFile = File(description="Файл JSON с ответом источника"),
) -> IntegrationRunRead:
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise AppError(
            f"Файл больше допустимых {settings.max_upload_mb} МБ",
            code=ErrorCode.FILE_TOO_LARGE,
            status_code=413,
        )
    try:
        raw = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(
            f"Файл не похож на JSON: {exc}", code=ErrorCode.INTEGRATION_FAILED
        ) from exc
    run = await sync.run_sync(session, code, user, raw=raw, filename=file.filename)
    return IntegrationRunRead.from_model(run, code)


@router.post(
    "/sync",
    response_model=list[IntegrationRunRead],
    dependencies=staff_only,
    summary="Синхронизировать все источники",
    description="Сначала LMS с программами, затем сайт с заявками на эти программы.",
)
async def run_all(session: SessionDep, user: CurrentUserDep) -> list[IntegrationRunRead]:
    runs = [(code, await sync.run_sync(session, code, user)) for code in sync.ADAPTERS]
    return [IntegrationRunRead.from_model(run, code) for code, run in runs]


@router.get(
    "/runs",
    response_model=list[IntegrationRunRead],
    summary="Журнал синхронизаций",
)
async def list_runs(
    session: SessionDep,
    pagination: PaginationDep,
    _: CurrentUserDep,
    source_code: str | None = Query(default=None, alias="source"),
) -> list[IntegrationRunRead]:
    runs = await sync.list_runs(session, source_code, pagination.limit, pagination.offset)
    return [IntegrationRunRead.from_model(run) for run in runs]
