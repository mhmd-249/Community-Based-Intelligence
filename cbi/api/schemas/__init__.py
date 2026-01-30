"""CBI API schemas."""

from cbi.api.schemas.auth import (
    LoginRequest,
    LoginResponse,
    OfficerResponse,
    OfficerUpdateRequest,
    PasswordChangeRequest,
    RefreshRequest,
    TokenResponse,
)
from cbi.api.schemas.base import (
    CamelCaseModel,
    IDMixin,
    LocationPoint,
    MessageResponse,
    PaginatedResponse,
    TimestampMixin,
)
from cbi.api.schemas.notifications import (
    NotificationListItem,
    NotificationListResponse,
    NotificationMarkReadRequest,
    NotificationMarkReadResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from cbi.api.schemas.reports import (
    InvestigationNote,
    LinkedReportItem,
    NotificationSummary,
    OfficerSummary,
    ReportCreate,
    ReportDetailResponse,
    ReporterSummary,
    ReportListItem,
    ReportListResponse,
    ReportNoteCreate,
    ReportResponse,
    ReportStatsResponse,
    ReportUpdate,
    TimelineEvent,
)

__all__ = [
    # Base
    "CamelCaseModel",
    "IDMixin",
    "TimestampMixin",
    "PaginatedResponse",
    "MessageResponse",
    "LocationPoint",
    # Auth
    "LoginRequest",
    "LoginResponse",
    "TokenResponse",
    "RefreshRequest",
    "OfficerResponse",
    "OfficerUpdateRequest",
    "PasswordChangeRequest",
    # Reports
    "ReportCreate",
    "ReportUpdate",
    "ReportNoteCreate",
    "ReportResponse",
    "ReportDetailResponse",
    "ReportListItem",
    "ReportListResponse",
    "ReportStatsResponse",
    "ReporterSummary",
    "OfficerSummary",
    "InvestigationNote",
    "NotificationSummary",
    "LinkedReportItem",
    "TimelineEvent",
    # Notifications
    "NotificationResponse",
    "NotificationListItem",
    "NotificationListResponse",
    "NotificationMarkReadRequest",
    "NotificationMarkReadResponse",
    "UnreadCountResponse",
]
