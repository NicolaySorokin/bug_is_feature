"""Аутентификация.

Проверка токена и извлечение ролей вынесены за интерфейс ``AuthBackend``.
В dev-режиме работает заглушка, которая берёт пользователя из заголовков
запроса, в боевом режиме - проверка Bearer-токена Keycloak по JWKS реалма.
Переключение выполняется переменной окружения ``AUTH_BACKEND``, остальной
код про это не знает.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import anyio
import jwt
from fastapi import HTTPException, Request, status

from app.core.config import Settings, settings
from app.enums import Role


@dataclass(frozen=True, slots=True)
class Principal:
    """Пользователь, извлечённый из токена (или подставленный заглушкой)."""

    subject: str
    username: str
    full_name: str
    email: str | None = None
    roles: frozenset[str] = field(default_factory=frozenset)
    # Keycloak - источник истины по профилю, и имя с почтой оттуда затирают
    # локальные значения. Dev-заглушка настоящего имени не знает, поэтому
    # ранее сохранённый профиль она не трогает.
    profile_is_authoritative: bool = True

    def has_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))

    @property
    def is_admin(self) -> bool:
        return Role.ADMIN in self.roles


class AuthBackend(Protocol):
    """Контракт, который должна реализовать любая схема аутентификации."""

    async def authenticate(self, request: Request) -> Principal: ...


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


class DevAuthBackend:
    """Заглушка для разработки.

    Пользователь задаётся заголовками ``X-Dev-User`` и ``X-Dev-Roles``
    (роли через запятую). Если заголовков нет, берутся значения из настроек.
    Никаких токенов не проверяет и в боевом режиме использоваться не должна.
    """

    def __init__(self, config: Settings) -> None:
        self._config = config

    async def authenticate(self, request: Request) -> Principal:
        username = request.headers.get("X-Dev-User") or self._config.dev_user_username
        raw_roles = request.headers.get("X-Dev-Roles")
        roles = (
            [role.strip() for role in raw_roles.split(",") if role.strip()]
            if raw_roles
            else self._config.dev_role_list
        )
        # Стабильный subject: один и тот же заголовок всегда даёт одного пользователя.
        subject = (
            self._config.dev_user_subject
            if username == self._config.dev_user_username
            else f"dev:{username}"
        )
        return Principal(
            subject=subject,
            username=username,
            full_name=(
                self._config.dev_user_full_name
                if username == self._config.dev_user_username
                else username
            ),
            email=(
                self._config.dev_user_email
                if username == self._config.dev_user_username
                else f"{username}@example.com"
            ),
            roles=frozenset(roles),
            profile_is_authoritative=False,
        )


class KeycloakAuthBackend:
    """Проверка Bearer-токена Keycloak по публичным ключам реалма."""

    def __init__(self, config: Settings) -> None:
        self._config = config
        self._jwk_client = jwt.PyJWKClient(
            config.keycloak_jwks_url,
            cache_keys=True,
            lifespan=config.keycloak_jwks_ttl_seconds,
        )

    async def authenticate(self, request: Request) -> Principal:
        token = bearer_token(request)
        if token is None:
            raise _unauthorized("Требуется Bearer-токен")

        try:
            signing_key = await anyio.to_thread.run_sync(
                self._jwk_client.get_signing_key_from_jwt, token
            )
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._config.keycloak_audience,
                issuer=self._config.keycloak_issuer,
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise _unauthorized(f"Токен не прошёл проверку: {exc}") from exc

        return self._to_principal(claims)

    def _to_principal(self, claims: dict[str, Any]) -> Principal:
        realm_roles = claims.get("realm_access", {}).get("roles", [])
        client_roles = (
            claims.get("resource_access", {})
            .get(self._config.keycloak_audience, {})
            .get("roles", [])
        )
        # В документах и отчётах принят порядок «Фамилия Имя»: собираем ФИО
        # из отдельных полей, а поле name (там «Имя Фамилия») - запасной вариант.
        parts = [claims.get("family_name"), claims.get("given_name")]
        full_name = " ".join(part for part in parts if part) or claims.get("name")
        return Principal(
            subject=claims["sub"],
            username=claims.get("preferred_username") or claims["sub"],
            full_name=full_name or claims.get("preferred_username") or claims["sub"],
            email=claims.get("email"),
            roles=frozenset([*realm_roles, *client_roles]),
        )


def build_auth_backend(config: Settings | None = None) -> AuthBackend:
    config = config or settings
    if config.auth_backend == "keycloak":
        return KeycloakAuthBackend(config)
    return DevAuthBackend(config)
