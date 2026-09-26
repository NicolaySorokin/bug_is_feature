"""Настройка реалма Keycloak по deploy/keycloak/realm-export.json.

Keycloak хранит данные в PostgreSQL, поэтому выгрузка реалма импортируется
только при самом первом запуске (``--import-realm`` пропускает уже
существующий реалм). Правки выгрузки в работающий реалм переносит этот
скрипт; деплой запускает его после каждого подъёма стенда:

* настройки реалма (политика паролей, сроки токенов, защита от подбора,
  тема страницы входа) приводятся к выгрузке;
* клиенты приводятся к выгрузке; адреса возврата клиентской части
  берутся из ``CORS_ORIGINS`` - это адреса веб-интерфейса именно этой среды;
* недостающие роли, клиенты и пользователи заводятся, существующие роли
  и пользователи не трогаются: их роли и профиль меняют администраторы
  из интерфейса CRM;
* пароли пользователей задаются секретом ``KEYCLOAK_USER_PASSWORDS``
  (пары ``логин:пароль`` через запятую) и ставятся тем, у кого пароля
  ещё нет. С ``--reset-passwords`` - всем перечисленным, так меняют
  пароли на новые из секрета.

В репозитории паролей нет. На боевой среде (``ENVIRONMENT=prod``)
пользователь выгрузки без пароля - ошибка: в систему под ним не войти.
В разработке недостающие пароли генерируются и печатаются в консоль.

    python -m scripts.keycloak_setup                    # обычный запуск
    python -m scripts.keycloak_setup --reset-passwords  # сменить пароли на секрет
    python -m scripts.keycloak_setup --loadtest on      # включить клиент нагрузки
    python -m scripts.keycloak_setup --generate-passwords  # новые пароли для секрета

Вызовы идут от администратора Keycloak (реалм master, ``KEYCLOAK_ADMIN``
и ``KEYCLOAK_ADMIN_PASSWORD``) по внутреннему адресу ``KEYCLOAK_INTERNAL_URL``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import string
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REALM_FILE = Path(os.environ.get("KEYCLOAK_REALM_FILE", "/realm/realm-export.json"))
WEB_CLIENT_ID = os.environ.get("KEYCLOAK_WEB_CLIENT_ID", "edu-crm-web")
LOADTEST_CLIENT_ID = "edu-crm-loadtest"

# Разделы выгрузки, которые не являются настройками реалма: их переносят
# отдельные шаги, а PUT реалма с ними заменил бы роли и клиентов целиком.
NOT_SETTINGS = {"users", "clients", "roles", "groups", "clientScopes", "components"}

# Пароль: четыре группы по пять знаков через дефис - 23 символа, около
# 115 бит случайности. Без знаков, которые ломают .env и командную строку
# ($, кавычки, #, пробел), и без похожих друг на друга (0/O, 1/l/I).
ALPHABET = "".join(
    char for char in string.ascii_letters + string.digits if char not in "0O1lI"
)


class SetupError(Exception):
    """Ошибка, после которой продолжать настройку нельзя."""


def log(message: str) -> None:
    print(f"==> {message}", flush=True)


def generate_password() -> str:
    while True:
        groups = ["".join(secrets.choice(ALPHABET) for _ in range(5)) for _ in range(4)]
        password = "-".join(groups)
        # Политика паролей реалма требует и строчные, и заглавные, и цифры.
        if (
            re.search(r"[a-z]", password)
            and re.search(r"[A-Z]", password)
            and re.search(r"[0-9]", password)
        ):
            return password


def parse_passwords(raw: str) -> dict[str, str]:
    """``логин:пароль`` через запятую, пробел или перевод строки."""
    result: dict[str, str] = {}
    for item in re.split(r"[\s,]+", raw.strip()):
        if not item:
            continue
        login, sep, password = item.partition(":")
        if not sep or not login or not password:
            raise SetupError(
                f"KEYCLOAK_USER_PASSWORDS: «{item.split(':')[0]}:…» - ожидается логин:пароль"
            )
        result[login] = password
    return result


def web_origins() -> list[str]:
    origins = os.environ.get("CORS_ORIGINS", "")
    return [origin.strip().rstrip("/") for origin in origins.split(",") if origin.strip()]


class Keycloak:
    """Admin REST API: токен администратора master обновляется по мере истечения."""

    def __init__(self, base_url: str, realm: str, username: str, password: str) -> None:
        self.base = base_url.rstrip("/")
        self.realm = realm
        self._username = username
        self._password = password
        self._token = ""
        self._expires = 0.0
        self.http = httpx.Client(timeout=30)

    def wait(self, timeout: float) -> None:
        """Keycloak после пересоздания контейнера поднимается не сразу."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                self._login()
                return
            except (httpx.HTTPError, SetupError) as exc:
                if time.monotonic() > deadline:
                    raise SetupError(f"Keycloak не ответил за {timeout:.0f} с: {exc}") from exc
                time.sleep(3)

    def _login(self) -> None:
        response = self.http.post(
            f"{self.base}/realms/master/protocol/openid-connect/token",
            data={
                "client_id": "admin-cli",
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
            },
        )
        if response.status_code in (400, 401):
            raise SetupError("Keycloak не принял KEYCLOAK_ADMIN и KEYCLOAK_ADMIN_PASSWORD")
        response.raise_for_status()
        body = response.json()
        self._token = body["access_token"]
        self._expires = time.monotonic() + body.get("expires_in", 60) - 10

    def request(
        self, method: str, path: str, *, json_body: Any = None, params: Any = None
    ) -> httpx.Response:
        if time.monotonic() > self._expires:
            self._login()
        url = f"{self.base}/admin/realms{path}"
        response = self.http.request(
            method,
            url,
            json=json_body,
            params=params,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        if response.status_code >= 400 and response.status_code != 404:
            raise SetupError(f"{method} {path}: {response.status_code} {response.text[:300]}")
        return response

    def realm_path(self, path: str = "") -> str:
        return f"/{self.realm}{path}"

    def find_client(self, client_id: str) -> dict[str, Any] | None:
        found = self.request(
            "GET", self.realm_path("/clients"), params={"clientId": client_id}
        ).json()
        return found[0] if found else None

    def find_user(self, username: str) -> dict[str, Any] | None:
        found = self.request(
            "GET",
            self.realm_path("/users"),
            params={"username": username, "exact": "true", "briefRepresentation": "true"},
        ).json()
        return found[0] if found else None

    def has_password(self, user_id: str) -> bool:
        credentials = self.request("GET", self.realm_path(f"/users/{user_id}/credentials"))
        return any(item.get("type") == "password" for item in credentials.json())

    def set_password(self, user_id: str, password: str) -> None:
        self.request(
            "PUT",
            self.realm_path(f"/users/{user_id}/reset-password"),
            json_body={"type": "password", "value": password, "temporary": False},
        )


def load_realm() -> dict[str, Any]:
    if not REALM_FILE.is_file():
        raise SetupError(f"Нет файла выгрузки реалма {REALM_FILE}")
    realm = json.loads(REALM_FILE.read_text("utf-8"))
    for user in realm.get("users", []):
        if user.get("credentials"):
            raise SetupError(
                f"В выгрузке реалма есть пароль пользователя {user['username']}: "
                "пароли задаются только секретом KEYCLOAK_USER_PASSWORDS"
            )
    return realm


def web_client(client: dict[str, Any], origins: list[str]) -> dict[str, Any]:
    """Адреса возврата клиентской части - адреса интерфейса этой среды."""
    if client.get("clientId") != WEB_CLIENT_ID or not origins:
        return client
    patched = dict(client)
    patched["redirectUris"] = [f"{origin}/*" for origin in origins]
    patched["webOrigins"] = origins
    attributes = dict(patched.get("attributes") or {})
    attributes["post.logout.redirect.uris"] = "##".join(f"{origin}/*" for origin in origins)
    patched["attributes"] = attributes
    return patched


def apply_realm(kc: Keycloak, realm: dict[str, Any], origins: list[str]) -> None:
    clients = [web_client(client, origins) for client in realm.get("clients", [])]

    if kc.request("GET", kc.realm_path()).status_code == 404:
        log(f"Реалма {kc.realm} нет - создаю из выгрузки")
        kc.request("POST", "", json_body={**realm, "clients": clients})
        return

    # Недостающее - одним частичным импортом: он сохраняет id пользователей
    # из выгрузки (к ним привязаны договоры демоданных) и их роли.
    result = kc.request(
        "POST",
        kc.realm_path("/partialImport"),
        json_body={
            "ifResourceExists": "SKIP",
            "roles": realm.get("roles", {}),
            "clients": clients,
            "users": realm.get("users", []),
        },
    ).json()
    added = [
        f"{item['resourceType'].lower()} {item['resourceName']}"
        for item in result.get("results", [])
        if item.get("action") == "ADDED"
    ]
    if added:
        log("Заведено: " + ", ".join(added))

    settings = {key: value for key, value in realm.items() if key not in NOT_SETTINGS}
    ssl_required = os.environ.get("KEYCLOAK_SSL_REQUIRED")
    if ssl_required:
        settings["sslRequired"] = ssl_required
    kc.request("PUT", kc.realm_path(), json_body=settings)
    log("Настройки реалма приведены к выгрузке")

    for client in clients:
        current = kc.find_client(client["clientId"])
        if current is None:
            continue
        # Мапперы и секреты переносятся только при заведении клиента:
        # PUT с ними дублировал бы мапперы.
        update = {
            key: value
            for key, value in client.items()
            if key not in {"protocolMappers", "secret"}
        }
        kc.request(
            "PUT",
            kc.realm_path(f"/clients/{current['id']}"),
            json_body={**current, **update},
        )
    log("Клиенты: " + ", ".join(client["clientId"] for client in clients))


def apply_passwords(
    kc: Keycloak,
    realm: dict[str, Any],
    passwords: dict[str, str],
    *,
    reset: bool,
    production: bool,
) -> None:
    usernames = [user["username"] for user in realm.get("users", [])]
    unknown = sorted(set(passwords) - set(usernames))
    missing: list[str] = []
    generated: dict[str, str] = {}
    changed = 0

    for username in usernames + unknown:
        user = kc.find_user(username)
        if user is None:
            log(f"Пароль для {username}: такого пользователя в реалме нет, пропускаю")
            continue
        password = passwords.get(username)
        if not reset and kc.has_password(user["id"]):
            continue
        if password is None:
            if kc.has_password(user["id"]):
                continue
            if production:
                missing.append(username)
                continue
            password = generated[username] = generate_password()
        kc.set_password(user["id"], password)
        changed += 1

    if missing:
        raise SetupError(
            "Нет пароля для пользователей " + ", ".join(missing) + ": добавьте их в "
            "KEYCLOAK_USER_PASSWORDS (секрет PROD_ENV), иначе под ними не войти"
        )
    log(f"Пароли: установлено {changed}, остальные без изменений")
    if generated:
        # Только в разработке: на боевой среде пароли приходят из секрета,
        # а журнал деплоя публичного репозитория виден всем.
        log("Сгенерированы пароли (среда разработки):")
        for username, password in generated.items():
            print(f"    {username}: {password}")


def toggle_loadtest(kc: Keycloak, enabled: bool) -> None:
    client = kc.find_client(LOADTEST_CLIENT_ID)
    if client is None:
        raise SetupError(f"В реалме нет клиента {LOADTEST_CLIENT_ID}")
    kc.request(
        "PUT",
        kc.realm_path(f"/clients/{client['id']}"),
        json_body={**client, "enabled": enabled},
    )
    state = "включён" if enabled else "выключен"
    log(f"Клиент нагрузочной проверки {LOADTEST_CLIENT_ID} {state}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Настройка реалма Keycloak по выгрузке")
    parser.add_argument(
        "--reset-passwords",
        action="store_true",
        help="поставить пароли из KEYCLOAK_USER_PASSWORDS всем перечисленным",
    )
    parser.add_argument(
        "--loadtest",
        choices=["on", "off"],
        help="только включить или выключить клиент нагрузочной проверки",
    )
    parser.add_argument(
        "--generate-passwords",
        action="store_true",
        help="напечатать новые пароли для секрета и выйти, Keycloak не нужен",
    )
    parser.add_argument("--wait", type=float, default=300, help="сколько ждать Keycloak, с")
    args = parser.parse_args()

    try:
        realm = load_realm()
        if args.generate_passwords:
            pairs = [f"{user['username']}:{generate_password()}" for user in realm["users"]]
            print("KEYCLOAK_USER_PASSWORDS=" + ",".join(pairs))
            return 0

        production = os.environ.get("ENVIRONMENT", "dev") == "prod"
        passwords = parse_passwords(os.environ.get("KEYCLOAK_USER_PASSWORDS", ""))
        admin_password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")
        if not admin_password:
            raise SetupError("Не задан KEYCLOAK_ADMIN_PASSWORD")

        kc = Keycloak(
            os.environ.get("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080"),
            os.environ.get("KEYCLOAK_REALM", realm["realm"]),
            os.environ.get("KEYCLOAK_ADMIN", "admin"),
            admin_password,
        )
        log(f"Жду Keycloak: {kc.base}")
        kc.wait(args.wait)

        if args.loadtest:
            toggle_loadtest(kc, args.loadtest == "on")
            return 0

        apply_realm(kc, realm, web_origins())
        apply_passwords(
            kc, realm, passwords, reset=args.reset_passwords, production=production
        )
    except SetupError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    log(f"Реалм {kc.realm} настроен")
    return 0


if __name__ == "__main__":
    sys.exit(main())
