"""Проверка живости сервиса и доступности базы."""

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import SessionDep
from app.core.config import settings

router = APIRouter(tags=["service"])


@router.get("/health", summary="Состояние сервиса")
async def health(session: SessionDep) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "environment": settings.environment,
        "auth_backend": settings.auth_backend,
    }
