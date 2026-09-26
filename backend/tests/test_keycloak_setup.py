"""Настройка реалма Keycloak: разбор секрета, пароли, адреса возврата."""

import re

import pytest

from scripts.keycloak_setup import (
    SetupError,
    generate_password,
    parse_passwords,
    web_client,
)


def test_passwords_parsed_from_secret() -> None:
    raw = (
        "petrov:Ab3de-fGh4k-mn5Pq-rs6Tu, ivanova:Xy7zA-bC8dE-fG9hJ-kM2nP\n"
        "orlova:Qw3eR-tY4uI-oP5aS-dF6gH"
    )
    assert parse_passwords(raw) == {
        "petrov": "Ab3de-fGh4k-mn5Pq-rs6Tu",
        "ivanova": "Xy7zA-bC8dE-fG9hJ-kM2nP",
        "orlova": "Qw3eR-tY4uI-oP5aS-dF6gH",
    }
    assert parse_passwords("") == {}


@pytest.mark.parametrize("raw", ["petrov", "petrov:", ":secret"])
def test_malformed_secret_is_rejected_without_echoing_password(raw: str) -> None:
    with pytest.raises(SetupError) as error:
        parse_passwords(raw)
    assert "secret" not in str(error.value)


def test_generated_password_fits_realm_policy() -> None:
    """Политика реалма: от 12 знаков, строчные, заглавные и цифры."""
    for _ in range(200):
        password = generate_password()
        assert len(password) >= 12
        assert re.search(r"[a-z]", password)
        assert re.search(r"[A-Z]", password)
        assert re.search(r"[0-9]", password)
        # Без знаков, которые ломают .env, compose и разбор секрета.
        assert re.fullmatch(r"[A-Za-z0-9-]+", password)


def test_web_client_redirects_only_to_environment_origins() -> None:
    client = {
        "clientId": "edu-crm-web",
        "redirectUris": ["http://localhost:3000/*", "https://edu-crm.nikitarodionov.ru/*"],
        "webOrigins": ["+"],
        "attributes": {"pkce.code.challenge.method": "S256"},
    }
    patched = web_client(client, ["https://edu-crm.nikitarodionov.ru"])

    assert patched["redirectUris"] == ["https://edu-crm.nikitarodionov.ru/*"]
    assert patched["webOrigins"] == ["https://edu-crm.nikitarodionov.ru"]
    assert patched["attributes"]["pkce.code.challenge.method"] == "S256"
    # Исходная выгрузка не меняется, другие клиенты не трогаются.
    assert client["webOrigins"] == ["+"]
    api = {"clientId": "edu-crm-api"}
    assert web_client(api, ["https://x"]) == api
