"""Точка входа FastAPI-приложения."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.security import build_auth_backend
from app.db.session import engine

DESCRIPTION = """
API системы контроля взаимодействия ИТ Школы Ростелекома с вузами.

В dev-режиме авторизация заменена заглушкой: пользователя можно задать
заголовками `X-Dev-User` и `X-Dev-Roles` (роли через запятую:
`manager`, `head`, `admin`).
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Схема аутентификации выбирается один раз на старте и лежит в state,
    # чтобы её можно было подменить в тестах.
    app.state.auth_backend = build_auth_backend(settings)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version="0.1.0",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs"}
