"""Хранение загруженных файлов.

Раздел 9.2 концепции: содержимое файла лежит на диске сервера, в PostgreSQL -
только сведения о нём и путь. Путь хранится относительно каталога хранилища,
поэтому стенд можно перенести на другую машину, не трогая базу.

Список допустимых форматов взят из функционального требования 3 ТЗ.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import anyio
from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import AppError, ErrorCode

# Расширение -> тип содержимого. Ключ - то, что видим в имени файла.
ALLOWED_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "pdf": "application/pdf",
    "zip": "application/zip",
    "gz": "application/gzip",
    "gzip": "application/gzip",
    "rar": "application/vnd.rar",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

SPREADSHEET_TYPES = ("xls", "xlsx")

_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class StoredFile:
    """Результат сохранения: что записали и куда."""

    original_name: str
    storage_path: str
    mime_type: str
    size_bytes: int


def _extension(filename: str) -> str:
    return PurePosixPath(filename).suffix.lstrip(".").lower()


def check_extension(filename: str, allowed: tuple[str, ...] | None = None) -> str:
    """Проверяет расширение файла и возвращает его в нижнем регистре."""
    extension = _extension(filename)
    permitted = allowed or tuple(ALLOWED_TYPES)
    if extension not in permitted:
        raise AppError(
            f"Формат «{extension or 'без расширения'}» не поддерживается",
            code=ErrorCode.FILE_TYPE_NOT_ALLOWED,
            status_code=415,
            details={"allowed": list(permitted)},
        )
    return extension


def storage_root() -> Path:
    root = settings.storage_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def absolute_path(storage_path: str) -> Path:
    """Абсолютный путь к файлу с защитой от выхода за пределы хранилища."""
    root = storage_root().resolve()
    candidate = (root / storage_path).resolve()
    if not candidate.is_relative_to(root):
        raise AppError("Некорректный путь к файлу", code=ErrorCode.VALIDATION_ERROR)
    return candidate


async def save_upload(
    upload: UploadFile,
    subdir: str,
    *,
    allowed: tuple[str, ...] | None = None,
) -> StoredFile:
    """Сохраняет загруженный файл, соблюдая ограничение на размер."""
    original_name = upload.filename or "file"
    extension = check_extension(original_name, allowed)

    directory = storage_root() / subdir
    directory.mkdir(parents=True, exist_ok=True)
    relative = str(PurePosixPath(subdir) / f"{uuid.uuid4()}.{extension}")
    target = directory / f"{Path(relative).name}"

    size = 0
    limit = settings.max_upload_bytes
    try:
        with target.open("wb") as handle:
            while chunk := await upload.read(_CHUNK):
                size += len(chunk)
                if size > limit:
                    raise AppError(
                        f"Файл больше допустимых {settings.max_upload_mb} МБ",
                        code=ErrorCode.FILE_TOO_LARGE,
                        status_code=413,
                    )
                await anyio.to_thread.run_sync(handle.write, chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise

    return StoredFile(
        original_name=original_name,
        storage_path=relative,
        # Тип содержимого - по проверенному расширению, а не со слов браузера:
        # при скачивании файл отдаётся с ним, и подменить его («картинка»
        # с типом text/html) нельзя.
        mime_type=ALLOWED_TYPES.get(extension, "application/octet-stream"),
        size_bytes=size,
    )


def delete(storage_path: str) -> None:
    absolute_path(storage_path).unlink(missing_ok=True)
