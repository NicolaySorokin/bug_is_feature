"""Проверка живости сервиса и служебные словари для клиента."""

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.errors import ErrorCode
from app.services.labels import ENUM_LABELS
from app.services.storage import ALLOWED_TYPES

router = APIRouter(tags=["service"])


@router.get("/health", summary="Состояние сервиса")
async def health(session: SessionDep) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "environment": settings.environment,
        "auth_backend": settings.auth_backend,
    }


@router.get(
    "/meta/enums",
    summary="Словари значений и ограничения",
    description=(
        "Подписи статусов, коды ошибок и ограничения на файлы одним ответом: "
        "клиенту не нужно держать эти списки у себя."
    ),
)
async def meta_enums() -> dict[str, object]:
    return {
        "labels": ENUM_LABELS,
        "error_codes": [code.value for code in ErrorCode],
        "uploads": {
            "allowed_extensions": sorted(ALLOWED_TYPES),
            "max_size_mb": settings.max_upload_mb,
        },
        "alerts": {
            "default_sla_days": settings.alert_default_sla_days,
            "expiring_days": settings.alert_expiring_days,
        },
    }
