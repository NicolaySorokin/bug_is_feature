"""Точка входа FastAPI-приложения."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.openapi import COMMON_ERRORS
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.security import build_auth_backend
from app.db.session import engine
from app.services import audit  # noqa: F401 - импорт включает запись журнала изменений
from app.services.integrations import scheduler

DESCRIPTION = """
API системы контроля взаимодействия ИТ Школы Ростелекома с вузами.

{auth}

**Права на данные.** Менеджер видит договоры, где он ответственный или
закреплён за вузом. Руководитель и администратор видят все договоры.

**Ошибки.** Любой отказ возвращает тело вида
`{"code": "not_found", "message": "...", "details": null}`; `code`
машиночитаем и не меняется вместе с текстом сообщения.
"""

# Описание входа зависит от схемы: про заглушку разработки на боевом стенде
# рассказывать незачем.
AUTH_DESCRIPTION = {
    "keycloak": (
        "**Авторизация.** Bearer-токен Keycloak (реалм `{realm}`): вход в систему "
        "через веб-интерфейс, токен передаётся в заголовке `Authorization`."
    ),
    "dev": (
        "**Авторизация.** Режим разработки: вместо Keycloak заглушка, пользователь "
        "задаётся заголовками `X-Dev-User` и `X-Dev-Roles` (роли через запятую: "
        "`manager`, `head`, `admin`)."
    ),
}

TAGS = [
    {"name": "service", "description": "Проверка живости и служебные словари."},
    {
        "name": "users",
        "description": (
            "Текущий пользователь, сотрудники, их роли в Keycloak и доступ к данным."
        ),
    },
    {
        "name": "universities",
        "description": "Вузы, их контактные лица, подтверждение, архив и объединение дублей.",
    },
    {"name": "catalog", "description": "Справочники направлений, программ и продуктов."},
    {
        "name": "interactions",
        "description": (
            "Взаимодействия с вузами - центральная сущность: процесс, программы "
            "и продукты, договор, контакты, лицензии."
        ),
    },
    {"name": "workflow", "description": "Шаблоны процессов и их версии для чтения."},
    {
        "name": "workflow admin",
        "description": "Шаблоны процессов: черновики версий, этапы, переходы, публикация.",
    },
    {
        "name": "comments & files",
        "description": "Комментарии и вложения по взаимодействию, типы документов этапа.",
    },
    {"name": "licenses", "description": "Реестр лицензий на продукты по договорам."},
    {"name": "reports", "description": "Отчёты, выгрузки XLS, XLSX, PDF и JSON, диаграммы."},
    {
        "name": "statistics",
        "description": (
            "Статистика обучения: заявки с сайта, обучающиеся из LMS и потоки "
            "по ИТ-программам - рейтинг востребованности."
        ),
    },
    {"name": "dashboard", "description": "Сводка на главной и проблемные процессы."},
    {
        "name": "integrations",
        "description": "Обмен с LMS и сайтом ИТ Школы, ошибки по записям, сопоставление.",
    },
    {"name": "imports", "description": "Загрузка каталогов из XLS и XLSX."},
    {"name": "audit", "description": "Журнал изменений предметных данных."},
    {"name": "settings", "description": "Системные настройки: нормы контроля процессов."},
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Схема аутентификации выбирается один раз на старте и лежит в state,
    # чтобы её можно было подменить в тестах.
    app.state.auth_backend = build_auth_backend(settings)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    # Обмен с LMS и сайтом по расписанию; интервал - в «Настройках», по
    # умолчанию выключен.
    async with scheduler.running():
        yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    # replace, а не format: в тексте есть фигурные скобки примера JSON.
    description=DESCRIPTION.replace(
        "{auth}",
        AUTH_DESCRIPTION[settings.auth_backend].replace("{realm}", settings.keycloak_realm),
    ),
    version="1.0.0",
    openapi_tags=TAGS,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Описание отказов общее для всех методов: см. app/api/openapi.py.
app.include_router(api_router, prefix=settings.api_v1_prefix, responses=COMMON_ERRORS)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs"}
