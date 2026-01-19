"""
Pydantic schemas for Notifications API.
"""

from datetime import datetime
from uuid import UUID

from cbi.api.schemas.base import CamelCaseModel, IDMixin, PaginatedResponse
from cbi.db.models import UrgencyLevel


class NotificationResponse(IDMixin):
    """Full notification response."""

    report_id: UUID | None
    officer_id: UUID | None
    urgency: UrgencyLevel
    title: str
    body: str
    channels: list[str]
    sent_at: datetime
    read_at: datetime | None
    dismissed_at: datetime | None
    created_at: datetime


class NotificationListItem(IDMixin):
    """Abbreviated notification for list views."""

    report_id: UUID | None
    urgency: UrgencyLevel
    title: str
    sent_at: datetime
    read_at: datetime | None


class NotificationListResponse(PaginatedResponse[NotificationListItem]):
    """Paginated list of notifications."""

    pass


class NotificationMarkReadRequest(CamelCaseModel):
    """Request to mark notifications as read."""

    notification_ids: list[UUID]


class NotificationMarkReadResponse(CamelCaseModel):
    """Response for marking notifications as read."""

    marked_count: int


class UnreadCountResponse(CamelCaseModel):
    """Unread notification count response."""

    unread_count: int
    critical_count: int
