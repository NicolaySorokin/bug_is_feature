"""Подписант договора и договор по типовому шаблону."""

import io
import zipfile
from datetime import date
from urllib.parse import unquote

from httpx import AsyncClient

from app.services import contract_documents
from tests.conftest import ADMIN, HEAD, MANAGER, PURE_HEAD, make_contract

SIGNATORY = {
    "signatory_name": "Смирнов Алексей Викторович",
    "signatory_position": "Проректор по учебной работе",
    "signatory_basis": "доверенности № 12 от 15.01.2026",
}


async def _default_template(client: AsyncClient, headers: dict = MANAGER) -> dict:
    response = await client.get("/api/v1/contract-templates", headers=headers)
    assert response.status_code == 200, response.text
    templates = response.json()
    assert templates, "типовой шаблон заводится при первом обращении"
    return templates[0]


async def _prepared(client: AsyncClient, university: dict) -> tuple[dict, dict, dict]:
    """Вуз с реквизитами, договор с подписантом и шаблон по умолчанию."""
    updated = await client.patch(
        f"/api/v1/universities/{university['id']}",
        json={"inn": "7701234567", "requisites": "Адрес: г. Москва, ул. Учебная, д. 1"},
        headers=ADMIN,
    )
    assert updated.status_code == 200, updated.text
    interaction, contract = await make_contract(client, university["id"], MANAGER, **SIGNATORY)
    return interaction, contract, await _default_template(client)


async def test_signatory_is_part_of_contract(client: AsyncClient, university: dict) -> None:
    """Подписант хранится отдельно от ответственного вместе с договором."""
    interaction, contract = await make_contract(client, university["id"], MANAGER, **SIGNATORY)
    assert contract["signatory_name"] == SIGNATORY["signatory_name"]

    read = await client.get(f"/api/v1/interactions/{interaction['id']}/contract", headers=HEAD)
    assert read.status_code == 200, read.text
    assert {key: read.json()[key] for key in SIGNATORY} == SIGNATORY


async def test_university_requisites(client: AsyncClient, university: dict) -> None:
    response = await client.patch(
        f"/api/v1/universities/{university['id']}",
        json={"requisites": "КПП 770101001\nОГРН 1027700000000"},
        headers=ADMIN,
    )
    assert response.status_code == 200, response.text
    detail = await client.get(f"/api/v1/universities/{university['id']}", headers=ADMIN)
    assert detail.json()["requisites"] == "КПП 770101001\nОГРН 1027700000000"


async def test_default_template_and_fields(client: AsyncClient) -> None:
    template = await _default_template(client)
    assert template["is_active"]
    assert "{{вуз}}" in template["body"]
    # Повторное обращение не заводит второй типовой шаблон.
    again = await client.get("/api/v1/contract-templates", headers=HEAD)
    assert len(again.json()) == 1
    # Его завела система, а не менеджер, который первым открыл список.
    journal = await client.get(
        "/api/v1/audit", params={"entity_type": "contract_templates"}, headers=ADMIN
    )
    assert [entry["user_id"] for entry in journal.json()["items"]] == [None]

    fields = await client.get("/api/v1/contract-templates/fields", headers=MANAGER)
    assert fields.status_code == 200, fields.text
    keys = {item["key"] for item in fields.json()}
    assert {"вуз", "инн_вуза", "реквизиты_вуза", "подписант_вуза", "программы"} <= keys


async def test_templates_are_edited_by_head(client: AsyncClient) -> None:
    body = {"name": "Доп. соглашение", "body": "# СОГЛАШЕНИЕ № {{номер_договора}}"}
    for headers in (MANAGER, ADMIN):
        denied = await client.post("/api/v1/contract-templates", json=body, headers=headers)
        assert denied.status_code == 403, denied.text

    created = await client.post("/api/v1/contract-templates", json=body, headers=PURE_HEAD)
    assert created.status_code == 201, created.text
    assert created.json()["updated_by"]["full_name"]

    # Выключенный шаблон менеджер не видит и документ по нему не формирует.
    template_id = created.json()["id"]
    off = await client.put(
        f"/api/v1/contract-templates/{template_id}",
        json={**body, "is_active": False},
        headers=PURE_HEAD,
    )
    assert off.status_code == 200, off.text
    visible = await client.get("/api/v1/contract-templates", headers=MANAGER)
    assert template_id not in {item["id"] for item in visible.json()}
    everything = await client.get("/api/v1/contract-templates", headers=PURE_HEAD)
    assert template_id in {item["id"] for item in everything.json()}

    # Администратор взаимодействия не ведёт, шаблоны ему не нужны.
    listing = await client.get("/api/v1/contract-templates", headers=ADMIN)
    assert listing.status_code == 403


async def test_unknown_field_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/contract-templates",
        json={"name": "С опечаткой", "body": "Вуз: {{вуз}}, ИНН {{ин_вуза}}"},
        headers=HEAD,
    )
    assert response.status_code == 422, response.text
    assert response.json()["details"]["unknown_fields"] == ["ин_вуза"]
    assert "{{ин_вуза}}" in response.json()["message"]


async def test_preview_fills_requisites(client: AsyncClient, university: dict) -> None:
    interaction, contract, template = await _prepared(client, university)
    response = await client.post(
        f"/api/v1/interactions/{interaction['id']}/contract/document/preview",
        json={"template_id": template["id"]},
        headers=MANAGER,
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    text = preview["text"]
    assert contract["number"] in text
    assert university["name"] in text
    assert "ИНН 7701234567" in text
    assert "ул. Учебная" in text
    assert "Проректор по учебной работе Смирнов Алексей Викторович" in text
    assert "А. В. Смирнов" in text
    assert "доверенности № 12 от 15.01.2026" in text
    assert "{{" not in text
    assert preview["filename"] == f"Проект договора {contract['number']}.docx"
    # Контактов у взаимодействия нет, это видно до формирования файла.
    missing = {item["key"] for item in preview["missing"]}
    assert "контакт_вуза" in missing
    assert "вуз" not in missing
    assert contract_documents.BLANK in text


async def test_docx_download(client: AsyncClient, university: dict) -> None:
    interaction, contract, template = await _prepared(client, university)
    response = await client.post(
        f"/api/v1/interactions/{interaction['id']}/contract/document",
        json={"template_id": template["id"]},
        headers=MANAGER,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    disposition = response.headers["content-disposition"]
    assert unquote(disposition.split("filename*=UTF-8''")[1]) == (
        f"Проект договора {contract['number']}.docx"
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert {"[Content_Types].xml", "word/document.xml", "_rels/.rels"} <= names
        document = archive.read("word/document.xml").decode("utf-8")
    assert contract["number"] in document
    assert "Смирнов Алексей Викторович" in document
    assert "«Ростелеком»" in document


async def test_attach_as_contract_draft(client: AsyncClient, university: dict) -> None:
    """Проект по шаблону лежит во вложениях, но это не «Договор»."""
    interaction, contract, template = await _prepared(client, university)
    response = await client.post(
        f"/api/v1/interactions/{interaction['id']}/contract/document/attach",
        json={"template_id": template["id"]},
        headers=MANAGER,
    )
    assert response.status_code == 201, response.text
    attachment = response.json()
    assert attachment["document_type"] == "contract_draft"
    assert attachment["original_name"] == f"Проект договора {contract['number']}.docx"

    files = await client.get(
        f"/api/v1/interactions/{interaction['id']}/attachments", headers=MANAGER
    )
    assert [item["id"] for item in files.json()] == [attachment["id"]]
    download = await client.get(attachment["download_url"], headers=MANAGER)
    assert download.status_code == 200
    assert zipfile.is_zipfile(io.BytesIO(download.content))


def test_render_and_helpers() -> None:
    text, missing = contract_documents.render(
        "{{вуз}} / {{ инн_вуза }} / {{неизвестное}}", {"вуз": "МТУСИ", "инн_вуза": None}
    )
    assert text == f"МТУСИ / {contract_documents.BLANK} / {{{{неизвестное}}}}"
    assert [field.key for field in missing] == ["инн_вуза"]
    assert contract_documents.unknown_fields("{{вуз}} {{нет}} {{нет}}") == ["нет"]
    assert contract_documents.initials("Иванова Мария Сергеевна") == "М. С. Иванова"
    assert contract_documents.initials("Иванов") == "Иванов"
    assert contract_documents.long_date(date(2026, 9, 1)) == "«01» сентября 2026 г."
    assert contract_documents.unknown_fields(contract_documents.DEFAULT_BODY) == []
