"""Сборка маршрутов API версии 1."""

from fastapi import APIRouter

from app.api.v1.endpoints import catalog, contracts, health, universities, users, workflow

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(universities.router)
api_router.include_router(catalog.router)
api_router.include_router(contracts.router)
api_router.include_router(workflow.contract_router)
api_router.include_router(workflow.router)
