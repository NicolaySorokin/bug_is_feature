"""Отчёты, выгрузки и диаграммы."""

from httpx import AsyncClient

from tests.conftest import ADMIN, HEAD, MANAGER, OTHER_MANAGER, make_contract


async def _catalog(client: AsyncClient) -> tuple[str, str]:
    direction = (
        await client.post(
            "/api/v1/catalog/directions", json={"name": "Разработка"}, headers=ADMIN
        )
    ).json()
    program = (
        await client.post(
            "/api/v1/catalog/programs",
            json={"name": "Python-разработчик", "direction_id": direction["id"]},
            headers=ADMIN,
        )
    ).json()
    return direction["id"], program["id"]


async def test_report_rows_and_charts_match_selection(
    client: AsyncClient, university: dict
) -> None:
    _, program_id = await _catalog(client)
    await make_contract(
        client, university["id"], MANAGER, program_ids=[program_id], status="active"
    )
    await make_contract(client, university["id"], MANAGER, status="draft")

    report = (await client.post("/api/v1/reports/preview", json={}, headers=MANAGER)).json()

    assert report["totals"]["contracts"] == 2
    assert report["totals"]["rows"] == 2  # один договор с программой, один без
    statuses = next(c for c in report["charts"] if c["key"] == "by_status")
    assert sum(item["value"] for item in statuses["items"]) == 2

    # Диаграмма строится по той же выборке: отфильтровали - изменилось и то, и то.
    filtered = (
        await client.post(
            "/api/v1/reports/preview",
            json={"filters": {"statuses": ["active"]}},
            headers=MANAGER,
        )
    ).json()
    assert filtered["totals"]["contracts"] == 1
    statuses = next(c for c in filtered["charts"] if c["key"] == "by_status")
    assert sum(item["value"] for item in statuses["items"]) == 1


async def test_report_respects_record_level_rights(
    client: AsyncClient, university: dict
) -> None:
    await make_contract(client, university["id"], MANAGER)
    await make_contract(client, university["id"], OTHER_MANAGER)

    mine = (await client.post("/api/v1/reports/preview", json={}, headers=MANAGER)).json()
    all_rows = (await client.post("/api/v1/reports/preview", json={}, headers=HEAD)).json()

    assert mine["totals"]["contracts"] == 1
    assert all_rows["totals"]["contracts"] == 2


async def test_period_filter_uses_signing_date(client: AsyncClient, university: dict) -> None:
    await make_contract(
        client, university["id"], MANAGER, signed_at="2026-03-01", number="ДГ-МАРТ"
    )
    await make_contract(
        client, university["id"], MANAGER, signed_at="2026-09-01", number="ДГ-СЕНТЯБРЬ"
    )

    report = (
        await client.post(
            "/api/v1/reports/preview",
            json={"filters": {"date_from": "2026-01-01", "date_to": "2026-06-30"}},
            headers=MANAGER,
        )
    ).json()
    assert report["totals"]["contracts"] == 1


async def test_exports_return_files(client: AsyncClient, university: dict) -> None:
    await make_contract(client, university["id"], MANAGER)

    xlsx = await client.post("/api/v1/reports/export?format=xlsx", json={}, headers=MANAGER)
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"  # книга Excel - это zip-архив
    assert "attachment" in xlsx.headers["content-disposition"]

    pdf = await client.post("/api/v1/reports/export?format=pdf", json={}, headers=MANAGER)
    assert pdf.content[:4] == b"%PDF"

    # xls - настоящий двоичный формат Excel 97 (контейнер OLE2), а не xlsx.
    xls = await client.post("/api/v1/reports/export?format=xls", json={}, headers=MANAGER)
    assert xls.status_code == 200
    assert xls.content[:4] == b"\xd0\xcf\x11\xe0"
    assert xls.headers["content-type"] == "application/vnd.ms-excel"
    assert xls.headers["content-disposition"].endswith('.xls"')

    result_json = await client.post(
        "/api/v1/reports/export?format=json", json={}, headers=MANAGER
    )
    assert result_json.json()["totals"]["contracts"] == 1


async def test_charts_render_in_png_and_pdf(client: AsyncClient, university: dict) -> None:
    await make_contract(client, university["id"], MANAGER)

    png = await client.post(
        "/api/v1/reports/chart?key=by_status&format=png", json={}, headers=MANAGER
    )
    assert png.status_code == 200
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"

    pdf = await client.post(
        "/api/v1/reports/chart?key=by_stage&format=pdf", json={}, headers=MANAGER
    )
    assert pdf.content[:4] == b"%PDF"


async def test_columns_can_be_chosen(client: AsyncClient, university: dict) -> None:
    await make_contract(client, university["id"], MANAGER)

    report = (
        await client.post(
            "/api/v1/reports/preview",
            json={"columns": ["university", "manager"]},
            headers=MANAGER,
        )
    ).json()
    assert report["columns"] == ["university", "manager"]
    assert report["column_titles"] == {"university": "Вуз", "manager": "Ответственный"}


async def test_broken_period_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/reports/preview",
        json={"filters": {"date_from": "2026-09-01", "date_to": "2026-01-01"}},
        headers=MANAGER,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
