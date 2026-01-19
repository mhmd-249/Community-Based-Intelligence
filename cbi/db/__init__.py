"""CBI database module."""

from cbi.db.models import (
    AlertType,
    AuditLog,
    Base,
    ConversationState,
    DiseaseType,
    LinkType,
    Notification,
    Officer,
    Report,
    ReportLink,
    Reporter,
    ReporterRelation,
    ReportStatus,
    UrgencyLevel,
)
from cbi.db.session import (
    close_db,
    execute_raw,
    get_session,
    get_session_dependency,
    health_check,
    init_db,
)

__all__ = [
    # Base
    "Base",
    # Models
    "Reporter",
    "Officer",
    "Report",
    "ReportLink",
    "Notification",
    "AuditLog",
    "ConversationState",
    # Enums
    "ReportStatus",
    "UrgencyLevel",
    "AlertType",
    "DiseaseType",
    "ReporterRelation",
    "LinkType",
    # Session
    "init_db",
    "close_db",
    "get_session",
    "get_session_dependency",
    "execute_raw",
    "health_check",
]
