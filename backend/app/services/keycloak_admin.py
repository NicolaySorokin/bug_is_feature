"""Управление учётными записями в Keycloak.

ТЗ: администратор управляет правами пользователей из интерфейса системы.
Роли при этом остаются в Keycloak (раздел 8 концепции), поэтому CRM не
хранит их у себя, а вызывает Admin REST API реалма.

Вызов идёт с токеном самого администратора CRM: роль ``admin`` в реалме
составная и включает права realm-management на пользователей
(deploy/keycloak/realm-export.json). Отсюда два следствия:

* в API не нужно хранить секрет служебной учётной записи;
* в журнале событий Keycloak видно, какой именно администратор что менял.

Keycloak вызывается по внутреннему адресу (сеть контейнеров), издатель
токена у него при этом общий - внешний адрес стенда.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.enums import Role

logger = logging.getLogger(__name__)

MANAGED_ROLES: tuple[str, ...] = tuple(role.value for role in Role)


@dataclass(slots=True)
class KeycloakUser:
    id: str
    username: str
    first_name: str = ""
    last_name: str = ""
    email: str | None = None
    enabled: bool = True
    roles: set[str] = field(default_factory=set)


def _error(message: str) -> AppError:
    return AppError(message, code=ErrorCode.IDENTITY_PROVIDER_ERROR, status_code=502)


class KeycloakAdmin:
    """Тонкая обёртка над Admin REST API одного реалма."""

    def __init__(self, token: str) -> None:
        base = (settings.keycloak_internal_url or settings.keycloak_base_url).rstrip("/")
        self._base = f"{base}/admin/realms/{settings.keycloak_realm}"
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                timeout=settings.keycloak_admin_timeout_seconds
            ) as client:
                response = await client.request(
                    method,
                    f"{self._base}{path}",
                    json=json,
                    params=params,
                    headers=self._headers,
                )
        except httpx.HTTPError as exc:
            raise _error(f"Keycloak недоступен: {exc}") from exc

        if response.status_code in (401, 403):
            raise AppError(
                "Keycloak отклонил запрос: у учётной записи нет прав на управление "
                "пользователями реалма",
                code=ErrorCode.FORBIDDEN,
                status_code=403,
            )
        if response.status_code == 409:
            raise AppError(
                "Пользователь с таким логином или почтой уже есть в Keycloak",
                code=ErrorCode.CONFLICT,
                status_code=409,
            )
        if response.status_code == 400 and "password" in response.text.lower():
            # Пароль не прошёл политику реалма: 12 знаков, регистр, цифры, не логин.
            raise AppError(
                "Пароль не подходит: нужно не меньше 12 знаков, строчные и заглавные "
                "буквы, цифры; пароль не должен совпадать с логином и недавними паролями",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=422,
            )
        if response.status_code >= 400:
            logger.warning(
                "Keycloak ответил %s на %s %s: %s",
                response.status_code,
                method,
                path,
                response.text[:500],
            )
            raise _error(f"Keycloak ответил ошибкой {response.status_code}")
        return response

    # --- Роли --------------------------------------------------------------

    async def role_members(self) -> dict[str, set[str]]:
        """Пользователи каждой роли системы: роль -> идентификаторы пользователей."""
        members: dict[str, set[str]] = {}
        for role in MANAGED_ROLES:
            response = await self._request(
                "GET", f"/roles/{role}/users", params={"first": 0, "max": 2000}
            )
            members[role] = {item["id"] for item in response.json()}
        return members

    async def user_roles(self, user_id: str) -> set[str]:
        response = await self._request("GET", f"/users/{user_id}/role-mappings/realm")
        return {item["name"] for item in response.json()} & set(MANAGED_ROLES)

    async def set_roles(self, user_id: str, roles: set[str]) -> set[str]:
        """Приводит роли пользователя к заданному набору (только роли системы)."""
        wanted = roles & set(MANAGED_ROLES)
        response = await self._request("GET", f"/users/{user_id}/role-mappings/realm")
        current = {item["name"]: item for item in response.json()}

        to_remove = [
            current[name] for name in current if name in MANAGED_ROLES and name not in wanted
        ]
        missing = [name for name in wanted if name not in current]
        to_add = [(await self._request("GET", f"/roles/{name}")).json() for name in missing]

        if to_remove:
            await self._request(
                "DELETE", f"/users/{user_id}/role-mappings/realm", json=to_remove
            )
        if to_add:
            await self._request("POST", f"/users/{user_id}/role-mappings/realm", json=to_add)
        return wanted

    # --- Учётные записи ----------------------------------------------------

    async def get_user(self, user_id: str) -> KeycloakUser:
        data = (await self._request("GET", f"/users/{user_id}")).json()
        return KeycloakUser(
            id=data["id"],
            username=data.get("username", ""),
            first_name=data.get("firstName") or "",
            last_name=data.get("lastName") or "",
            email=data.get("email"),
            enabled=bool(data.get("enabled", True)),
        )

    async def set_enabled(self, user_id: str, enabled: bool) -> None:
        await self._request("PUT", f"/users/{user_id}", json={"enabled": enabled})

    async def update_profile(
        self, user_id: str, *, first_name: str, last_name: str, email: str | None
    ) -> None:
        payload: dict[str, Any] = {"firstName": first_name, "lastName": last_name}
        if email:
            payload["email"] = email
        await self._request("PUT", f"/users/{user_id}", json=payload)

    async def create_user(
        self,
        *,
        username: str,
        first_name: str,
        last_name: str,
        email: str | None,
        password: str,
        roles: set[str],
    ) -> str:
        """Заводит учётную запись с временным паролем. Возвращает её id."""
        payload: dict[str, Any] = {
            "username": username,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": True,
            "emailVerified": bool(email),
            # Временный пароль: при первом входе Keycloak попросит сменить его.
            "credentials": [{"type": "password", "value": password, "temporary": True}],
        }
        if email:
            payload["email"] = email
        response = await self._request("POST", "/users", json=payload)

        location = response.headers.get("Location", "")
        user_id = location.rstrip("/").rsplit("/", 1)[-1]
        if not user_id:
            raise _error("Keycloak не вернул идентификатор новой учётной записи")
        if roles:
            await self.set_roles(user_id, roles)
        return user_id

    async def reset_password(
        self, user_id: str, password: str, *, temporary: bool = True
    ) -> None:
        await self._request(
            "PUT",
            f"/users/{user_id}/reset-password",
            json={"type": "password", "value": password, "temporary": temporary},
        )


def split_full_name(full_name: str) -> tuple[str, str]:
    """«Фамилия Имя Отчество» -> (имя, фамилия) для полей Keycloak.

    В Keycloak нет отчества; оно остаётся в CRM, где ФИО хранится целиком.
    """
    parts = full_name.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return "", parts[0]
    return parts[1], parts[0]
