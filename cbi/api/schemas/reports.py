"""
Pydantic schemas for Reports API.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from cbi.api.schemas.base import (
    CamelCaseModel,
    IDMixin,
    LocationPoint,
    PaginatedResponse,
    TimestampMixin,
)
from cbi.db.models import (
    AlertType,
    DiseaseType,
    ReporterRelation,
    ReportStatus,
    UrgencyLevel,
)


class ReportCreate(CamelCaseModel):
    """Schema for creating a new report (usually from agent)."""

    conversation_id: str
    reporter_id: UUID | None = None
    symptoms: list[str] = Field(default_factory=list)
    suspected_disease: DiseaseType = DiseaseType.unknown
    reporter_relation: ReporterRelation | None = None
    location_text: str | None = None
    location_normalized: str | None = None
    location: LocationPoint | None = None
    onset_text: str | None = None
    onset_date: date | None = None
    cases_count: int = 1
    deaths_count: int = 0
    affected_groups: str | None = None
    urgency: UrgencyLevel = UrgencyLevel.medium
    alert_type: AlertType = AlertType.single_case
    source: str = "telegram"


class ReportUpdate(CamelCaseModel):
    """Schema for updating an existing report."""

    status: ReportStatus | None = None
    officer_id: UUID | None = None
    symptoms: list[str] | None = None
    suspected_disease: DiseaseType | None = None
    location_normalized: str | None = None
    location: LocationPoint | None = None
    onset_date: date | None = None
    cases_count: int | None = None
    deaths_count: int | None = None
    urgency: UrgencyLevel | None = None
    alert_type: AlertType | None = None
    data_completeness: float | None = None
    confidence_score: float | None = None


class ReportNoteCreate(CamelCaseModel):
    """Schema for adding a note to a report."""

    content: str = Field(..., min_length=1, max_length=2000)


class ReporterSummary(CamelCaseModel):
    """Summary of reporter information (minimal PII)."""

    id: UUID
    preferred_language: str
    total_reports: int


class OfficerSummary(CamelCaseModel):
    """Summary of officer information."""

    id: UUID
    name: str
    region: str | None


class ReportResponse(IDMixin, TimestampMixin):
    """Full report response with all fields."""

    conversation_id: str
    status: ReportStatus
    symptoms: list[str]
    suspected_disease: DiseaseType
    reporter_relation: ReporterRelation | None
    location_text: str | None
    location_normalized: str | None
    onset_text: str | None
    onset_date: date | None
    cases_count: int
    deaths_count: int
    affected_groups: str | None
    urgency: UrgencyLevel
    alert_type: AlertType
    data_completeness: float
    confidence_score: float | None
    source: str
    resolved_at: datetime | None

    # Related entities (optional)
    reporter: ReporterSummary | None = None
    officer: OfficerSummary | None = None


class ReportListItem(IDMixin):
    """Abbreviated report for list views."""

    conversation_id: str
    status: ReportStatus
    suspected_disease: DiseaseType
    location_normalized: str | None
    urgency: UrgencyLevel
    alert_type: AlertType
    cases_count: int
    deaths_count: int
    created_at: datetime


class ReportListResponse(PaginatedResponse[ReportListItem]):
    """Paginated list of reports."""

    pass


class ReportStatsResponse(CamelCaseModel):
    """Report statistics for dashboard."""

    total: int
    open: int
    critical: int
    resolved: int
    by_disease: dict[str, int] = Field(default_factory=dict)
    by_urgency: dict[str, int] = Field(default_factory=dict)
