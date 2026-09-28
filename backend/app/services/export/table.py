"""Выгрузка произвольной таблицы: XLS, XLSX и PDF.

XLS это настоящий Excel 97 (xlwt), ТЗ называет формат отдельно. В нём
не больше 65 535 строк, для большего объёма есть XLSX.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.core.errors import AppError, ErrorCode
from app.schemas.report import ChartData
from app.services.export import xlsx as report_xlsx

XLS_MAX_ROWS = 65_000
MAX_WIDTH = 55


@dataclass(slots=True)
class Table:
    title: str
    meta: list[str]
    headers: list[str]
    rows: list[list[object]]
    charts: list[ChartData] = field(default_factory=list)


def _width(value: object) -> int:
    if isinstance(value, date | datetime):
        return 12
    return len(str(value)) if value is not None else 0


def to_xlsx(table: Table) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Данные"
    sheet["A1"] = table.title
    sheet["A1"].font = report_xlsx.TITLE_FONT
    for offset, line in enumerate(table.meta, start=2):
        sheet.cell(row=offset, column=1, value=line).font = report_xlsx.MUTED_FONT

    header_row = len(table.meta) + 3
    widths: dict[int, int] = {}
    for index, title in enumerate(table.headers, start=1):
        cell = sheet.cell(row=header_row, column=index, value=title)
        cell.font = Font(bold=True, color="0B0B0B")
        cell.fill = PatternFill("solid", fgColor="F0EFEC")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        widths[index] = len(title)

    for offset, row in enumerate(table.rows, start=header_row + 1):
        for index, value in enumerate(row, start=1):
            if isinstance(value, datetime):
                value = value.replace(tzinfo=None)
            cell = sheet.cell(row=offset, column=index, value=value)
            if isinstance(value, date | datetime):
                cell.number_format = report_xlsx.DATE_FORMAT
            widths[index] = max(widths[index], _width(value))

    last_column = get_column_letter(max(len(table.headers), 1))
    last_row = header_row + len(table.rows)
    sheet.auto_filter.ref = f"A{header_row}:{last_column}{last_row}"
    sheet.freeze_panes = f"A{header_row + 1}"
    for index, width in widths.items():
        sheet.column_dimensions[get_column_letter(index)].width = min(width + 2, MAX_WIDTH)

    if table.charts:
        charts_sheet = workbook.create_sheet("Диаграммы")
        charts_sheet.column_dimensions["A"].width = 40
        charts_sheet.column_dimensions["B"].width = 14
        row = 1
        for chart in table.charts:
            row = report_xlsx._write_chart(charts_sheet, chart, row)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def to_xls(table: Table) -> bytes:
    """Excel 97 (BIFF8). Диаграммы формат не хранит, поэтому пишем сводки."""
    import xlwt

    if len(table.rows) > XLS_MAX_ROWS:
        raise AppError(
            f"В выгрузке {len(table.rows)} строк - это больше предела формата XLS. "
            "Выберите XLSX или сузьте фильтры",
            code=ErrorCode.REPORT_FAILED,
        )

    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("Данные")
    title_style = xlwt.easyxf("font: bold on, height 280")
    muted_style = xlwt.easyxf("font: colour grey50")
    header_style = xlwt.easyxf(
        "font: bold on; pattern: pattern solid, fore_colour ivory; "
        "borders: bottom thin; align: wrap on, vert centre"
    )
    date_style = xlwt.easyxf(num_format_str="DD.MM.YYYY")

    sheet.write(0, 0, table.title, title_style)
    for offset, line in enumerate(table.meta, start=1):
        sheet.write(offset, 0, line, muted_style)

    header_row = len(table.meta) + 2
    widths = [len(title) for title in table.headers]
    for index, title in enumerate(table.headers):
        sheet.write(header_row, index, title, header_style)

    for offset, row in enumerate(table.rows, start=header_row + 1):
        for index, value in enumerate(row):
            if isinstance(value, datetime):
                sheet.write(offset, index, value.replace(tzinfo=None), date_style)
            elif isinstance(value, date):
                sheet.write(offset, index, value, date_style)
            elif value is None:
                sheet.write(offset, index, "")
            else:
                sheet.write(offset, index, value)
            widths[index] = max(widths[index], _width(value))

    for index, width in enumerate(widths):
        sheet.col(index).width = 256 * min(width + 2, MAX_WIDTH)
    sheet.set_panes_frozen(True)
    sheet.set_horz_split_pos(header_row + 1)

    # Сводки диаграмм отдельными листами.
    for chart in table.charts:
        chart_sheet = book.add_sheet(_sheet_name(chart.title))
        chart_sheet.write(0, 0, chart.title, title_style)
        chart_sheet.write(1, 0, "Значение", header_style)
        chart_sheet.write(1, 1, chart.measure.capitalize(), header_style)
        for offset, item in enumerate(chart.items, start=2):
            chart_sheet.write(offset, 0, item.label)
            chart_sheet.write(offset, 1, item.value)
        chart_sheet.col(0).width = 256 * 45
        chart_sheet.col(1).width = 256 * 14

    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _sheet_name(title: str) -> str:
    # Имя листа Excel: до 31 символа, без []:*?/\
    cleaned = "".join(char for char in title if char not in "[]:*?/\\")
    return cleaned[:31] or "Диаграмма"


def to_pdf(table: Table, column_widths: Sequence[float] | None = None) -> bytes:
    from app.services.export import pdf as report_pdf

    return report_pdf.build_table(table, column_widths)
