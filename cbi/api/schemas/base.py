"""
Base Pydantic schemas and utilities.
"""

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class CamelCaseModel(BaseModel):
    """Base model with camelCase serialization for API responses."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=lambda s: "".join(
            word.capitalize() if i else word for i, word in enumerate(s.split("_"))
        ),
    )


class PaginatedResponse(CamelCaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class MessageResponse(CamelCaseModel):
    """Simple message response."""

    message: str


class LocationPoint(CamelCaseModel):
    """Geographic point for location data."""

    latitude: float
    longitude: float


class TimestampMixin(CamelCaseModel):
    """Mixin for created_at and updated_at fields."""

    created_at: datetime
    updated_at: datetime | None = None


class IDMixin(CamelCaseModel):
    """Mixin for UUID id field."""

    id: UUID
