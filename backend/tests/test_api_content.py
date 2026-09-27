"""Комментарии, файлы и лицензии взаимодействия.

Рабочие материалы принадлежат взаимодействию: переписка и документы
появляются задолго до договора. Лицензия - по договору, на продукт
взаимодействия.
"""

from datetime import date, timedelta

from httpx import AsyncClient

from tests.conftest import (
    ADMIN,
    HEAD,
    MANAGER,
    OTHER_MANAGER,
    contract_payload,
    make_contract,
    make_interaction,
)

# Наименьший возможный PNG: содержимое файла для проверок не важно.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


async def test_comment_is_added_and_listed(client: AsyncClient, university: dict) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)
    url = f"/api/v1/interactions/{interaction['id']}/comments"

    created = await client.post(url, json={"text": "Договорились о встрече"}, headers=MANAGER)
    assert created.status_code == 201, created.text
    assert created.json()["author"]["username"] == "petrov"

    listing = await client.get(url, headers=MANAGER)
    assert [item["text"] for item in listing.json()] == ["Договорились о встрече"]


async def test_file_is_uploaded_with_document_type(
    client: AsyncClient, university: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)

    uploaded = await client.post(
        f"/api/v1/interactions/{interaction['id']}/attachments",
        files={"file": ("скан.png", PNG, "image/png")},
        data={"document_type": "contract"},
        headers=MANAGER,
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    assert attachment["original_name"] == "скан.png"
    assert attachment["size_bytes"] == len(PNG)
    assert attachment["document_type"] == "contract"

    downloaded = await client.get(attachment["download_url"], headers=MANAGER)
    assert downloaded.status_code == 200
    assert downloaded.content == PNG

    # Без типа документ - «прочее».
    other = await client.post(
        f"/api/v1/interactions/{interaction['id']}/attachments",
        files={"file": ("фото.png", PNG, "image/png")},
        headers=MANAGER,
    )
    assert other.json()["document_type"] == "other"


async def test_unsupported_file_type_is_rejected(
    client: AsyncClient, university: dict
) -> None:
    interaction = await make_interaction(client, university["id"], MANAGER)

    response = await client.post(
        f"/api/v1/interactions/{interaction['id']}/attachments",
        files={"file": ("скрипт.exe", b"MZ", "application/octet-stream")},
        headers=MANAGER,
    )
    assert response.status_code == 415
    body = response.json()
    assert body["code"] == "file_type_not_allowed"
    assert "pdf" in body["details"]["allowed"]


async def test_foreign_interaction_files_are_closed(
    client: AsyncClient, university: dict
) -> None:
    foreign = await make_interaction(client, university["id"], OTHER_MANAGER)
    uploaded = (
        await client.post(
            f"/api/v1/interactions/{foreign['id']}/attachments",
            files={"file": ("скан.png", PNG, "image/png")},
            headers=OTHER_MANAGER,
        )
    ).json()

    listing = await client.get(
        f"/api/v1/interactions/{foreign['id']}/attachments", headers=MANAGER
    )
    assert listing.status_code == 403
    download = await client.get(uploaded["download_url"], headers=MANAGER)
    assert download.status_code == 403


async def _interaction_with_product(client: AsyncClient, university: dict) -> tuple[dict, str]:
    program = (
        await client.post("/api/v1/catalog/programs", json={"name": "Курс"}, headers=ADMIN)
    ).json()
    product = (
        await client.post(
            "/api/v1/catalog/products", json={"name": "Платформа"}, headers=ADMIN
        )
    ).json()
    await client.put(
        f"/api/v1/catalog/programs/{program['id']}/products",
        json={"product_ids": [product["id"]]},
        headers=HEAD,
    )
    interaction = await make_interaction(
        client, university["id"], MANAGER, program_ids=[program["id"]]
    )
    detail = (
        await client.get(f"/api/v1/interactions/{interaction['id']}", headers=MANAGER)
    ).json()
    link = await client.post(
        f"/api/v1/interactions/{interaction['id']}/products",
        json={
            "product_id": product["id"],
            "program_link_ids": [detail["program_links"][0]["id"]],
        },
        headers=MANAGER,
    )
    assert link.status_code == 201, link.text
    return interaction, link.json()["id"]


async def test_license_needs_contract(client: AsyncClient, university: dict) -> None:
    interaction, link_id = await _interaction_with_product(client, university)
    url = f"/api/v1/interactions/{interaction['id']}/products/{link_id}/licenses"

    without_contract = await client.post(url, json={"number": "ЛИЦ-1"}, headers=MANAGER)
    assert without_contract.status_code == 409

    await client.put(
        f"/api/v1/interactions/{interaction['id']}/contract",
        json=contract_payload(number="ДГ-7"),
        headers=MANAGER,
    )
    created = await client.post(url, json={"number": "ЛИЦ-1"}, headers=MANAGER)
    assert created.status_code == 201, created.text


async def test_license_lifecycle(client: AsyncClient, university: dict) -> None:
    interaction, link_id = await _interaction_with_product(client, university)
    contract = (
        await client.put(
            f"/api/v1/interactions/{interaction['id']}/contract",
            json=contract_payload(),
            headers=MANAGER,
        )
    ).json()
    valid_to = (date.today() + timedelta(days=200)).isoformat()

    created = await client.post(
        f"/api/v1/interactions/{interaction['id']}/products/{link_id}/licenses",
        json={"number": "ЛИЦ-1", "seats": 50, "valid_to": valid_to},
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
    assert item["interaction_id"] == interaction["id"]
    assert item["product_name"] == "Платформа"
    assert item["days_left"] == 200

    licenses = await client.get(
        f"/api/v1/interactions/{interaction['id']}/licenses", headers=MANAGER
    )
    assert len(licenses.json()) == 1

    # Продукт с лицензиями из состава не убрать.
    removed = await client.delete(
        f"/api/v1/interactions/{interaction['id']}/products/{link_id}", headers=MANAGER
    )
    assert removed.status_code == 409


async def test_overdue_license_expires_by_itself(
    client: AsyncClient, university: dict
) -> None:
    interaction, link_id = await _interaction_with_product(client, university)
    await client.put(
        f"/api/v1/interactions/{interaction['id']}/contract",
        json=contract_payload(signed_at=(date.today() - timedelta(days=30)).isoformat()),
        headers=MANAGER,
    )
    created = await client.post(
        f"/api/v1/interactions/{interaction['id']}/products/{link_id}/licenses",
        json={
            "number": "ЛИЦ-2",
            "status": "active",
            "valid_to": (date.today() - timedelta(days=1)).isoformat(),
        },
        headers=MANAGER,
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "expired"


async def test_contract_with_licenses_is_not_deleted(
    client: AsyncClient, university: dict
) -> None:
    interaction, contract = await make_contract(client, university["id"], MANAGER)
    response = await client.delete(
        f"/api/v1/interactions/{interaction['id']}/contract", headers=MANAGER
    )
    # Действующий договор не удаляют - закрывают.
    assert response.status_code == 409
    assert contract["status"] == "active"


async def test_file_type_is_taken_from_extension(
    client: AsyncClient, university: dict
) -> None:
    """Тип содержимого при скачивании - по проверенному расширению, а не со слов браузера."""
    interaction = await make_interaction(client, university["id"], MANAGER)
    uploaded = await client.post(
        f"/api/v1/interactions/{interaction['id']}/attachments",
        files={"file": ("схема.png", PNG, "text/html")},
        headers=MANAGER,
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["mime_type"] == "image/png"
    downloaded = await client.get(uploaded.json()["download_url"], headers=MANAGER)
    assert downloaded.headers["content-type"] == "image/png"
