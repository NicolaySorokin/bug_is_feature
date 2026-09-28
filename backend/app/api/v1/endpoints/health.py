"""Проверка живости сервиса и служебные словари для клиента."""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select, text

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.errors import ErrorCode
from app.models.user import User
from app.services.labels import ENUM_LABELS
from app.services.storage import ALLOWED_TYPES

router = APIRouter(tags=["service"])


class KeycloakConfig(BaseModel):
    url: str
    realm: str
    client_id: str


class DemoAccount(BaseModel):
    username: str
    full_name: str
    roles: list[str]


class AuthConfig(BaseModel):
    """Как входить в систему. Клиент читает это до входа, поэтому без токена."""

    mode: str
    keycloak: KeycloakConfig | None = None
    # Только в режиме разработки: учётные записи для входа без пароля.
    demo_accounts: list[DemoAccount] = []


@router.get(
    "/health",
    summary="Состояние сервиса",
    description='Отвечает `{"status": "ok"}`, если API работает и база доступна.',
)
async def health(session: SessionDep) -> dict[str, str]:
    # Метод открыт без входа, поэтому сообщает только статус.
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get(
    "/meta/auth",
    response_model=AuthConfig,
    summary="Настройки входа для клиентской части",
    description=(
        "С Keycloak - адрес, реалм и публичный клиент для входа по Authorization "
        "Code + PKCE. В режиме разработки - список учётных записей заглушки."
    ),
)
async def auth_config(session: SessionDep) -> AuthConfig:
    if settings.auth_backend == "keycloak":
        return AuthConfig(
            mode="keycloak",
            keycloak=KeycloakConfig(
                url=settings.keycloak_base_url.rstrip("/"),
                realm=settings.keycloak_realm,
                client_id=settings.keycloak_web_client_id,
            ),
        )

    users = await session.execute(
        select(User)
        .where(User.is_active.is_(True), func.cardinality(User.roles) > 0)
        .order_by(User.full_name)
        .limit(100)
    )
    return AuthConfig(
        mode="dev",
        demo_accounts=[
            DemoAccount(username=user.username, full_name=user.full_name, roles=user.roles)
            for user in users.scalars()
        ],
    )


@router.get(
    "/meta/enums",
    summary="Словари значений и ограничения",
    description=(
        "Подписи статусов, коды ошибок и ограничения на файлы одним ответом: "
        "клиенту не нужно держать эти списки у себя."
    ),
)
async def meta_enums() -> dict[str, object]:
    return {
        "labels": ENUM_LABELS,
        "error_codes": [code.value for code in ErrorCode],
        "uploads": {
            "allowed_extensions": sorted(ALLOWED_TYPES),
            "max_size_mb": settings.max_upload_mb,
        },
        "alerts": {
            "default_sla_days": settings.alert_default_sla_days,
            "expiring_days": settings.alert_expiring_days,
        },
    }
