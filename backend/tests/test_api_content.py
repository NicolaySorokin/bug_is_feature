"""Комментарии, файлы и лицензии по договору."""

from httpx import AsyncClient

from tests.conftest import ADMIN, MANAGER, OTHER_MANAGER, make_contract

# Наименьший возможный PNG: содержимое файла для проверок не важно.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


async def test_comment_is_added_and_listed(
    client: AsyncClient, university: dict
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)

    created = await client.post(
        f"/api/v1/contracts/{contract['id']}/comments",
        json={"text": "Договорились о встрече"},
        headers=MANAGER,
    )
    assert created.status_code == 201, created.text
    assert created.json()["author"]["username"] == "petrov"

    listing = await client.get(
        f"/api/v1/contracts/{contract['id']}/comments", headers=MANAGER
    )
    assert [item["text"] for item in listing.json()] == ["Договорились о встрече"]


async def test_file_is_uploaded_and_downloaded(
    client: AsyncClient, university: dict
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)

    uploaded = await client.post(
        f"/api/v1/contracts/{contract['id']}/attachments",
        files={"file": ("скан.png", PNG, "image/png")},
        headers=MANAGER,
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    assert attachment["original_name"] == "скан.png"
    assert attachment["size_bytes"] == len(PNG)

    downloaded = await client.get(attachment["download_url"], headers=MANAGER)
    assert downloaded.status_code == 200
    assert downloaded.content == PNG


async def test_unsupported_file_type_is_rejected(
    client: AsyncClient, university: dict
) -> None:
    contract = await make_contract(client, university["id"], MANAGER)

    response = await client.post(
        f"/api/v1/contracts/{contract['id']}/attachments",
        files={"file": ("скрипт.exe", b"MZ", "application/octet-stream")},
        headers=MANAGER,
    )
    assert response.status_code == 415
    body = response.json()
    assert body["code"] == "file_type_not_allowed"
    assert "pdf" in body["details"]["allowed"]


async def test_foreign_contract_files_are_closed(
    client: AsyncClient, university: dict
) -> None:
    foreign = await make_contract(client, university["id"], OTHER_MANAGER)

    response = await client.get(
        f"/api/v1/contracts/{foreign['id']}/attachments", headers=MANAGER
    )
    assert response.status_code == 403


async def test_license_lifecycle(client: AsyncClient, university: dict) -> None:
    product = (
        await client.post(
            "/api/v1/catalog/products", json={"name": "Платформа"}, headers=ADMIN
        )
    ).json()
    contract = await make_contract(
        client, university["id"], MANAGER, product_ids=[product["id"]]
    )
    detail = (
        await client.get(f"/api/v1/contracts/{contract['id']}", headers=MANAGER)
    ).json()
    link_id = detail["products"][0]["id"]

    created = await client.post(
        f"/api/v1/contracts/{contract['id']}/products/{link_id}/licenses",
        json={"number": "ЛИЦ-1", "seats": 50, "valid_to": "2026-10-01"},
        headers=MANAGER,
    )
    assert created.status_code == 201, created.text
    license_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/licenses/{license_id}", json={"seats": 75}, headers=MANAGER
    )
    assert updated.json()["seats"] == 75

    registry = (
        await client.get(
            "/api/v1/licenses", params={"expiring_in_days": 3650}, headers=MANAGER
        )
    ).json()
    assert registry["total"] == 1
    item = registry["items"][0]
    assert item["contract_number"] == contract["number"]
    assert item["product_name"] == "Платформа"
    assert item["days_left"] is not None

    contract_licenses = await client.get(
        f"/api/v1/contracts/{contract['id']}/licenses", headers=MANAGER
    )
    assert len(contract_licenses.json()) == 1
