"""Базовые схемы, общие для всех разделов API."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Страница списка с общим числом записей."""

    items: list[T]
    total: int
    limit: int
    offset: int
