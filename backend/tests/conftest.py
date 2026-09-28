"""Общая обвязка тестов.

Тесты API работают с настоящей PostgreSQL в отдельной базе <основная>_test,
которая пересоздаётся перед каждым тестом. Без PostgreSQL тесты API
пропускаются, остальные работают.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import DevAuthBackend
from app.db.base import Base
from app.db.session import commit, get_session
from app.main import app
from app.models import User  # noqa: F401 (импорт наполняет метадату)
from app.services import cache

TEST_DB = f"{settings.postgres_db}_test"

# Роли не наследуются. Орлова руководит и сама ведёт вузы, администратор
# бизнес-данных не видит.
MANAGER = {"X-Dev-User": "petrov", "X-Dev-Roles": "manager"}
OTHER_MANAGER = {"X-Dev-User": "ivanova", "X-Dev-Roles": "manager"}
HEAD = {"X-Dev-User": "orlova", "X-Dev-Roles": "manager,head"}
PURE_HEAD = {"X-Dev-User": "fedorov", "X-Dev-Roles": "head"}
ADMIN = {"X-Dev-User": "root", "X-Dev-Roles": "admin"}

TEST_GRAPH = {
    "stages": [
        {"code": "contact", "name": "Контакт", "sla_days": 7, "is_initial": True},
        {"code": "meeting", "name": "Встреча", "is_optional": True},
        {"code": "signing", "name": "Подписание", "is_final": True, "outcome": "successful"},
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
}


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
    except SQLAlchemyError as exc:  # pragma: no cover (зависит от окружения)
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
                await commit(session)
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_session
    # ASGITransport не запускает события старта, поэтому схему входа выставляем сами.
    app.state.auth_backend = DevAuthBackend(settings)

    previous_storage = settings.storage_dir
    settings.storage_dir = tmp_path / "storage"
    # Кэш выборок выключен: часть тестов правит базу напрямую, мимо счётчика
    # изменений. Сам кэш проверяет test_system.py.
    previous_ttl = settings.cache_ttl_seconds
    settings.cache_ttl_seconds = 0
    cache.clear()

    # Непредвиденная ошибка должна дойти до клиента ответом 500, как в работе.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as instance:
        yield instance

    app.dependency_overrides.clear()
    settings.storage_dir = previous_storage
    settings.cache_ttl_seconds = previous_ttl
    cache.clear()


@pytest.fixture
async def university(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/universities",
        json={"name": f"Тестовый университет {uuid.uuid4().hex[:6]}", "city": "Москва"},
        headers=ADMIN,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_template(
    client: AsyncClient, name: str = "Тестовый процесс", graph: dict | None = None
) -> dict:
    """Шаблон с действующей версией: контакт, встреча, подписание."""
    response = await client.post(
        "/api/v1/workflow/templates",
        json={"name": name, "graph": graph or TEST_GRAPH},
        headers=ADMIN,
    )
    assert response.status_code == 201, response.text
    version = response.json()

    published = await client.post(
        f"/api/v1/workflow/versions/{version['id']}/publish", headers=ADMIN
    )
    assert published.status_code == 200, published.text
    return version


@pytest.fixture
async def workflow_version(client: AsyncClient) -> dict:
    return await create_template(client)


async def me(client: AsyncClient, headers: dict) -> dict:
    response = await client.get("/api/v1/me", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def join_team(client: AsyncClient, member: dict, head: dict = HEAD) -> None:
    """Менеджер входит в команду руководителя: тот видит и назначает его."""
    member_id = (await me(client, member))["id"]
    head_id = (await me(client, head))["id"]
    response = await client.patch(
        f"/api/v1/users/{member_id}", json={"head_id": head_id}, headers=ADMIN
    )
    assert response.status_code == 200, response.text


async def ensure_template(client: AsyncClient) -> None:
    templates = (await client.get("/api/v1/workflow/templates", headers=HEAD)).json()
    if not templates:
        await create_template(client)


async def make_interaction(
    client: AsyncClient,
    university_id: str,
    headers: dict,
    *,
    start: bool = True,
    **extra,
) -> dict:
    """Взаимодействие, которое ведёт владелец headers.

    Менеджеру его заводит руководитель, потому что вуз из теста за менеджером
    не закреплён.
    """
    await ensure_template(client)
    author = headers
    roles = headers["X-Dev-Roles"].split(",")
    if "head" not in roles:
        await join_team(client, headers)
        author = HEAD
    if "manager" in roles:
        extra.setdefault("manager_id", (await me(client, headers))["id"])
    response = await client.post(
        "/api/v1/interactions",
        json={"university_id": university_id, "start": start, **extra},
        headers=author,
    )
    assert response.status_code == 201, response.text
    return response.json()


def contract_payload(**extra) -> dict:
    today = date.today()
    return {
        "number": f"ДГ-{uuid.uuid4().hex[:8]}",
        "status": "active",
        "signed_at": today.isoformat(),
        "valid_from": today.isoformat(),
        "valid_to": (today + timedelta(days=365)).isoformat(),
        **extra,
    }


async def make_contract(
    client: AsyncClient, university_id: str, headers: dict, **extra
) -> tuple[dict, dict]:
    """Взаимодействие с договором: (взаимодействие, договор)."""
    interaction = await make_interaction(client, university_id, headers)
    response = await client.put(
        f"/api/v1/interactions/{interaction['id']}/contract",
        json=contract_payload(**extra),
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return interaction, response.json()
