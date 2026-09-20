"""Выгрузка отчёта в PDF.

Лист альбомный: у отчёта до тринадцати колонок, в книжной ориентации они
нечитаемы. Сначала идёт табличная часть, затем диаграммы по той же выборке.
Длинные отчёты в PDF обрезаются - см. ``MAX_ROWS``: документ на тысячи строк
никто не читает, для такого объёма есть выгрузка в XLSX.
"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

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

    table = Table(
        [header, *body],
        colWidths=[width / len(report.columns)] * len(report.columns),
        repeatRows=1,
    )
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


def _chart_image(chart: ChartData, width: int) -> Image:
    """Диаграмма как изображение: рисует её тот же код, что и для PNG."""
    chart_width, chart_height = chart_export.chart_size(chart, width)
    return Image(
        BytesIO(chart_export.to_png(chart, width)),
        width=chart_width,
        height=chart_height,
    )


def _footer(canvas, document) -> None:  # noqa: ANN001 - подпись задана reportlab
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


def build(report: ReportResponse) -> bytes:
    styles = _styles()
    buffer = BytesIO()
    pagesize = landscape(A4)
    document = BaseDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=16 * mm,
        title=report.title,
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

    story: list = [
        Paragraph(report.title, styles["title"]),
        Spacer(1, 4),
        Paragraph(
            f"Период: {format_period(report.filters)} · "
            f"построен {report.generated_at.strftime('%d.%m.%Y %H:%M')}",
            styles["meta"],
        ),
        Paragraph(
            f"Договоров: {report.totals.contracts} · вузов: {report.totals.universities} · "
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

    if report.charts:
        story.append(PageBreak())
        story.append(Paragraph("Диаграммы", styles["title"]))
        story.append(
            Paragraph(
                "Диаграммы построены по той же выборке, что и таблица.", styles["meta"]
            )
        )
        story.append(Spacer(1, 8))
        for chart in report.charts:
            story.append(_chart_image(chart, int(document.width)))
            story.append(Spacer(1, 14))

    document.build(story)
    return buffer.getvalue()
