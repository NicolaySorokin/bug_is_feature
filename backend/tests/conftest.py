"""Общая обвязка тестов.

Тесты API работают с настоящей PostgreSQL: часть запросов опирается
на возможности именно этой СУБД (JSONB, ON CONFLICT, приведение типов),
и проверять их на другой базе смысла нет. Используется отдельная база
``<основная>_test``, которая пересоздаётся перед каждым тестом - так
тесты не зависят друг от друга и от демоданных.

Если PostgreSQL недоступен, тесты API пропускаются: правила процесса
и разбор файлов проверяются без базы и продолжают работать.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import DevAuthBackend
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models import User  # noqa: F401 - импорт наполняет метадату

TEST_DB = f"{settings.postgres_db}_test"

MANAGER = {"X-Dev-User": "petrov", "X-Dev-Roles": "manager"}
OTHER_MANAGER = {"X-Dev-User": "ivanova", "X-Dev-Roles": "manager"}
HEAD = {"X-Dev-User": "orlova", "X-Dev-Roles": "manager,head"}
ADMIN = {"X-Dev-User": "root", "X-Dev-Roles": "manager,head,admin"}


def _url(database: str) -> str:
    return (
        f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{database}"
    )


async def _create_database() -> None:
    """Создаёт тестовую базу, если её ещё нет."""
    admin_engine = create_async_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as connection:
            # ProgrammingError означает, что база уже создана прошлым прогоном.
            with contextlib.suppress(ProgrammingError):
                await connection.exec_driver_sql(f'CREATE DATABASE "{TEST_DB}"')
    except SQLAlchemyError as exc:  # pragma: no cover - зависит от окружения
        pytest.skip(f"PostgreSQL недоступен: {exc}")
    finally:
        await admin_engine.dispose()


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    await _create_database()
    test_engine = create_async_engine(_url(TEST_DB))
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def client(engine: AsyncEngine, tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Клиент API поверх приложения, подключённого к тестовой базе."""
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def override_session() -> AsyncIterator:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_session
    # ASGITransport не запускает события старта приложения, поэтому схему
    # аутентификации выставляем сами.
    app.state.auth_backend = DevAuthBackend(settings)

    previous_storage = settings.storage_dir
    settings.storage_dir = tmp_path / "storage"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as instance:
        yield instance

    app.dependency_overrides.clear()
    settings.storage_dir = previous_storage


@pytest.fixture
async def university(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/universities",
        json={"name": f"Тестовый университет {uuid.uuid4().hex[:6]}", "city": "Москва"},
        headers=ADMIN,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def workflow_version(client: AsyncClient) -> dict:
    """Опубликованный шаблон процесса: контакт -> встреча -> подписание."""
    response = await client.post(
        "/api/v1/workflow/templates",
        json={
            "name": "Тестовый процесс",
            "graph": {
                "stages": [
                    {"code": "contact", "name": "Контакт", "sla_days": 7},
                    {"code": "meeting", "name": "Встреча", "is_optional": True},
                    {"code": "signing", "name": "Подписание", "is_final": True},
                ],
                "transitions": [
                    {"from_code": "contact", "to_code": "meeting"},
                    {"from_code": "meeting", "to_code": "signing"},
                    {
                        "from_code": "meeting",
                        "to_code": "contact",
                        "is_backward": True,
                        "requires_comment": True,
                    },
                ],
            },
        },
        headers=ADMIN,
    )
    assert response.status_code == 201, response.text
    version = response.json()

    published = await client.post(
        f"/api/v1/workflow/versions/{version['id']}/publish", headers=ADMIN
    )
    assert published.status_code == 200, published.text
    return version


async def make_contract(
    client: AsyncClient, university_id: str, headers: dict, **extra
) -> dict:
    payload = {
        "university_id": university_id,
        "number": f"ДГ-{uuid.uuid4().hex[:8]}",
        "status": "active",
        **extra,
    }
    response = await client.post("/api/v1/contracts", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()
