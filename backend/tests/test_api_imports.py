"""Загрузка каталогов из XLSX: предпросмотр, проверка, импорт."""

from io import BytesIO

from httpx import AsyncClient
from openpyxl import Workbook

from tests.conftest import ADMIN, HEAD, MANAGER, create_template

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
    "ИТ-программа",
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


async def _interactions(client: AsyncClient) -> dict:
    # Импорт не нашёл ответственного, взаимодействие в очереди руководителя.
    return (await client.get("/api/v1/interactions", headers=HEAD)).json()


async def test_catalog_import_creates_interaction_with_license(client: AsyncClient) -> None:
    await create_template(client)
    program = await client.post(
        "/api/v1/catalog/programs", json={"name": "Python-разработчик"}, headers=ADMIN
    )
    assert program.status_code == 201
    content = book(
        [
            CATALOG_HEADERS,
            [
                "Казанский университет",
                "Ростелеком",
                "Платформа онлайн-обучения",
                "Python-разработчик",
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
    # Проверка это пробная загрузка: итог известен, а данных ещё нет.
    assert checked["run"]["rows_created"] == 1
    assert checked["run"]["rows_failed"] == 0
    # Замечание про ненайденного менеджера не мешает загрузке строки.
    assert all("Предупреждение" in item["message"] for item in checked["errors"])
    assert (await _interactions(client))["total"] == 0

    result = (
        await client.post(f"/api/v1/imports/{run_id}/commit", json={}, headers=ADMIN)
    ).json()
    assert result["run"]["status"] == "completed"
    assert result["run"]["rows_created"] == 1
    assert result["run"]["rows_failed"] == 0
    # Менеджер не найден, вуз новый: об этом сказано, строка загружена.
    messages = " ".join(item["message"] for item in result["errors"])
    assert "не найден" in messages
    assert "на проверку" in messages

    interactions = await _interactions(client)
    assert interactions["total"] == 1
    interaction = interactions["items"][0]
    assert interaction["source"] == "import"
    assert interaction["status"] == "draft"
    assert interaction["contract"]["number"] == "ДГ-2026-100"
    assert interaction["university"]["name"] == "Казанский университет"

    detail = (
        await client.get(f"/api/v1/interactions/{interaction['id']}", headers=HEAD)
    ).json()
    assert detail["product_links"][0]["transfer_status"] == "transferred"
    assert [item["program"]["name"] for item in detail["program_links"]] == [
        "Python-разработчик"
    ]
    # Связи продукта с программой нет в справочнике, это отмеченное исключение.
    assert detail["links"][0]["is_exception"] is True
    assert detail["contacts"][0]["contact"]["full_name"] == "Гафуров Ильдар Рашидович"

    university = (
        await client.get(
            f"/api/v1/universities/{interaction['university']['id']}", headers=HEAD
        )
    ).json()
    assert university["status"] == "pending"

    licenses = (await client.get("/api/v1/licenses", headers=HEAD)).json()
    assert licenses["items"][0]["valid_to"] == "2027-12-31"


async def test_repeated_import_updates_instead_of_duplicating(
    client: AsyncClient,
) -> None:
    await create_template(client)
    row = ["Вуз", None, None, None, "ДГ-1", None, None, None, None, None, None]
    content = book([CATALOG_HEADERS, row])

    first = await _upload(client, content, "catalog")
    await client.post(f"/api/v1/imports/{first['run']['id']}/commit", json={}, headers=ADMIN)

    second = await _upload(client, content, "catalog")
    result = (
        await client.post(
            f"/api/v1/imports/{second['run']['id']}/commit", json={}, headers=ADMIN
        )
    ).json()

    assert result["run"]["rows_created"] == 0
    assert result["run"]["rows_updated"] == 1
    assert (await _interactions(client))["total"] == 1


async def test_bad_values_are_reported_per_row(client: AsyncClient) -> None:
    content = book(
        [
            CATALOG_HEADERS,
            ["Вуз", None, None, None, "ДГ-2", "вчера", None, None, None, None, None],
            [None, None, None, None, "ДГ-3", None, None, None, None, None, None],
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
    await create_template(client)
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

    universities = (
        await client.get("/api/v1/universities", params={"status": "pending"}, headers=ADMIN)
    ).json()
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


async def test_university_import_matches_by_inn(client: AsyncClient) -> None:
    """ИНН узнаёт вуз даже под другим названием, а одноимённый вуз с другим ИНН
    не подменяет существующий.
    """
    created = await client.post(
        "/api/v1/universities",
        json={"name": "Томский университет", "inn": "7018012345", "city": "Томск"},
        headers=ADMIN,
    )
    assert created.status_code == 201, created.text
    university_id = created.json()["id"]

    content = book(
        [
            ["Название ВУЗа", "ИНН", "Сайт"],
            ["Национальный исследовательский ТГУ", "7018012345", "https://tsu.example"],
            ["Томский университет", "7000000001", ""],
            ["Новый вуз", "12345", ""],
        ]
    )
    preview = await _upload(client, content, "universities")
    assert preview["suggested_mapping"]["inn"] == "ИНН"
    result = (
        await client.post(
            f"/api/v1/imports/{preview['run']['id']}/commit",
            json={"mapping": preview["suggested_mapping"]},
            headers=ADMIN,
        )
    ).json()
    assert result["run"]["rows_updated"] == 1
    assert result["run"]["rows_created"] == 1
    assert result["run"]["rows_failed"] == 1
    assert any("ИНН" in (error["message"] or "") for error in result["errors"])

    same = (await client.get(f"/api/v1/universities/{university_id}", headers=ADMIN)).json()
    assert same["name"] == "Томский университет"
    assert same["website"] == "https://tsu.example"

    pending = (
        await client.get("/api/v1/universities", params={"status": "pending"}, headers=ADMIN)
    ).json()
    assert [item["inn"] for item in pending["items"]] == ["7000000001"]
