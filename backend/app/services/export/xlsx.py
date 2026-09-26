"""Выгрузка отчёта в XLSX.

Книга состоит из двух листов: «Отчёт» - табличная часть с выбранными
колонками, «Диаграммы» - те же данные в виде сводных табличек и диаграмм
Excel рядом с ними. Диаграмма строится из ячеек листа, поэтому получатель
видит, из каких именно чисел она собрана, и может пересчитать их сам.
"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.schemas.report import COLUMN_TITLES, ChartData, ReportResponse
from app.services.reports import format_period, row_value

HEADER_FILL = PatternFill("solid", fgColor="F0EFEC")
HEADER_FONT = Font(bold=True, color="0B0B0B")
TITLE_FONT = Font(bold=True, size=14, color="0B0B0B")
MUTED_FONT = Font(size=9, color="52514E")
SERIES_COLOR = "2A78D6"

MAX_WIDTH = 55
DATE_FORMAT = "DD.MM.YYYY"


def _write_meta(sheet: Worksheet, report: ReportResponse) -> int:
    """Шапка листа: что за отчёт, за какой период и когда построен."""
    sheet["A1"] = report.title
    sheet["A1"].font = TITLE_FONT
    sheet["A2"] = f"Период: {format_period(report.filters)}"
    sheet["A2"].font = MUTED_FONT
    sheet["A3"] = (
        f"Построен: {report.generated_at.strftime('%d.%m.%Y %H:%M')} · "
        f"взаимодействий: {report.totals.interactions} · строк: {report.totals.rows}"
    )
    sheet["A3"].font = MUTED_FONT
    return 5  # первая строка таблицы


def _autosize(sheet: Worksheet, widths: dict[int, int]) -> None:
    for index, width in widths.items():
        sheet.column_dimensions[get_column_letter(index)].width = min(width + 2, MAX_WIDTH)


def _write_table(sheet: Worksheet, report: ReportResponse) -> None:
    header_row = _write_meta(sheet, report)
    widths: dict[int, int] = {}

    for index, column in enumerate(report.columns, start=1):
        cell = sheet.cell(row=header_row, column=index, value=COLUMN_TITLES[column])
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        widths[index] = len(COLUMN_TITLES[column])

    for offset, row in enumerate(report.rows, start=header_row + 1):
        for index, column in enumerate(report.columns, start=1):
            value = row_value(row, column.value)
            cell = sheet.cell(row=offset, column=index, value=value)
            if isinstance(value, date | datetime):
                cell.number_format = DATE_FORMAT
                widths[index] = max(widths[index], 12)
            else:
                widths[index] = max(widths[index], len(str(value or "")))

    last_row = header_row + len(report.rows)
    last_column = get_column_letter(len(report.columns))
    sheet.auto_filter.ref = f"A{header_row}:{last_column}{max(last_row, header_row)}"
    sheet.freeze_panes = f"A{header_row + 1}"
    _autosize(sheet, widths)


def _write_chart(sheet: Worksheet, chart: ChartData, top_row: int) -> int:
    """Сводная табличка и диаграмма по ней. Возвращает строку для следующей."""
    sheet.cell(row=top_row, column=1, value=chart.title).font = HEADER_FONT
    sheet.cell(row=top_row + 1, column=1, value="Значение").font = MUTED_FONT
    sheet.cell(row=top_row + 1, column=2, value=chart.measure.capitalize()).font = MUTED_FONT

    for offset, item in enumerate(chart.items, start=top_row + 2):
        sheet.cell(row=offset, column=1, value=item.label)
        sheet.cell(row=offset, column=2, value=item.value)

    last_row = top_row + 1 + len(chart.items)
    if chart.items:
        excel_chart = BarChart()
        excel_chart.type = "bar"  # горизонтальные столбики
        excel_chart.title = chart.title
        excel_chart.legend = None  # один ряд - легенда не нужна
        excel_chart.height = max(5.0, 0.7 * len(chart.items) + 2)
        excel_chart.width = 16
        excel_chart.add_data(
            Reference(sheet, min_col=2, min_row=top_row + 1, max_row=last_row),
            titles_from_data=True,
        )
        excel_chart.set_categories(
            Reference(sheet, min_col=1, min_row=top_row + 2, max_row=last_row)
        )
        excel_chart.dataLabels = DataLabelList()
        excel_chart.dataLabels.showVal = True
        # Наибольшее значение - сверху: по умолчанию Excel ставит его вниз.
        excel_chart.y_axis.scaling.orientation = "maxMin"
        excel_chart.x_axis.majorGridlines = None
        series = excel_chart.series[0]
        series.graphicalProperties.solidFill = SERIES_COLOR
        series.graphicalProperties.line.noFill = True
        sheet.add_chart(excel_chart, f"D{top_row}")

    # Место под диаграмму: она выше таблички, если значений мало.
    return max(last_row, top_row + int(1.6 * len(chart.items)) + 6) + 3


def _write_charts(sheet: Worksheet, report: ReportResponse) -> None:
    sheet.column_dimensions["A"].width = 40
    sheet.column_dimensions["B"].width = 14
    row = 1
    for chart in report.charts:
        row = _write_chart(sheet, chart, row)


def build(report: ReportResponse) -> bytes:
    workbook = Workbook()
    table_sheet = workbook.active
    table_sheet.title = "Отчёт"
    _write_table(table_sheet, report)
    _write_charts(workbook.create_sheet("Диаграммы"), report)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
