"""Сборка маршрутов API версии 1."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit,
    catalog,
    content,
    contracts,
    dashboard,
    health,
    imports,
    integrations,
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
api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(dashboard.router)
api_router.include_router(universities.router)
api_router.include_router(catalog.router)
api_router.include_router(contracts.router)
api_router.include_router(workflow.contract_router)
api_router.include_router(workflow.router)
# Редактор шаблонов идёт после чтения: у него тот же префикс, но свои права.
api_router.include_router(workflow_admin.router)
api_router.include_router(workflow_admin.presentation_router)
api_router.include_router(content.router)
api_router.include_router(content.files_router)
api_router.include_router(licenses.contract_router)
api_router.include_router(licenses.router)
api_router.include_router(reports.router)
api_router.include_router(statistics.router)
api_router.include_router(integrations.router)
api_router.include_router(imports.router)
api_router.include_router(audit.router)
api_router.include_router(settings.router)
