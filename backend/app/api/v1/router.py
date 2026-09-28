"""Сборка маршрутов API версии 1."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1.endpoints import (
    audit,
    catalog,
    content,
    contract_templates,
    dashboard,
    health,
    imports,
    integrations,
    interactions,
    licenses,
    reports,
    settings,
    statistics,
    universities,
    users,
    workflow,
    workflow_admin,
)

api_router = APIRouter()
# Проверка живости и настройки входа открыты без авторизации.
api_router.include_router(health.router)

# Остальное только для пользователей системы. Запись пользователя берётся
# в каждом запросе: изменения попадают в журнал от имени автора, а отключённая
# учётная запись ничего не сделает.
authenticated = APIRouter(dependencies=[Depends(get_current_user)])
authenticated.include_router(users.router)
authenticated.include_router(dashboard.router)
authenticated.include_router(universities.router)
authenticated.include_router(catalog.router)
authenticated.include_router(interactions.router)
authenticated.include_router(workflow.router)
# Редактор шаблонов идёт после чтения: у него тот же префикс, но свои права.
authenticated.include_router(workflow_admin.router)
authenticated.include_router(workflow_admin.presentation_router)
authenticated.include_router(content.router)
authenticated.include_router(content.files_router)
authenticated.include_router(licenses.router)
authenticated.include_router(contract_templates.router)
authenticated.include_router(contract_templates.documents_router)
authenticated.include_router(reports.router)
authenticated.include_router(statistics.router)
authenticated.include_router(integrations.router)
authenticated.include_router(imports.router)
authenticated.include_router(audit.router)
authenticated.include_router(settings.router)
api_router.include_router(authenticated)
