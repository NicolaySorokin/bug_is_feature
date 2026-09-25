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
    # Пул соединений на один рабочий процесс API. В бою процессов несколько
    # (WEB_CONCURRENCY), сумма должна укладываться в max_connections PostgreSQL.
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- Авторизация ---
    # dev      - заглушка, пользователь берётся из заголовков запроса;
    # keycloak - проверка Bearer-токена по JWKS реалма.
    auth_backend: Literal["dev", "keycloak"] = "dev"
    # Адрес, по которому Keycloak виден браузеру: именно он попадает в токен
    # полем iss, и по нему же проверяется издатель.
    keycloak_base_url: str = "http://localhost:8080"
    # Адрес изнутри сети контейнеров - по нему API забирает ключи реалма.
    # Пусто - берётся keycloak_base_url.
    keycloak_internal_url: str = ""
    keycloak_realm: str = "edu-crm"
    keycloak_audience: str = "edu-crm-api"
    # Публичный клиент, через который входит браузер (Authorization Code + PKCE).
    keycloak_web_client_id: str = "edu-crm-web"
    keycloak_jwks_ttl_seconds: int = 600
    # Управление пользователями и ролями идёт через Admin REST API Keycloak
    # с токеном самого администратора CRM: роль admin в реалме включает права
    # realm-management на пользователей. Отдельных секретов не требуется.
    keycloak_admin_timeout_seconds: float = 10.0

    # Пользователь, который подставляется dev-заглушкой, если заголовки не переданы.
    dev_user_subject: str = "00000000-0000-0000-0000-0000000000de"
    dev_user_username: str = "dev"
    dev_user_full_name: str = "Разработчик"
    dev_user_email: str = "dev@example.com"
    dev_user_roles: str = "manager,head,admin"

    # --- Интеграции ---
    # Контракты LMS и сайта организаторы предоставляют в ходе работы. Пока
    # базовый адрес пуст, адаптер отвечает тестовыми данными из fixtures,
    # а при появлении реального API достаточно задать переменные окружения.
    lms_base_url: str = ""
    lms_token: str = ""
    site_base_url: str = ""
    site_token: str = ""
    integration_timeout_seconds: float = 15.0

    # --- Файлы ---
    storage_dir: Path = Path("storage")
    max_upload_mb: int = 25

    # --- Контроль проблемных процессов (раздел 7 концепции) ---
    # Сколько дней без движения по этапу считать задержкой, если у этапа
    # не задан свой sla_days.
    alert_default_sla_days: int = 14
    # За сколько дней до конца срока договора или лицензии поднимать тревогу.
    alert_expiring_days: int = 60

    # --- Кэш тяжёлых выборок (требование 13 ТЗ) ---
    # Сколько секунд живёт запись. 0 - кэш выключен.
    cache_ttl_seconds: int = 60

    # --- Прочее ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

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
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

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
        """Ключи реалма берём по внутреннему адресу, издателя проверяем по внешнему.

        В Docker это разные адреса: браузер ходит на localhost, а API -
        на имя контейнера. Если их не разделить, токен не пройдёт проверку
        издателя либо API не достучится до Keycloak.
        """
        base = (self.keycloak_internal_url or self.keycloak_base_url).rstrip("/")
        return f"{base}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
