"""Правила хранения файлов, без базы данных.

Формат вложения ограничен списком из ТЗ, а путём из базы нельзя выйти
за пределы хранилища.
"""

from pathlib import Path

import pytest

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.services import storage


@pytest.fixture(autouse=True)
def storage_dir(tmp_path: Path):
    previous = settings.storage_dir
    settings.storage_dir = tmp_path / "storage"
    yield settings.storage_dir
    settings.storage_dir = previous


def test_allowed_formats_match_the_specification() -> None:
    assert set(storage.ALLOWED_TYPES) == {
        "png",
        "jpg",
        "jpeg",
        "pdf",
        "zip",
        "gz",
        "gzip",
        "rar",
        "doc",
        "docx",
        "xls",
        "xlsx",
    }


def test_extension_is_checked_regardless_of_case() -> None:
    assert storage.check_extension("Договор.PDF") == "pdf"
    assert storage.check_extension("каталог.XLSX", storage.SPREADSHEET_TYPES) == "xlsx"


def test_foreign_format_is_refused() -> None:
    with pytest.raises(AppError) as info:
        storage.check_extension("скрипт.exe")
    assert info.value.code == ErrorCode.FILE_TYPE_NOT_ALLOWED
    assert info.value.status_code == 415


def test_file_without_extension_is_refused() -> None:
    with pytest.raises(AppError, match="без расширения"):
        storage.check_extension("документ")


def test_import_accepts_only_spreadsheets() -> None:
    with pytest.raises(AppError) as info:
        storage.check_extension("скан.png", storage.SPREADSHEET_TYPES)
    assert info.value.details == {"allowed": ["xls", "xlsx"]}


def test_path_cannot_leave_storage_directory() -> None:
    inside = storage.absolute_path("contracts/файл.pdf")
    assert inside.is_relative_to(storage.storage_root().resolve())

    with pytest.raises(AppError, match="Некорректный путь"):
        storage.absolute_path("../../etc/passwd")
