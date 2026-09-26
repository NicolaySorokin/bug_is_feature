"""Настройка реалма Keycloak: начальные пароли, разбор переменной, адреса возврата."""

import re

import pytest

from scripts.keycloak_setup import (
    SetupError,
    apply_passwords,
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


class FakeKeycloak:
    """Реалм в памяти: пользователи, пароли и роль администратора."""

    def __init__(self, users: dict[str, bool], admins: set[str]) -> None:
        # логин -> есть ли пароль
        self.passwords: dict[str, tuple[str, bool] | None] = {
            username: ("старый", False) if has else None for username, has in users.items()
        }
        self.admins = admins

    def find_user(self, username: str) -> dict | None:
        if username not in self.passwords:
            return None
        return {"id": username, "username": username, "enabled": True}

    def has_password(self, user_id: str) -> bool:
        return self.passwords[user_id] is not None

    def set_password(self, user_id: str, password: str, *, temporary: bool = False) -> None:
        self.passwords[user_id] = (password, temporary)

    def role_members(self, role: str) -> list[dict]:
        assert role == "admin"
        return [self.find_user(username) for username in sorted(self.admins)]


REALM = {"users": [{"username": "admin"}, {"username": "orlova"}, {"username": "petrov"}]}


def test_initial_passwords_only_for_users_without_one() -> None:
    """Пароль, сменённый на сайте, деплой не перезаписывает."""
    kc = FakeKeycloak({"admin": True, "orlova": False, "petrov": False}, {"admin"})
    apply_passwords(
        kc,
        REALM,
        {"admin": "Новый-пароль-1", "orlova": "Пароль-Орловой-2"},
        reset=False,
        production=True,
        console_password="Консоль-Keycloak-3",
    )
    assert kc.passwords["admin"] == ("старый", False)
    assert kc.passwords["orlova"] == ("Пароль-Орловой-2", False)
    # Пароля в секрете нет - на бою не придумываем, пароль задаст администратор.
    assert kc.passwords["petrov"] is None


def test_reset_replaces_only_listed_passwords() -> None:
    kc = FakeKeycloak({"admin": True, "orlova": True, "petrov": True}, {"admin"})
    apply_passwords(
        kc,
        REALM,
        {"orlova": "Пароль-Орловой-2"},
        reset=True,
        production=True,
        console_password="Консоль-Keycloak-3",
    )
    assert kc.passwords["orlova"] == ("Пароль-Орловой-2", False)
    assert kc.passwords["admin"] == ("старый", False)
    assert kc.passwords["petrov"] == ("старый", False)


def test_user_deleted_on_site_is_not_recreated() -> None:
    kc = FakeKeycloak({"admin": True, "orlova": True}, {"admin"})
    apply_passwords(
        kc,
        REALM,
        {"petrov": "Пароль-Петрова-4"},
        reset=False,
        production=True,
        console_password="Консоль-Keycloak-3",
    )
    assert "petrov" not in kc.passwords


def test_admin_gets_console_password_when_nobody_can_administer() -> None:
    """Новый реалм без KEYCLOAK_USER_PASSWORDS: войти может хотя бы администратор."""
    kc = FakeKeycloak({"admin": False, "orlova": False, "petrov": False}, {"admin"})
    apply_passwords(
        kc, REALM, {}, reset=False, production=True, console_password="Консоль-Keycloak-3"
    )
    # Временный: Keycloak попросит сменить его при первом входе.
    assert kc.passwords["admin"] == ("Консоль-Keycloak-3", True)
    assert kc.passwords["orlova"] is None
    assert kc.passwords["petrov"] is None


def test_console_password_is_not_used_while_an_admin_can_log_in() -> None:
    kc = FakeKeycloak({"admin": False, "orlova": True, "petrov": False}, {"admin", "orlova"})
    apply_passwords(
        kc, REALM, {}, reset=False, production=True, console_password="Консоль-Keycloak-3"
    )
    assert kc.passwords["admin"] is None


def test_development_generates_missing_passwords() -> None:
    kc = FakeKeycloak({"admin": False, "orlova": True, "petrov": False}, {"admin"})
    apply_passwords(
        kc, REALM, {}, reset=False, production=False, console_password="Консоль-Keycloak-3"
    )
    assert kc.passwords["orlova"] == ("старый", False)
    for username in ("admin", "petrov"):
        password, temporary = kc.passwords[username]
        assert len(password) >= 12 and not temporary


def test_weak_console_password_gives_clear_error() -> None:
    """Keycloak отклонил пароль консоли по политике - понятно, что делать дальше."""

    class StrictKeycloak(FakeKeycloak):
        def set_password(self, user_id: str, password: str, *, temporary: bool = False):
            if len(password) < 12:
                raise SetupError("PUT reset-password: 400 invalidPasswordMinLengthMessage")
            super().set_password(user_id, password, temporary=temporary)

    kc = StrictKeycloak({"admin": False, "orlova": False, "petrov": False}, {"admin"})
    with pytest.raises(SetupError) as error:
        apply_passwords(kc, REALM, {}, reset=False, production=True, console_password="admin")
    assert "KEYCLOAK_USER_PASSWORDS" in str(error.value)
    assert "admin" in str(error.value)
