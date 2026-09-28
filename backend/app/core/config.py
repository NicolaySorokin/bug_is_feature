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

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "edu_crm"
    postgres_password: str = "edu_crm"
    postgres_db: str = "edu_crm"
    # Печатать все SQL-запросы в лог, для отладки.
    db_echo: bool = False
    # Пул соединений на один процесс API. Сумма по всем процессам должна
    # укладываться в max_connections PostgreSQL.
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Авторизация: dev берёт пользователя из
    # заголовков, keycloak проверяет Bearer-токен.
    auth_backend: Literal["dev", "keycloak"] = "dev"
    # Адрес Keycloak для браузера, он же издатель токена (iss).
    keycloak_base_url: str = "http://localhost:8080"
    # Адрес Keycloak внутри сети контейнеров, по нему API берёт ключи.
    # Если пусто, берётся keycloak_base_url.
    keycloak_internal_url: str = ""
    keycloak_realm: str = "edu-crm"
    keycloak_audience: str = "edu-crm-api"
    # Публичный клиент, через который входит браузер (Authorization Code + PKCE).
    keycloak_web_client_id: str = "edu-crm-web"
    keycloak_jwks_ttl_seconds: int = 600
    # Пользователями управляем через Admin API Keycloak токеном самого
    # администратора, отдельные секреты не нужны.
    keycloak_admin_timeout_seconds: float = 10.0

    # Пользователь, который подставляется dev-заглушкой, если заголовки не переданы.
    dev_user_subject: str = "00000000-0000-0000-0000-0000000000de"
    dev_user_username: str = "dev"
    dev_user_full_name: str = "Разработчик"
    dev_user_email: str = "dev@example.com"
    dev_user_roles: str = "manager,head,admin"

    # Интеграции. Пока адрес пуст, адаптер отвечает тестовыми данными из fixtures.
    lms_base_url: str = ""
    lms_token: str = ""
    site_base_url: str = ""
    site_token: str = ""
    integration_timeout_seconds: float = 15.0
    # Обмен по расписанию раз в N часов, 0 значит только вручную.
    # Администратор меняет значение в «Настройках».
    integration_sync_interval_hours: int = 0

    # Файлы
    storage_dir: Path = Path("storage")
    max_upload_mb: int = 25

    # Контроль проблемных процессов. Норма этапа в
    # днях, если у этапа нет своего sla_days.
    alert_default_sla_days: int = 14
    # За сколько дней до конца срока договора или лицензии поднимать тревогу.
    alert_expiring_days: int = 60

    # Сколько выгрузок один процесс API собирает одновременно, остальные ждут
    # в очереди. Так отчёты не тормозят интерфейс.
    export_concurrency: int = 1

    # Кэш выборок: срок жизни записи в секундах, 0 выключает кэш.
    cache_ttl_seconds: int = 60

    # Прочее
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
        """Ключи берём по внутреннему адресу, издателя проверяем по внешнему:
        в Docker браузер и API видят Keycloak по разным адресам.
        """
        base = (self.keycloak_internal_url or self.keycloak_base_url).rstrip("/")
        return f"{base}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
