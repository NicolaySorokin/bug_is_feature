"""Отчёты и диаграммы.

Фильтры передаются телом запроса: списков идентификаторов бывает много,
в строке запроса они не помещаются. Один и тот же запрос даёт и данные
для экрана (``/preview``), и файл (``/export``), и отдельную диаграмму
(``/chart``) - выборка при этом считается одинаково.
"""

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentUserDep, PrincipalDep, SessionDep
from app.core.errors import AppError, ErrorCode
from app.schemas.report import (
    COLUMN_TITLES,
    DEFAULT_COLUMNS,
    ChartKey,
    ColumnInfo,
    ExportFormat,
    ImageFormat,
    ReportRequest,
    ReportResponse,
)
from app.services import reports
from app.services.export import charts as chart_export
from app.services.export import pdf as pdf_export
from app.services.export import xlsx as xlsx_export

router = APIRouter(prefix="/reports", tags=["reports"])

CONTENT_TYPES = {
    ExportFormat.XLSX: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    ExportFormat.XLS: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    ExportFormat.PDF: ("application/pdf", "pdf"),
    ExportFormat.JSON: ("application/json", "json"),
}


@router.get(
    "/columns",
    response_model=list[ColumnInfo],
    summary="Доступные колонки отчёта",
)
async def list_columns(_: CurrentUserDep) -> list[ColumnInfo]:
    return [
        ColumnInfo(key=column, title=title, default=column in DEFAULT_COLUMNS)
        for column, title in COLUMN_TITLES.items()
    ]


@router.post(
    "/preview",
    response_model=ReportResponse,
    summary="Выборка отчёта с диаграммами",
    description=(
        "Строки и агрегаты для диаграмм считаются по одной выборке, "
        "поэтому таблица и диаграммы на экране всегда согласованы."
    ),
)
async def preview(
    payload: ReportRequest,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
) -> ReportResponse:
    return await reports.build_report(session, payload, principal, user)


@router.post(
    "/export",
    summary="Выгрузить отчёт файлом",
    description=(
        "Форматы: xlsx, xls, pdf, json. Формат xls отдаётся содержимым xlsx - "
        "Excel открывает его без вопросов, а двоичный формат Excel 97 давно "
        "не используется."
    ),
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def export(
    payload: ReportRequest,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
    export_format: ExportFormat = Query(default=ExportFormat.XLSX, alias="format"),
) -> Response:
    report = await reports.build_report(session, payload, principal, user)
    media_type, extension = CONTENT_TYPES[export_format]

    try:
        if export_format is ExportFormat.PDF:
            content = pdf_export.build(report)
        elif export_format is ExportFormat.JSON:
            content = report.model_dump_json(indent=2).encode("utf-8")
        else:
            content = xlsx_export.build(report)
    except Exception as exc:  # noqa: BLE001 - наружу уходит понятный код ошибки
        raise AppError(
            f"Не удалось сформировать отчёт: {exc}", code=ErrorCode.REPORT_FAILED
        ) from exc

    stamp = report.generated_at.strftime("%Y%m%d-%H%M")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="report-{stamp}.{extension}"'
        },
    )


@router.post(
    "/chart",
    summary="Диаграмма по выборке отдельным файлом",
    description="Форматы изображения: png и pdf (функциональное требование 1 ТЗ).",
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "application/pdf": {}}}},
)
async def chart(
    payload: ReportRequest,
    session: SessionDep,
    user: CurrentUserDep,
    principal: PrincipalDep,
    key: ChartKey = Query(default=ChartKey.BY_STATUS, description="Какая диаграмма"),
    image_format: ImageFormat = Query(default=ImageFormat.PNG, alias="format"),
) -> Response:
    report = await reports.build_report(session, payload, principal, user)
    data = next((item for item in report.charts if item.key is key), None)
    if data is None:
        raise AppError("Такой диаграммы нет", code=ErrorCode.REPORT_FAILED)

    try:
        if image_format is ImageFormat.PNG:
            content, media_type = chart_export.to_png(data), "image/png"
        else:
            content, media_type = chart_export.to_pdf(data), "application/pdf"
    except Exception as exc:  # noqa: BLE001 - наружу уходит понятный код ошибки
        raise AppError(
            f"Не удалось построить диаграмму: {exc}", code=ErrorCode.REPORT_FAILED
        ) from exc

    stamp = report.generated_at.strftime("%Y%m%d-%H%M")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="chart-{key.value}-{stamp}.{image_format.value}"'
            )
        },
    )
