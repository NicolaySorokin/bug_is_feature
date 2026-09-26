"""Обмен с LMS и сайтом на тестовых ответах адаптеров."""

from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient

from app.core.errors import AppError, ErrorCode
from app.services.integrations import base
from tests.conftest import ADMIN, HEAD, MANAGER


@pytest.fixture(autouse=True)
def stable_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Свои ответы LMS и сайта: демонстрационные растут вместе с демоданными."""
    monkeypatch.setattr(base, "FIXTURES", Path(__file__).parent / "fixtures" / "integrations")


async def test_sources_are_registered_with_fixtures(client: AsyncClient) -> None:
    sources = (await client.get("/api/v1/integrations/sources", headers=MANAGER)).json()
    codes = {source["code"] for source in sources}
    assert codes == {"lms", "site"}
    # Адрес внешней системы не задан - работаем на тестовых данных.
    assert all(source["uses_fixture"] for source in sources)


async def test_sync_fills_catalogs_and_starts_workflow(
    client: AsyncClient, workflow_version: dict
) -> None:
    runs = (await client.post("/api/v1/integrations/sync", headers=HEAD)).json()
    assert [run["status"] for run in runs] == ["success", "success"]
    assert runs[0]["source_code"] == "lms"
    assert runs[0]["records_created"] > 0

    programs = (await client.get("/api/v1/catalog/programs", headers=ADMIN)).json()
    assert "Инженер DevOps" in {program["name"] for program in programs}

    universities = (await client.get("/api/v1/universities", headers=ADMIN)).json()
    assert universities["total"] == 3

    # Заявки с сайта превратились в договоры с запущенным процессом.
    contracts = (await client.get("/api/v1/contracts", headers=ADMIN)).json()
    numbers = {item["number"] for item in contracts["items"]}
    assert numbers == {"ЗАЯВКА-req-2026-001", "ЗАЯВКА-req-2026-002"}

    contract_id = contracts["items"][0]["id"]
    workflow = await client.get(f"/api/v1/contracts/{contract_id}/workflow", headers=ADMIN)
    assert workflow.status_code == 200
    assert workflow.json()["status"] == "in_progress"


async def test_repeated_sync_does_not_duplicate(
    client: AsyncClient, workflow_version: dict
) -> None:
    await client.post("/api/v1/integrations/sync", headers=HEAD)
    runs = (await client.post("/api/v1/integrations/sync", headers=HEAD)).json()

    assert all(run["records_created"] == 0 for run in runs)
    assert all(run["records_updated"] > 0 for run in runs)
    assert (await client.get("/api/v1/contracts", headers=ADMIN)).json()["total"] == 2


async def test_runs_are_written_to_journal(
    client: AsyncClient, workflow_version: dict
) -> None:
    await client.post("/api/v1/integrations/sources/lms/sync", headers=HEAD)

    journal = (
        await client.get(
            "/api/v1/integrations/runs", params={"source": "lms"}, headers=MANAGER
        )
    ).json()
    assert len(journal) == 1
    assert journal[0]["status"] == "success"
    assert journal[0]["finished_at"] is not None


async def test_disabled_source_is_not_synced(client: AsyncClient) -> None:
    await client.patch(
        "/api/v1/integrations/sources/lms",
        json={"is_enabled": False},
        headers=ADMIN,
    )
    response = await client.post("/api/v1/integrations/sources/lms/sync", headers=ADMIN)
    assert response.status_code == 400
    assert response.json()["code"] == "integration_failed"


async def test_manager_cannot_start_sync(client: AsyncClient) -> None:
    response = await client.post("/api/v1/integrations/sync", headers=MANAGER)
    assert response.status_code == 403


def _unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("Name or service not known", request=request)


@pytest.mark.parametrize(
    ("respond", "expected"),
    [
        (lambda _: httpx.Response(502), "ответила ошибкой 502"),
        (lambda _: httpx.Response(401), "проверьте токен"),
        (lambda _: httpx.Response(200, text="<html>не JSON</html>"), "не в формате JSON"),
        (lambda request: _unreachable(request), "Не удалось связаться"),
    ],
)
async def test_external_errors_are_readable(
    monkeypatch: pytest.MonkeyPatch, respond: object, expected: str
) -> None:
    """Текст ошибки виден сотрудникам в журнале обмена: без адресов и английского."""
    real_client = httpx.AsyncClient

    def client_with_mock(**kwargs: object) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(base.httpx, "AsyncClient", client_with_mock)
    with pytest.raises(AppError) as error:
        await base.fetch_json("https://lms.internal.example/api/v1/programs", "token")

    assert expected in error.value.message
    assert "lms.internal.example" not in error.value.message
    assert error.value.code == ErrorCode.INTEGRATION_FAILED
