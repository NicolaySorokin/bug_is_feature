"""Загрузка каталогов из XLSX: предпросмотр, проверка, импорт."""

from io import BytesIO

from httpx import AsyncClient
from openpyxl import Workbook

from tests.conftest import ADMIN, MANAGER

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def book(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


CATALOG_HEADERS = [
    "Название ВУЗа",
    "Вендор",
    "ПО",
    "Номер договора",
    "Подписание лицензии",
    "Срок действия лицензии (год)",
    "Статус по передачи",
    "ФИО Менеджера",
    "Ответственные от ВУЗа",
    "Комментарий",
]


async def _upload(client: AsyncClient, content: bytes, import_type: str) -> dict:
    response = await client.post(
        "/api/v1/imports",
        files={"file": ("catalog.xlsx", content, XLSX_TYPE)},
        data={"type": import_type},
        headers=ADMIN,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_catalog_import_creates_contract_with_license(client: AsyncClient) -> None:
    content = book(
        [
            CATALOG_HEADERS,
            [
                "Казанский университет",
                "Ростелеком",
                "Платформа онлайн-обучения",
                "ДГ-2026-100",
                "01.02.2026",
                "2027",
                "Передано",
                "Неизвестный Сотрудник",
                "Гафуров Ильдар Рашидович",
                "Первый договор",
            ],
        ]
    )
    preview = await _upload(client, content, "catalog")

    # Колонки узнаны по заголовкам, вручную сопоставлять ничего не нужно.
    assert preview["suggested_mapping"]["university_name"] == "Название ВУЗа"
    assert preview["suggested_mapping"]["license_valid_to"] == "Срок действия лицензии (год)"
    assert preview["rows_total"] == 1
    assert preview["sample_rows"][0][0] == "Казанский университет"

    run_id = preview["run"]["id"]
    checked = (
        await client.post(f"/api/v1/imports/{run_id}/validate", json={}, headers=ADMIN)
    ).json()
    assert checked["run"]["status"] == "validated"
    assert checked["errors"] == []

    result = (
        await client.post(f"/api/v1/imports/{run_id}/commit", json={}, headers=ADMIN)
    ).json()
    assert result["run"]["status"] == "completed"
    assert result["run"]["rows_created"] == 1
    assert result["run"]["rows_failed"] == 0
    # Менеджер с таким ФИО не найден - об этом сказано, но строка загружена.
    assert "не найден" in result["errors"][0]["message"]

    contracts = (await client.get("/api/v1/contracts", headers=ADMIN)).json()
    assert contracts["total"] == 1
    contract = contracts["items"][0]
    assert contract["number"] == "ДГ-2026-100"
    assert contract["university"]["name"] == "Казанский университет"

    detail = (
        await client.get(f"/api/v1/contracts/{contract['id']}", headers=ADMIN)
    ).json()
    assert detail["products"][0]["transfer_status"] == "implemented"

    licenses = (await client.get("/api/v1/licenses", headers=ADMIN)).json()
    assert licenses["items"][0]["valid_to"] == "2027-12-31"


async def test_repeated_import_updates_instead_of_duplicating(
    client: AsyncClient,
) -> None:
    row = ["Вуз", None, None, "ДГ-1", None, None, None, None, None, None]
    content = book([CATALOG_HEADERS, row])

    first = await _upload(client, content, "catalog")
    await client.post(
        f"/api/v1/imports/{first['run']['id']}/commit", json={}, headers=ADMIN
    )

    second = await _upload(client, content, "catalog")
    result = (
        await client.post(
            f"/api/v1/imports/{second['run']['id']}/commit", json={}, headers=ADMIN
        )
    ).json()

    assert result["run"]["rows_created"] == 0
    assert result["run"]["rows_updated"] == 1
    assert (await client.get("/api/v1/contracts", headers=ADMIN)).json()["total"] == 1


async def test_bad_values_are_reported_per_row(client: AsyncClient) -> None:
    content = book(
        [
            CATALOG_HEADERS,
            ["Вуз", None, None, "ДГ-2", "вчера", None, None, None, None, None],
            [None, None, None, "ДГ-3", None, None, None, None, None, None],
        ]
    )
    preview = await _upload(client, content, "catalog")
    result = (
        await client.post(
            f"/api/v1/imports/{preview['run']['id']}/validate", json={}, headers=ADMIN
        )
    ).json()

    assert result["run"]["status"] == "failed"
    messages = {(item["row_number"], item["field_name"]) for item in result["errors"]}
    assert (2, "Подписание лицензии") in messages
    assert (3, "Название ВУЗа") in messages


async def test_mapping_can_be_corrected_by_hand(client: AsyncClient) -> None:
    content = book(
        [
            ["Учебное заведение", "Соглашение"],
            ["Северный университет", "ДГ-77"],
        ]
    )
    preview = await _upload(client, content, "catalog")
    assert preview["suggested_mapping"]["university_name"] is None

    result = (
        await client.post(
            f"/api/v1/imports/{preview['run']['id']}/commit",
            json={
                "mapping": {
                    "university_name": "Учебное заведение",
                    "contract_number": "Соглашение",
                }
            },
            headers=ADMIN,
        )
    ).json()
    assert result["run"]["rows_created"] == 1

    universities = (await client.get("/api/v1/universities", headers=ADMIN)).json()
    assert universities["items"][0]["name"] == "Северный университет"


async def test_missing_required_column_is_refused(client: AsyncClient) -> None:
    content = book([["Что-то своё"], ["значение"]])
    preview = await _upload(client, content, "catalog")

    response = await client.post(
        f"/api/v1/imports/{preview['run']['id']}/commit", json={}, headers=ADMIN
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "import_failed"
    assert "Название ВУЗа" in body["message"]


async def test_template_is_downloadable(client: AsyncClient) -> None:
    response = await client.get("/api/v1/imports/template?type=programs", headers=ADMIN)
    assert response.status_code == 200
    assert response.content[:2] == b"PK"


async def test_import_is_closed_for_manager(client: AsyncClient) -> None:
    response = await client.get("/api/v1/imports/types", headers=MANAGER)
    assert response.status_code == 403
