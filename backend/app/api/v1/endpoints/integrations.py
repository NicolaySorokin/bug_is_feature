"""Обмен с LMS и сайтом ИТ Школы.

Раздел «LMS и сайт» интерфейса: состояние источников, ручной запуск
синхронизации, журнал запусков с ошибками по записям и очередь ручного
сопоставления.

Это технический раздел (пункт 28 перечня исправлений): журнал видят
администратор и сотрудники с правом «Журнал обмена», запускают обмен -
администратор и сотрудники с правом «Запуск обмена». Бизнес-пользователи
видят результаты обмена там, где они касаются их данных, - в карточке
взаимодействия (заявка вуза приходит комментарием).
"""

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentUserDep,
    PaginationDep,
    PrincipalDep,
    SessionDep,
    require_action,
)
from app.core.config import settings
from app.core.errors import AppError, ConflictError, ErrorCode, NotFoundError
from app.enums import MappingStatus, UniversityStatus
from app.models.catalog import ItProduct, ItProgram
from app.models.integration import IntegrationMapping, IntegrationRun, IntegrationSource
from app.models.university import University
from app.schemas.integration import (
    IntegrationRunRead,
    IntegrationSourceRead,
    IntegrationSourceUpdate,
    MappingRead,
    MappingResolve,
)
from app.services.access import Action
from app.services.integrations import sync

router = APIRouter(prefix="/integrations", tags=["integrations"])
log_readers = [
    require_action(
        Action.VIEW_INTEGRATION_LOG,
        "Журнал обмена - администратору и по праву «Журнал обмена»",
    )
]
runners = [
    require_action(
        Action.SYNC_INTEGRATIONS, "Запуск обмена - администратору и по праву «Запуск обмена»"
    )
]
resolvers = [require_action(Action.RESOLVE_MAPPINGS, "Сопоставление ведёт администратор")]

MODELS = {
    sync.PROGRAM: ItProgram,
    sync.PRODUCT: ItProduct,
    sync.UNIVERSITY: University,
    sync.COURSE: ItProgram,
}


def _to_source_read(source: IntegrationSource) -> IntegrationSourceRead:
    model = IntegrationSourceRead.model_validate(source)
    model.uses_fixture = not source.base_url
    return model


@router.get(
    "/sources",
    response_model=list[IntegrationSourceRead],
    dependencies=log_readers,
    summary="Источники данных",
    description=(
        "Если адрес источника не задан, адаптер отдаёт тестовые данные - "
        "контракты API LMS и сайта организаторы предоставляют в ходе работы."
    ),
)
async def list_sources(session: SessionDep) -> list[IntegrationSourceRead]:
    sources = await sync.ensure_sources(session)
    return [_to_source_read(source) for source in sources]


@router.patch(
    "/sources/{code}",
    response_model=IntegrationSourceRead,
    dependencies=runners,
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
    dependencies=runners,
    summary="Запустить синхронизацию",
    description=(
        "Обновляет справочники, вузы и статистику обучения; заявки вузов "
        "добавляет в открытые взаимодействия или заводит взаимодействия-черновики. "
        "Повторный запуск дублей не создаёт. Ошибки отдельных записей не роняют "
        "обмен: запуск получает статус partial и список ошибок."
    ),
)
async def run_sync(code: str, session: SessionDep, user: CurrentUserDep) -> IntegrationRunRead:
    run = await sync.run_sync(session, code, user)
    return IntegrationRunRead.from_model(run, code)


@router.post(
    "/sources/{code}/upload",
    response_model=IntegrationRunRead,
    dependencies=runners,
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
    dependencies=runners,
    summary="Синхронизировать все включённые источники",
    description=(
        "Сначала LMS с программами, затем сайт с заявками на эти программы. "
        "Выключенные источники пропускаются."
    ),
)
async def run_all(session: SessionDep, user: CurrentUserDep) -> list[IntegrationRunRead]:
    enabled = {
        source.code for source in await sync.ensure_sources(session) if source.is_enabled
    }
    runs = [
        (code, await sync.run_sync(session, code, user))
        for code in sync.ADAPTERS
        if code in enabled
    ]
    return [IntegrationRunRead.from_model(run, code) for code, run in runs]


@router.get(
    "/runs",
    response_model=list[IntegrationRunRead],
    dependencies=log_readers,
    summary="Журнал синхронизаций",
)
async def list_runs(
    session: SessionDep,
    pagination: PaginationDep,
    source_code: str | None = Query(default=None, alias="source"),
) -> list[IntegrationRunRead]:
    runs = await sync.list_runs(session, source_code, pagination.limit, pagination.offset)
    return [IntegrationRunRead.from_model(run) for run in runs]


# --- Ручное сопоставление ----------------------------------------------------------


async def _names(session: SessionDep, entity_type: str, ids: set[uuid.UUID]) -> dict:
    model = MODELS.get(entity_type)
    if model is None or not ids:
        return {}
    rows = await session.execute(select(model.id, model.name).where(model.id.in_(ids)))
    return dict(rows.all())


async def _read(session: SessionDep, mapping: IntegrationMapping) -> MappingRead:
    source = await session.get(IntegrationSource, mapping.source_id)
    ids = {item for item in (mapping.suggested_entity_id, mapping.entity_id) if item}
    names = await _names(session, mapping.entity_type, ids)
    return MappingRead(
        id=mapping.id,
        source_code=source.code if source else "",
        entity_type=mapping.entity_type,
        entity_title=sync.ENTITY_TITLES.get(mapping.entity_type, mapping.entity_type),
        external_id=mapping.external_id,
        external_name=mapping.external_name,
        payload=mapping.payload,
        suggested_entity_id=mapping.suggested_entity_id,
        suggested_name=names.get(mapping.suggested_entity_id),
        status=mapping.status,
        entity_id=mapping.entity_id,
        entity_name=names.get(mapping.entity_id),
        created_at=mapping.created_at,
        resolved_at=mapping.resolved_at,
    )


async def _get_mapping(session: SessionDep, mapping_id: uuid.UUID) -> IntegrationMapping:
    mapping = await session.get(IntegrationMapping, mapping_id)
    if mapping is None:
        raise NotFoundError("Запись очереди сопоставления не найдена")
    if mapping.status != MappingStatus.PENDING:
        raise ConflictError("По этой записи решение уже принято")
    return mapping


@router.get(
    "/mappings",
    response_model=list[MappingRead],
    dependencies=resolvers,
    summary="Очередь ручного сопоставления",
    description=(
        "Внешние записи, которые система не сопоставила сама: в системе есть "
        "запись с таким же названием, а внешнего идентификатора у неё нет. "
        "Пока решения нет, запись не загружается."
    ),
)
async def list_mappings(
    session: SessionDep,
    mapping_status: MappingStatus | None = Query(
        default=MappingStatus.PENDING, alias="status"
    ),
) -> list[MappingRead]:
    statement = select(IntegrationMapping).order_by(IntegrationMapping.created_at.desc())
    if mapping_status is not None:
        statement = statement.where(IntegrationMapping.status == mapping_status)
    rows = (await session.execute(statement.limit(500))).scalars()
    return [await _read(session, row) for row in rows]


async def _finish(
    session: SessionDep, mapping: IntegrationMapping, entity_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    await sync.remember(
        session, mapping.source_id, mapping.entity_type, entity_id, mapping.external_id
    )
    if mapping.entity_type == sync.COURSE:
        await sync.apply_course_mapping(
            session, mapping.source_id, mapping.external_id, entity_id
        )
    mapping.status = MappingStatus.RESOLVED
    mapping.entity_id = entity_id
    mapping.resolved_by_id = user_id
    mapping.resolved_at = datetime.now(UTC)
    await session.flush()


@router.post(
    "/mappings/{mapping_id}/resolve",
    response_model=MappingRead,
    dependencies=resolvers,
    summary="Сопоставить с существующей записью",
    description="Следующий обмен обновит выбранную запись, а не заведёт новую.",
)
async def resolve_mapping(
    mapping_id: uuid.UUID, payload: MappingResolve, session: SessionDep, user: CurrentUserDep
) -> MappingRead:
    mapping = await _get_mapping(session, mapping_id)
    model = MODELS.get(mapping.entity_type)
    if model is None or await session.get(model, payload.entity_id) is None:
        raise NotFoundError("Запись системы для сопоставления не найдена")
    await _finish(session, mapping, payload.entity_id, user.id)
    return await _read(session, mapping)


@router.post(
    "/mappings/{mapping_id}/create",
    response_model=MappingRead,
    dependencies=resolvers,
    summary="Завести новую запись",
    description="Это другая запись, не та, что предложила система: завести её в справочник.",
)
async def create_from_mapping(
    mapping_id: uuid.UUID, session: SessionDep, user: CurrentUserDep, principal: PrincipalDep
) -> MappingRead:
    mapping = await _get_mapping(session, mapping_id)
    data = {"name": mapping.external_name, **(mapping.payload or {})}
    if mapping.entity_type in (sync.PROGRAM, sync.COURSE):
        entity = await sync.create_program(session, data)
    elif mapping.entity_type == sync.PRODUCT:
        entity = await sync.create_product(session, data)
    elif mapping.entity_type == sync.UNIVERSITY:
        entity = await sync.create_university(session, data, "integration")
        # Администратор принял решение - вуз подтверждён.
        entity.status = UniversityStatus.CONFIRMED
        entity.confirmed_by_id = user.id
        entity.confirmed_at = datetime.now(UTC)
        await sync.sync_contacts(session, entity, data.get("contacts") or [])
    else:  # pragma: no cover - других типов в очереди нет
        raise ConflictError("Для этого типа записи завести новую нельзя")
    await _finish(session, mapping, entity.id, user.id)
    return await _read(session, mapping)


@router.post(
    "/mappings/{mapping_id}/ignore",
    response_model=MappingRead,
    dependencies=resolvers,
    summary="Не загружать запись",
    description="Запись источника не нужна системе: следующие обмены её пропустят.",
)
async def ignore_mapping(
    mapping_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> MappingRead:
    mapping = await _get_mapping(session, mapping_id)
    mapping.status = MappingStatus.IGNORED
    mapping.resolved_by_id = user.id
    mapping.resolved_at = datetime.now(UTC)
    await session.flush()
    return await _read(session, mapping)


@router.get(
    "/runs/{run_id}",
    response_model=IntegrationRunRead,
    dependencies=log_readers,
    summary="Запуск синхронизации с ошибками по записям",
)
async def read_run(run_id: uuid.UUID, session: SessionDep) -> IntegrationRunRead:
    run = await session.scalar(
        select(IntegrationRun)
        .where(IntegrationRun.id == run_id)
        .options(selectinload(IntegrationRun.source), selectinload(IntegrationRun.errors))
    )
    if run is None:
        raise NotFoundError("Запуск не найден")
    return IntegrationRunRead.from_model(run)
