"""Шрифты для PDF.

Встроенные шрифты reportlab кириллицу не содержат, поэтому подключаем
DejaVu: в образе он ставится пакетом fonts-dejavu-core, при локальном
запуске ищется среди системных. Если ничего не нашли, отчёт всё равно
формируется - но латиницей, и об этом пишем в лог один раз.
"""

from __future__ import annotations

import logging
from pathlib import Path

from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

REGULAR = "DejaVuSans"
BOLD = "DejaVuSans-Bold"

# Порядок важен: сначала Linux-образ, затем типичные локальные установки.
_CANDIDATES: list[tuple[str, str]] = [
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/DejaVuSans.ttf", "C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
]

_registered: tuple[str, str] | None = None


def font_files() -> tuple[Path, Path] | None:
    """Пути к файлам шрифта: нужны диаграммам, которые рисует Pillow."""
    for regular, bold in _CANDIDATES:
        regular_path, bold_path = Path(regular), Path(bold)
        if regular_path.is_file():
            return regular_path, bold_path if bold_path.is_file() else regular_path
    return None


def ensure_fonts() -> tuple[str, str]:
    """Возвращает имена обычного и жирного начертания для PDF."""
    global _registered
    if _registered is not None:
        return _registered

    found = font_files()
    if found is None:
        logger.warning(
            "Шрифт с кириллицей не найден, PDF будет собран стандартным Helvetica. "
            "Установите пакет fonts-dejavu-core."
        )
        _registered = ("Helvetica", "Helvetica-Bold")
        return _registered

    regular_path, bold_path = found
    pdfmetrics.registerFont(TTFont(REGULAR, str(regular_path)))
    pdfmetrics.registerFont(TTFont(BOLD, str(bold_path)))
    # Чтобы разметка вида <b>…</b> в Paragraph находила жирное начертание.
    addMapping(REGULAR, 0, 0, REGULAR)
    addMapping(REGULAR, 1, 0, BOLD)
    _registered = (REGULAR, BOLD)
    return _registered
