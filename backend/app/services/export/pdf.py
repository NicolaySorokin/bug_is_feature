"""Выгрузка отчёта в PDF.

Лист альбомный, сначала таблица, затем диаграммы. Строк не больше MAX_ROWS,
для большого объёма есть XLSX.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from io import BytesIO
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.report import COLUMN_TITLES, ChartData, ReportResponse
from app.services.export import charts as chart_export
from app.services.export.fonts import ensure_fonts
from app.services.reports import format_period, row_value

if TYPE_CHECKING:  # pragma: no cover (только для подсказок типов)
    from app.services.export.table import Table as ExportTable

MAX_ROWS = 1000
HEADER_FILL = colors.HexColor("#f0efec")
GRID = colors.HexColor("#e1e0d9")
BASELINE = colors.HexColor("#c3c2b7")
INK_PRIMARY = colors.HexColor("#0b0b0b")
INK_SECONDARY = colors.HexColor("#52514e")
INK_MUTED = colors.HexColor("#898781")
MARGIN = 14 * mm


def _styles() -> dict[str, ParagraphStyle]:
    regular, bold = ensure_fonts()
    return {
        "title": ParagraphStyle(
            "title", fontName=bold, fontSize=16, leading=20, textColor=INK_PRIMARY
        ),
        "meta": ParagraphStyle(
            "meta", fontName=regular, fontSize=9, leading=12, textColor=INK_SECONDARY
        ),
        "header": ParagraphStyle(
            "header", fontName=bold, fontSize=8, leading=10, textColor=INK_PRIMARY
        ),
        "cell": ParagraphStyle(
            "cell",
            fontName=regular,
            fontSize=8,
            leading=10,
            textColor=INK_PRIMARY,
            alignment=TA_LEFT,
        ),
        "note": ParagraphStyle(
            "note", fontName=regular, fontSize=8, leading=10, textColor=INK_MUTED
        ),
    }


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value)


def _table(report: ReportResponse, styles: dict[str, ParagraphStyle], width: float) -> Table:
    header = [Paragraph(COLUMN_TITLES[column], styles["header"]) for column in report.columns]
    body = [
        [
            Paragraph(_text(row_value(row, column.value)), styles["cell"])
            for column in report.columns
        ]
        for row in report.rows[:MAX_ROWS]
    ]

    return _grid([header, *body], [width / len(report.columns)] * len(report.columns))


def _chart_image(chart: ChartData, width: int) -> Image:
    """Диаграмма как изображение: рисует её тот же код, что и для PNG."""
    chart_width, chart_height = chart_export.chart_size(chart, width)
    return Image(
        BytesIO(chart_export.to_png(chart, width)),
        width=chart_width,
        height=chart_height,
    )


def _footer(canvas, document) -> None:  # noqa: ANN001 (подпись задана reportlab)
    regular, _ = ensure_fonts()
    canvas.saveState()
    canvas.setFont(regular, 7)
    canvas.setFillColor(INK_MUTED)
    canvas.drawString(
        MARGIN, 8 * mm, "ИТ Школа Ростелекома · система контроля работы с вузами"
    )
    canvas.drawRightString(
        document.pagesize[0] - MARGIN, 8 * mm, f"Страница {canvas.getPageNumber()}"
    )
    canvas.restoreState()


def _document(buffer: BytesIO, title: str) -> BaseDocTemplate:
    """Альбомный лист A4 с колонтитулом, общий для всех PDF."""
    document = BaseDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=16 * mm,
        title=title,
        author="ИТ Школа Ростелекома",
    )
    frame = Frame(
        document.leftMargin,
        document.bottomMargin,
        document.width,
        document.height,
        id="main",
    )
    document.addPageTemplates([PageTemplate(id="report", frames=[frame], onPage=_footer)])
    return document


def _grid(data: list[list], widths: list[float]) -> Table:
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, BASELINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _charts_story(
    charts: list[ChartData], styles: dict[str, ParagraphStyle], width: int
) -> list:
    if not charts:
        return []
    story: list = [
        PageBreak(),
        Paragraph("Диаграммы", styles["title"]),
        Paragraph("Диаграммы построены по той же выборке, что и таблица.", styles["meta"]),
        Spacer(1, 8),
    ]
    for chart in charts:
        story.append(_chart_image(chart, width))
        story.append(Spacer(1, 14))
    return story


def build_table(
    table_data: ExportTable, column_widths: Sequence[float] | None = None
) -> bytes:
    """Произвольная таблица с шапкой и диаграммами, например статистика обучения."""
    styles = _styles()
    buffer = BytesIO()
    document = _document(buffer, table_data.title)
    story: list = [Paragraph(table_data.title, styles["title"]), Spacer(1, 4)]
    story += [Paragraph(line, styles["meta"]) for line in table_data.meta]
    story.append(Spacer(1, 10))

    if table_data.rows:
        count = len(table_data.headers)
        if column_widths:
            total = sum(column_widths)
            widths = [document.width * part / total for part in column_widths]
        else:
            widths = [document.width / count] * count
        header = [Paragraph(title, styles["header"]) for title in table_data.headers]
        body = [
            [Paragraph(_text(value), styles["cell"]) for value in row]
            for row in table_data.rows[:MAX_ROWS]
        ]
        story.append(_grid([header, *body], widths))
        if len(table_data.rows) > MAX_ROWS:
            story.append(Spacer(1, 6))
            story.append(
                Paragraph(
                    f"Показаны первые {MAX_ROWS} строк из {len(table_data.rows)}. "
                    "Полный набор данных есть в выгрузке XLSX.",
                    styles["note"],
                )
            )
    else:
        story.append(Paragraph("За выбранный период данных нет.", styles["note"]))

    story += _charts_story(table_data.charts, styles, int(document.width))
    document.build(story)
    return buffer.getvalue()


def build(report: ReportResponse) -> bytes:
    styles = _styles()
    buffer = BytesIO()
    document = _document(buffer, report.title)

    story: list = [
        Paragraph(report.title, styles["title"]),
        Spacer(1, 4),
        Paragraph(
            f"Период: {format_period(report.filters)} · "
            f"построен {report.generated_at.strftime('%d.%m.%Y %H:%M')}",
            styles["meta"],
        ),
        Paragraph(
            f"Взаимодействий: {report.totals.interactions} · "
            f"вузов: {report.totals.universities} · "
            f"программ: {report.totals.programs} · продуктов: {report.totals.products} · "
            f"строк: {report.totals.rows}",
            styles["meta"],
        ),
        Spacer(1, 10),
    ]

    if report.rows:
        story.append(_table(report, styles, document.width))
        if len(report.rows) > MAX_ROWS:
            story.append(Spacer(1, 6))
            story.append(
                Paragraph(
                    f"Показаны первые {MAX_ROWS} строк из {len(report.rows)}. "
                    "Полный набор данных есть в выгрузке XLSX.",
                    styles["note"],
                )
            )
    else:
        story.append(Paragraph("За выбранный период данных нет.", styles["note"]))

    story += _charts_story(report.charts, styles, int(document.width))
    document.build(story)
    return buffer.getvalue()
