"""Обмен с LMS и сайтом по расписанию."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.models.integration import IntegrationRun
from app.services.integrations import base, scheduler
from tests.conftest import ADMIN


@pytest.fixture(autouse=True)
def stable_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "FIXTURES", Path(__file__).parent / "fixtures" / "integrations")


async def _set_interval(client: AsyncClient, hours: int) -> None:
    response = await client.put(
        "/api/v1/settings",
        headers=ADMIN,
        json={"values": {"integration_sync_interval_hours": hours}},
    )
    assert response.status_code == 200, response.text


async def test_schedule_is_off_by_default(client: AsyncClient, engine: AsyncEngine) -> None:
    settings = (await client.get("/api/v1/settings", headers=ADMIN)).json()
    interval = next(
        item for item in settings if item["key"] == "integration_sync_interval_hours"
    )
    assert interval["value"] == 0

    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    assert await scheduler.tick(factory) == []


async def test_schedule_runs_due_sources_once(
    client: AsyncClient, engine: AsyncEngine, workflow_version: dict
) -> None:
    await _set_interval(client, 6)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    # Обменов ещё не было, срок подошёл у обоих источников, LMS первой.
    assert await scheduler.tick(factory) == ["lms", "site"]
    async with factory() as session:
        runs = (await session.execute(select(IntegrationRun))).scalars().all()
    assert {run.trigger for run in runs} == {"schedule"}
    assert all(run.triggered_by is None for run in runs)

    # Сразу после обмена повторять нечего, а через интервал снова пора.
    assert await scheduler.tick(factory) == []
    later = datetime.now(UTC) + timedelta(hours=7)
    assert await scheduler.tick(factory, now=later) == ["lms", "site"]


async def test_manual_run_postpones_schedule(
    client: AsyncClient, engine: AsyncEngine, workflow_version: dict
) -> None:
    await _set_interval(client, 6)
    response = await client.post("/api/v1/integrations/sources/lms/sync", headers=ADMIN)
    assert response.status_code == 200, response.text

    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    assert await scheduler.tick(factory) == ["site"]


async def test_disabled_source_is_skipped(client: AsyncClient, engine: AsyncEngine) -> None:
    await _set_interval(client, 1)
    response = await client.patch(
        "/api/v1/integrations/sources/site", headers=ADMIN, json={"is_enabled": False}
    )
    assert response.status_code == 200, response.text

    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    assert await scheduler.tick(factory) == ["lms"]
