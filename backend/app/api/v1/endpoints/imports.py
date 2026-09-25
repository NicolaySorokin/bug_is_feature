"""Загрузка каталогов из XLS и XLSX.

Требование 1 ТЗ: справочники должны актуализироваться подгрузкой файла
через интерфейс по согласованному маппингу полей. Загрузка разбита на шаги
раздела 6.2 концепции: файл - предпросмотр - сопоставление - проверка -
импорт - итог. Доступ только у администратора: импорт меняет общие данные.
"""

import uuid
from datetime import UTC, datetime

import anyio
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserDep, PaginationDep, SessionDep, require_roles
from app.core.errors import ConflictError, NotFoundError
from app.enums import ImportRunStatus, ImportType, Role
from app.models.importing import ImportRowError, ImportRun
from app.schemas.importing import (
    ImportErrorRead,
    ImportFieldInfo,
    ImportMappingRequest,
    ImportPreview,
    ImportResult,
    ImportRunRead,
    ImportTypeInfo,
)
from app.services import imports, storage

router = APIRouter(
    prefix="/imports",
    tags=["imports"],
    dependencies=[Depends(require_roles(Role.ADMIN))],
)

SPREADSHEETS = ("xls", "xlsx")


def _fields(spec: imports.ImportSpec) -> list[ImportFieldInfo]:
    return [
        ImportFieldInfo(
            key=item.key,
            title=item.title,
            aliases=list(item.aliases),
            required=item.required,
        )
        for item in spec.fields
    ]


def _spec(import_type: ImportType) -> imports.ImportSpec:
    spec = imports.SPECS.get(import_type)
    if spec is None:  # pragma: no cover - значение ограничено перечислением
        raise NotFoundError("Неизвестный тип импорта")
    return spec


async def _get_run(session: SessionDep, run_id: uuid.UUID) -> ImportRun:
    statement = (
        select(ImportRun).where(ImportRun.id == run_id).options(selectinload(ImportRun.errors))
    )
    run = (await session.execute(statement)).scalar_one_or_none()
    if run is None:
        raise NotFoundError("Загрузка не найдена")
    return run


def _result(run: ImportRun, errors: list[ImportErrorRead]) -> ImportResult:
    return ImportResult(run=ImportRunRead.model_validate(run), errors=errors)


async def _replace_errors(
    session: SessionDep, run: ImportRun, errors: list[imports.RowError]
) -> list[ImportErrorRead]:
    """Ошибки прошлой проверки заменяются целиком: они относились к прошлому запуску."""
    for existing in list(run.errors):
        await session.delete(existing)
    run.errors.clear()

    for error in errors:
        session.add(
            ImportRowError(
                import_run_id=run.id,
                row_number=error.row_number,
                field_name=error.field_name,
                message=error.message,
            )
        )
    await session.flush()
    return [
        ImportErrorRead(
            row_number=error.row_number, field_name=error.field_name, message=error.message
        )
        for error in errors
    ]


def _mapping(run: ImportRun, payload: ImportMappingRequest) -> dict[str, str | None]:
    return payload.mapping or dict(run.mapping or {})


def _ensure_not_imported(run: ImportRun) -> None:
    # Повторный импорт того же файла ничего не испортит, но исказит итог
    # загрузки в журнале: для повтора файл загружают заново.
    if run.status == ImportRunStatus.COMPLETED:
        raise ConflictError(
            "Этот файл уже импортирован. Чтобы повторить, загрузите его заново"
        )


async def _read(storage_path: str) -> imports.SheetData:
    # Разбор книги - работа процессора: выносим из цикла событий.
    return await anyio.to_thread.run_sync(
        imports.read_sheet, storage.absolute_path(storage_path)
    )


@router.get("/types", response_model=list[ImportTypeInfo], summary="Типы загрузок")
async def list_types(_: CurrentUserDep) -> list[ImportTypeInfo]:
    return [
        ImportTypeInfo(
            import_type=spec.import_type,
            title=spec.title,
            description=spec.description,
            fields=_fields(spec),
        )
        for spec in imports.SPECS.values()
    ]


@router.get(
    "/template",
    summary="Файл-образец с заголовками",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def download_template(
    _: CurrentUserDep,
    import_type: ImportType = Query(default=ImportType.CATALOG, alias="type"),
) -> Response:
    spec = _spec(import_type)
    return Response(
        content=imports.build_template(spec),
        media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        headers={
            "Content-Disposition": f'attachment; filename="template-{import_type.value}.xlsx"'
        },
    )


@router.get("", response_model=list[ImportRunRead], summary="История загрузок")
async def list_runs(
    session: SessionDep, pagination: PaginationDep, _: CurrentUserDep
) -> list[ImportRunRead]:
    result = await session.execute(
        select(ImportRun)
        .order_by(ImportRun.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    return [ImportRunRead.model_validate(row) for row in result.scalars()]


@router.post(
    "",
    response_model=ImportPreview,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить файл и получить предпросмотр",
    description=(
        "Файл сохраняется, показываются его заголовки, первые строки "
        "и предложенное сопоставление колонок. Данные при этом не меняются."
    ),
)
async def upload(
    session: SessionDep,
    user: CurrentUserDep,
    file: UploadFile = File(description="Файл XLS или XLSX"),
    import_type: ImportType = Form(default=ImportType.CATALOG, alias="type"),
) -> ImportPreview:
    spec = _spec(import_type)
    stored = await storage.save_upload(file, "imports", allowed=SPREADSHEETS)

    sheet = await _read(stored.storage_path)
    mapping = imports.suggest_mapping(spec, sheet.headers)

    run = ImportRun(
        uploaded_by=user.id,
        filename=stored.original_name,
        storage_path=stored.storage_path,
        import_type=import_type,
        status=ImportRunStatus.UPLOADED,
        mapping=mapping,
        rows_total=len(sheet.rows),
    )
    session.add(run)
    await session.flush()

    return ImportPreview(
        run=ImportRunRead.model_validate(run),
        headers=sheet.headers,
        suggested_mapping=mapping,
        sample_rows=[
            [imports.cell_text(cell) for cell in row]
            for row in sheet.rows[: imports.MAX_PREVIEW_ROWS]
        ],
        rows_total=len(sheet.rows),
        fields=_fields(spec),
    )


@router.get("/{run_id}", response_model=ImportResult, summary="Загрузка и её ошибки")
async def read_run(run_id: uuid.UUID, session: SessionDep, _: CurrentUserDep) -> ImportResult:
    run = await _get_run(session, run_id)
    return _result(
        run,
        [
            ImportErrorRead(
                row_number=error.row_number,
                field_name=error.field_name,
                message=error.message,
            )
            for error in run.errors
        ],
    )


@router.post(
    "/{run_id}/validate",
    response_model=ImportResult,
    summary="Проверить данные перед импортом",
    description=(
        "Пробная загрузка с откатом: сколько строк будет добавлено и обновлено, "
        "какие строки не пройдут и почему. Данные не меняются."
    ),
)
async def validate(
    run_id: uuid.UUID,
    payload: ImportMappingRequest,
    session: SessionDep,
    _: CurrentUserDep,
) -> ImportResult:
    run = await _get_run(session, run_id)
    _ensure_not_imported(run)
    spec = _spec(ImportType(run.import_type))
    sheet = await _read(run.storage_path)

    mapping = _mapping(run, payload)
    # Пробная загрузка в точке сохранения с откатом: видно, сколько строк
    # добавится и обновится и какие строки не пройдут, а данные не меняются.
    savepoint = await session.begin_nested()
    try:
        outcome = await imports.run_import(session, spec, sheet, mapping)
    finally:
        await savepoint.rollback()

    run.mapping = mapping
    run.rows_total = len(sheet.rows)
    loadable = outcome.created + outcome.updated
    run.status = ImportRunStatus.VALIDATED if loadable else ImportRunStatus.FAILED
    result = _result(run, await _replace_errors(session, run, outcome.errors))
    # Прогноз - только в ответе: счётчики запуска заполняет настоящая загрузка.
    result.run.rows_created = outcome.created
    result.run.rows_updated = outcome.updated
    result.run.rows_failed = outcome.failed
    return result


@router.post(
    "/{run_id}/commit",
    response_model=ImportResult,
    summary="Выполнить импорт",
    description=(
        "Строки с ошибками пропускаются, остальные загружаются. "
        "В итоге видно, сколько записей создано, обновлено и отклонено."
    ),
)
async def commit(
    run_id: uuid.UUID,
    payload: ImportMappingRequest,
    session: SessionDep,
    _: CurrentUserDep,
) -> ImportResult:
    run = await _get_run(session, run_id)
    _ensure_not_imported(run)
    spec = _spec(ImportType(run.import_type))
    sheet = await _read(run.storage_path)

    mapping = _mapping(run, payload)
    outcome = await imports.run_import(session, spec, sheet, mapping)

    run.mapping = mapping
    run.rows_total = len(sheet.rows)
    run.rows_created = outcome.created
    run.rows_updated = outcome.updated
    run.rows_failed = outcome.failed
    run.status = ImportRunStatus.COMPLETED
    run.finished_at = datetime.now(UTC)
    return _result(run, await _replace_errors(session, run, outcome.errors))
