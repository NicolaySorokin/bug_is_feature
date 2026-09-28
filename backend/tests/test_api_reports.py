"""Отчёты, выгрузки и диаграммы по взаимодействиям."""

from httpx import AsyncClient

from tests.conftest import (
    ADMIN,
    HEAD,
    MANAGER,
    OTHER_MANAGER,
    make_contract,
    make_interaction,
)


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
    await make_interaction(client, university["id"], MANAGER, program_ids=[program_id])
    await make_interaction(client, university["id"], MANAGER, start=False)

    report = (await client.post("/api/v1/reports/preview", json={}, headers=MANAGER)).json()

    assert report["totals"]["interactions"] == 2
    assert report["totals"]["contracts"] == 0
    assert report["totals"]["rows"] == 2  # одно взаимодействие с программой, одно без
    statuses = next(c for c in report["charts"] if c["key"] == "by_status")
    assert sum(item["value"] for item in statuses["items"]) == 2
    # Статусы полным рядом по порядку жизненного цикла, в том числе нулевые.
    assert [item["label"] for item in statuses["items"]] == [
        "Черновик",
        "В работе",
        "Заблокировано",
        "Завершено",
        "Отменено",
    ]
    assert [item["value"] for item in statuses["items"]] == [1, 1, 0, 0, 0]
    # Закрытых нет, поэтому у результатов «Нет данных», а не ряд нулей.
    outcomes = next(c for c in report["charts"] if c["key"] == "by_outcome")
    assert outcomes["items"] == []

    # Диаграмма строится по той же выборке: после фильтра изменились обе.
    filtered = (
        await client.post(
            "/api/v1/reports/preview",
            json={"filters": {"statuses": ["in_progress"]}},
            headers=MANAGER,
        )
    ).json()
    assert filtered["totals"]["interactions"] == 1
    assert filtered["rows"][0]["program"] == "Python-разработчик"
    statuses = next(c for c in filtered["charts"] if c["key"] == "by_status")
    assert sum(item["value"] for item in statuses["items"]) == 1


async def test_report_respects_record_level_rights(
    client: AsyncClient, university: dict
) -> None:
    await make_interaction(client, university["id"], MANAGER)
    await make_interaction(client, university["id"], OTHER_MANAGER)

    mine = (await client.post("/api/v1/reports/preview", json={}, headers=MANAGER)).json()
    team = (await client.post("/api/v1/reports/preview", json={}, headers=HEAD)).json()

    assert mine["totals"]["interactions"] == 1
    assert team["totals"]["interactions"] == 2
    # Администратору без бизнес-роли отчёты не положены.
    denied = await client.post("/api/v1/reports/preview", json={}, headers=ADMIN)
    assert denied.status_code == 403


async def test_report_filters_by_outcome(client: AsyncClient, university: dict) -> None:
    cancelled = await make_interaction(client, university["id"], MANAGER)
    await make_interaction(client, university["id"], MANAGER)
    await client.post(
        f"/api/v1/interactions/{cancelled['id']}/cancel",
        json={"reason": "university_refused"},
        headers=MANAGER,
    )
    report = (
        await client.post(
            "/api/v1/reports/preview",
            json={
                "filters": {"outcomes": ["unsuccessful"]},
                "columns": ["university", "outcome", "closure_reason"],
            },
            headers=MANAGER,
        )
    ).json()
    assert report["totals"]["interactions"] == 1
    assert report["rows"][0]["closure_reason_label"] == "Отказ вуза"
    outcomes = next(c for c in report["charts"] if c["key"] == "by_outcome")
    assert [(item["label"], item["value"]) for item in outcomes["items"]] == [
        ("Успешно", 0),
        ("Частично успешно", 0),
        ("Неуспешно", 1),
    ]


async def test_period_by_signing_date_excludes_unsigned(
    client: AsyncClient, university: dict
) -> None:
    await make_contract(
        client,
        university["id"],
        MANAGER,
        signed_at="2026-03-01",
        valid_from="2026-03-01",
        number="ДГ-МАРТ",
    )
    await make_contract(
        client,
        university["id"],
        MANAGER,
        signed_at="2026-09-01",
        valid_from="2026-09-01",
        number="ДГ-СЕНТЯБРЬ",
    )
    await make_interaction(client, university["id"], MANAGER)  # без договора

    report = (
        await client.post(
            "/api/v1/reports/preview",
            json={
                "filters": {
                    "date_from": "2026-01-01",
                    "date_to": "2026-06-30",
                    "period_basis": "signed",
                }
            },
            headers=MANAGER,
        )
    ).json()
    assert report["totals"]["contracts"] == 1
    assert report["rows"][0]["contract_number"] == "ДГ-МАРТ"
    # Неподписанное взаимодействие не потеряно молча, о нём сказано отдельно.
    assert report["totals"]["unsigned_excluded"] == 1


async def test_exports_return_files(client: AsyncClient, university: dict) -> None:
    await make_interaction(client, university["id"], MANAGER)

    xlsx = await client.post("/api/v1/reports/export?format=xlsx", json={}, headers=MANAGER)
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"  # книга Excel это zip-архив
    assert "attachment" in xlsx.headers["content-disposition"]

    pdf = await client.post("/api/v1/reports/export?format=pdf", json={}, headers=MANAGER)
    assert pdf.content[:4] == b"%PDF"

    # xls это настоящий Excel 97 (OLE2), а не xlsx.
    xls = await client.post("/api/v1/reports/export?format=xls", json={}, headers=MANAGER)
    assert xls.status_code == 200
    assert xls.content[:4] == b"\xd0\xcf\x11\xe0"
    assert xls.headers["content-type"] == "application/vnd.ms-excel"
    assert xls.headers["content-disposition"].endswith('.xls"')

    result_json = await client.post(
        "/api/v1/reports/export?format=json", json={}, headers=MANAGER
    )
    assert result_json.json()["totals"]["interactions"] == 1


async def test_charts_render_in_png_and_pdf(client: AsyncClient, university: dict) -> None:
    await make_interaction(client, university["id"], MANAGER)

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
    await make_interaction(client, university["id"], MANAGER)

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
    assert response.json()["message"] == "Начало периода позже его окончания"


async def test_report_rows_follow_composition_filters(
    client: AsyncClient, university: dict
) -> None:
    """Фильтр по программе, направлению или продукту сужает и строки: другие
    программы того же взаимодействия в отчёт и диаграммы не попадают."""

    async def post(url: str, body: dict, headers: dict = ADMIN) -> dict:
        response = await client.post(url, json=body, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    development = await post("/api/v1/catalog/directions", {"name": "Разработка"})
    testing = await post("/api/v1/catalog/directions", {"name": "Тестирование"})
    python = await post(
        "/api/v1/catalog/programs",
        {"name": "Python-разработчик", "direction_id": development["id"]},
    )
    qa = await post(
        "/api/v1/catalog/programs", {"name": "Тестировщик", "direction_id": testing["id"]}
    )
    sandbox = await post("/api/v1/catalog/products", {"name": "Песочница"})
    await client.put(
        f"/api/v1/catalog/programs/{python['id']}/products",
        json={"product_ids": [sandbox["id"]]},
        headers=HEAD,
    )
    interaction = await make_interaction(
        client, university["id"], MANAGER, program_ids=[python["id"], qa["id"]]
    )
    detail = (
        await client.get(f"/api/v1/interactions/{interaction['id']}", headers=MANAGER)
    ).json()
    python_link = next(
        item["id"] for item in detail["program_links"] if item["program_id"] == python["id"]
    )
    await post(
        f"/api/v1/interactions/{interaction['id']}/products",
        {"product_id": sandbox["id"], "program_link_ids": [python_link]},
        MANAGER,
    )

    async def programs(filters: dict) -> list[str]:
        report = (
            await client.post(
                "/api/v1/reports/preview", json={"filters": filters}, headers=MANAGER
            )
        ).json()
        chart = next(item for item in report["charts"] if item["key"] == "by_program")
        assert sorted(item["label"] for item in chart["items"]) == sorted(
            row["program"] for row in report["rows"]
        )
        return sorted(row["program"] for row in report["rows"])

    assert await programs({}) == ["Python-разработчик", "Тестировщик"]
    assert await programs({"program_ids": [qa["id"]]}) == ["Тестировщик"]
    assert await programs({"direction_ids": [development["id"]]}) == ["Python-разработчик"]
    assert await programs({"product_ids": [sandbox["id"]]}) == ["Python-разработчик"]
