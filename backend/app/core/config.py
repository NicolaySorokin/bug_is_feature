"""Конфигурация приложения. Все значения читаются из переменных окружения."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "EDU CRM API"
    environment: Literal["dev", "prod"] = "dev"
    api_v1_prefix: str = "/api/v1"

    # --- PostgreSQL ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "edu_crm"
    postgres_password: str = "edu_crm"
    postgres_db: str = "edu_crm"
    # Печатать каждый SQL-запрос в лог. Полезно при отладке, шумно в остальное время.
    db_echo: bool = False

    # --- Авторизация ---
    # dev      - заглушка, пользователь берётся из заголовков запроса;
    # keycloak - проверка Bearer-токена по JWKS реалма.
    auth_backend: Literal["dev", "keycloak"] = "dev"
    keycloak_base_url: str = "http://localhost:8080"
    keycloak_realm: str = "edu-crm"
    keycloak_audience: str = "edu-crm-api"
    keycloak_jwks_ttl_seconds: int = 600

    # Пользователь, который подставляется dev-заглушкой, если заголовки не переданы.
    dev_user_subject: str = "00000000-0000-0000-0000-0000000000de"
    dev_user_username: str = "dev"
    dev_user_full_name: str = "Разработчик"
    dev_user_email: str = "dev@example.com"
    dev_user_roles: str = "manager,head,admin"

    # --- Прочее ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    storage_dir: Path = Path("storage")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """URL для Alembic и служебных скриптов без asyncio."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def dev_role_list(self) -> list[str]:
        return [role.strip() for role in self.dev_user_roles.split(",") if role.strip()]

    @property
    def keycloak_issuer(self) -> str:
        return f"{self.keycloak_base_url.rstrip('/')}/realms/{self.keycloak_realm}"

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_issuer}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
