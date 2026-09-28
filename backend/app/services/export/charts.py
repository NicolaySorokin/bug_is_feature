"""Диаграммы отчёта в PNG и PDF.

Горизонтальные столбики по убыванию, один цвет, значения подписаны у концов.
Рисует Pillow, в PDF вставляется та же картинка: векторный вывод reportlab
потребовал бы собирать pycairo в образе.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas

from app.schemas.report import ChartData
from app.services.export.fonts import font_files

# Палитра: один цвет для данных, остальные для оформления.
SERIES = (42, 120, 214)
SURFACE = (252, 252, 251)
INK_PRIMARY = (11, 11, 11)
INK_SECONDARY = (82, 81, 78)
INK_MUTED = (137, 135, 129)
GRID = (225, 224, 217)
BASELINE = (195, 194, 183)

# Размеры в точках, при отрисовке умножаются на SCALE: картинка получается
# 144 dpi и не мылится в презентации.
SCALE = 2
PADDING = 10
TITLE_SIZE = 12
SMALL_SIZE = 8
BAR_HEIGHT = 16
ROW_GAP = 10
LABEL_MAX = 190
LABEL_MIN = 90
VALUE_GAP = 6
TITLE_BLOCK = 34
AXIS_BLOCK = 16
BAR_RADIUS = 4


@dataclass(frozen=True, slots=True)
class _Fonts:
    regular: ImageFont.FreeTypeFont
    bold: ImageFont.FreeTypeFont
    small: ImageFont.FreeTypeFont


def _load_fonts() -> _Fonts:
    files = font_files()
    if files is None:  # без шрифта с кириллицей подписи будут квадратами
        default = ImageFont.load_default()
        return _Fonts(regular=default, bold=default, small=default)
    regular, bold = files
    return _Fonts(
        regular=ImageFont.truetype(str(regular), TITLE_SIZE * SCALE - 2),
        bold=ImageFont.truetype(str(bold), TITLE_SIZE * SCALE),
        small=ImageFont.truetype(str(regular), SMALL_SIZE * SCALE),
    )


def chart_size(chart: ChartData, width: int = 520) -> tuple[int, int]:
    """Размер диаграммы в точках: высота зависит от числа строк."""
    rows = max(len(chart.items), 1)
    height = TITLE_BLOCK + rows * (BAR_HEIGHT + ROW_GAP) + AXIS_BLOCK + PADDING
    return width, height


def _fit(text: str, font: ImageFont.FreeTypeFont, limit: int, draw: ImageDraw.Draw) -> str:
    """Обрезает подпись по ширине колонки, а не по числу символов."""
    if draw.textlength(text, font=font) <= limit:
        return text
    ellipsis = "…"
    shortened = text
    while shortened and draw.textlength(shortened + ellipsis, font=font) > limit:
        shortened = shortened[:-1]
    return shortened + ellipsis


def _ticks(maximum: int) -> list[int]:
    """Четыре-пять круглых отметок на шкале значений."""
    if maximum <= 5:
        return list(range(maximum + 1))
    step = max(1, round(maximum / 4))
    # Округляем шаг до «красивого» числа, чтобы подписи читались.
    for nice in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if nice >= step:
            step = nice
            break
    return list(range(0, maximum + step, step))


def render(chart: ChartData, width: int = 520) -> Image.Image:
    """Рисует диаграмму. Возвращает картинку в масштабе SCALE."""
    fonts = _load_fonts()
    width_pt, height_pt = chart_size(chart, width)
    image = Image.new("RGB", (width_pt * SCALE, height_pt * SCALE), SURFACE)
    draw = ImageDraw.Draw(image)

    pad = PADDING * SCALE
    draw.text((pad, pad), chart.title, font=fonts.bold, fill=INK_PRIMARY)
    draw.text(
        (pad, pad + (TITLE_SIZE + 5) * SCALE),
        f"Единица измерения: {chart.measure}",
        font=fonts.small,
        fill=INK_SECONDARY,
    )

    if not chart.items:
        draw.text(
            (pad, (TITLE_BLOCK + 10) * SCALE),
            "Нет данных за выбранный период",
            font=fonts.small,
            fill=INK_MUTED,
        )
        return image

    label_width = min(LABEL_MAX, max(LABEL_MIN, int(width * 0.34))) * SCALE
    left = pad + label_width
    value_space = int(draw.textlength("00000", font=fonts.small)) + VALUE_GAP * SCALE
    right = image.width - pad - value_space
    plot_width = max(right - left, 40 * SCALE)

    maximum = max(item.value for item in chart.items)
    ticks = _ticks(maximum)
    scale_max = max(ticks[-1], 1)
    top = TITLE_BLOCK * SCALE
    row_height = (BAR_HEIGHT + ROW_GAP) * SCALE
    bottom = top + row_height * len(chart.items)

    # Сетка рисуется первой: она должна остаться под столбиками.
    for tick in ticks:
        x = left + plot_width * tick / scale_max
        draw.line([(x, top), (x, bottom)], fill=GRID, width=1)
        text = str(tick)
        draw.text(
            (x - draw.textlength(text, font=fonts.small) / 2, bottom + 4 * SCALE),
            text,
            font=fonts.small,
            fill=INK_MUTED,
        )
    draw.line([(left, top), (left, bottom)], fill=BASELINE, width=SCALE)

    for index, item in enumerate(chart.items):
        y = top + index * row_height + (ROW_GAP // 2) * SCALE
        bar_height = BAR_HEIGHT * SCALE
        length = int(plot_width * item.value / scale_max)

        label = _fit(item.label, fonts.small, label_width - VALUE_GAP * SCALE, draw)
        label_width_px = draw.textlength(label, font=fonts.small)
        draw.text(
            (left - VALUE_GAP * SCALE - label_width_px, y + bar_height / 4),
            label,
            font=fonts.small,
            fill=INK_SECONDARY,
        )

        if length > 0:
            draw.rounded_rectangle(
                [(left, y), (left + max(length, BAR_RADIUS * SCALE), y + bar_height)],
                radius=BAR_RADIUS * SCALE,
                fill=SERIES,
                corners=(False, True, True, False),
            )
        draw.text(
            (left + length + VALUE_GAP * SCALE, y + bar_height / 4),
            str(item.value),
            font=fonts.small,
            fill=INK_PRIMARY,
        )

    return image


def to_png(chart: ChartData, width: int = 520) -> bytes:
    buffer = BytesIO()
    render(chart, width).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def to_image_reader(chart: ChartData, width: int = 520) -> ImageReader:
    """Диаграмма в виде, который понимает reportlab."""
    return ImageReader(BytesIO(to_png(chart, width)))


def to_pdf(chart: ChartData, width: int = 520) -> bytes:
    """Отдельный файл PDF с одной диаграммой."""
    width_pt, height_pt = chart_size(chart, width)
    page_width, _ = A4
    margin = 40
    buffer = BytesIO()
    canvas = pdf_canvas.Canvas(buffer, pagesize=(page_width, height_pt + 2 * margin))
    canvas.setTitle(chart.title)
    canvas.drawImage(
        to_image_reader(chart, width),
        margin,
        margin,
        width=min(width_pt, page_width - 2 * margin),
        height=height_pt,
    )
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()
