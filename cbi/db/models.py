"""
SQLAlchemy 2.0 async models for CBI database.

Uses mapped_column syntax with full type hints.
GeoAlchemy2 for PostGIS Geography types.
"""

from datetime import date, datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING
from uuid import UUID

from geoalchemy2 import Geography
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PG_UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Enum Types
# =============================================================================


class ReportStatus(str, PyEnum):
    """Report status workflow."""

    open = "open"
    investigating = "investigating"
    resolved = "resolved"
    false_alarm = "false_alarm"


class UrgencyLevel(str, PyEnum):
    """Urgency levels for triage."""

    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class AlertType(str, PyEnum):
    """Alert classification types."""

    suspected_outbreak = "suspected_outbreak"
    cluster = "cluster"
    single_case = "single_case"
    rumor = "rumor"


class DiseaseType(str, PyEnum):
    """Suspected disease types."""

    cholera = "cholera"
    dengue = "dengue"
    malaria = "malaria"
    measles = "measles"
    meningitis = "meningitis"
    unknown = "unknown"


class ReporterRelation(str, PyEnum):
    """Reporter relationship to cases."""

    self_ = "self"
    family = "family"
    neighbor = "neighbor"
    health_worker = "health_worker"
    community_leader = "community_leader"
    other = "other"


class LinkType(str, PyEnum):
    """Link types for case clustering."""

    geographic = "geographic"
    temporal = "temporal"
    symptom = "symptom"
    manual = "manual"


# =============================================================================
# Base Model
# =============================================================================


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


# =============================================================================
# Models
# =============================================================================


class Reporter(Base):
    """Community members who submit reports (minimal PII)."""

    __tablename__ = "reporters"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    phone_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    phone_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(5), default="ar")
    total_reports: Mapped[int] = mapped_column(Integer, default=0)
    first_report_at: Mapped[datetime | None] = mapped_column(default=None)
    last_report_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    reports: Mapped[list["Report"]] = relationship(
        "Report",
        back_populates="reporter",
        lazy="selectin",
    )
    conversation_states: Mapped[list["ConversationState"]] = relationship(
        "ConversationState",
        back_populates="reporter",
        lazy="selectin",
    )


class Officer(Base):
    """Health officers who receive and act on reports."""

    __tablename__ = "officers"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    region: Mapped[str | None] = mapped_column(String(100), default=None)
    role: Mapped[str] = mapped_column(String(50), default="officer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    assigned_reports: Mapped[list["Report"]] = relationship(
        "Report",
        back_populates="officer",
        lazy="selectin",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification",
        back_populates="officer",
        lazy="selectin",
    )


class Report(Base):
    """Health incident reports from community."""

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "data_completeness >= 0 AND data_completeness <= 1",
            name="valid_completeness",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="valid_confidence",
        ),
        CheckConstraint(
            "cases_count >= 0 AND deaths_count >= 0",
            name="valid_counts",
        ),
        Index("idx_reports_location", "location_point", postgresql_using="gist"),
        Index(
            "idx_reports_open_urgent",
            "urgency",
            "created_at",
            postgresql_where="status = 'open'",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    reporter_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reporters.id", ondelete="SET NULL"),
        default=None,
    )
    officer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("officers.id", ondelete="SET NULL"),
        default=None,
    )
    conversation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status", create_type=False),
        default=ReportStatus.open,
    )

    # MVS Data
    symptoms: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    suspected_disease: Mapped[DiseaseType] = mapped_column(
        Enum(DiseaseType, name="disease_type", create_type=False),
        default=DiseaseType.unknown,
    )
    reporter_relation: Mapped[ReporterRelation | None] = mapped_column(
        Enum(
            ReporterRelation,
            name="reporter_rel",
            create_type=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        default=None,
    )
    location_text: Mapped[str | None] = mapped_column(Text, default=None)
    location_normalized: Mapped[str | None] = mapped_column(String(200), default=None)
    location_point = mapped_column(Geography(geometry_type="POINT", srid=4326))
    onset_text: Mapped[str | None] = mapped_column(Text, default=None)
    onset_date: Mapped[date | None] = mapped_column(Date, default=None)
    cases_count: Mapped[int] = mapped_column(Integer, default=1)
    deaths_count: Mapped[int] = mapped_column(Integer, default=0)
    affected_groups: Mapped[str | None] = mapped_column(Text, default=None)

    # Classification
    urgency: Mapped[UrgencyLevel] = mapped_column(
        Enum(UrgencyLevel, name="urgency_level", create_type=False),
        default=UrgencyLevel.medium,
    )
    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, name="alert_type", create_type=False),
        default=AlertType.single_case,
    )
    data_completeness: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float | None] = mapped_column(Float, default=None)

    # Raw data
    raw_conversation: Mapped[dict] = mapped_column(JSONB, default=list)
    extracted_entities: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Officer annotations
    investigation_notes: Mapped[list] = mapped_column(JSONB, default=list)
    outcome: Mapped[str | None] = mapped_column(Text, default=None)

    # Metadata
    source: Mapped[str] = mapped_column(String(20), default="telegram")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)

    # Relationships
    reporter: Mapped["Reporter | None"] = relationship(
        "Reporter",
        back_populates="reports",
    )
    officer: Mapped["Officer | None"] = relationship(
        "Officer",
        back_populates="assigned_reports",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification",
        back_populates="report",
        lazy="selectin",
    )
    links_as_source: Mapped[list["ReportLink"]] = relationship(
        "ReportLink",
        foreign_keys="ReportLink.report_id_1",
        back_populates="report_1",
        lazy="selectin",
    )
    links_as_target: Mapped[list["ReportLink"]] = relationship(
        "ReportLink",
        foreign_keys="ReportLink.report_id_2",
        back_populates="report_2",
        lazy="selectin",
    )


class ReportLink(Base):
    """Connections between related cases for outbreak detection."""

    __tablename__ = "report_links"
    __table_args__ = (
        CheckConstraint("report_id_1 != report_id_2", name="different_reports"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="valid_link_confidence",
        ),
        UniqueConstraint("report_id_1", "report_id_2", "link_type", name="unique_link"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    report_id_1: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_id_2: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    link_type: Mapped[LinkType] = mapped_column(
        Enum(LinkType, name="link_type", create_type=False),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_by: Mapped[str] = mapped_column(String(50), default="surveillance_agent")

    # Relationships
    report_1: Mapped["Report"] = relationship(
        "Report",
        foreign_keys=[report_id_1],
        back_populates="links_as_source",
    )
    report_2: Mapped["Report"] = relationship(
        "Report",
        foreign_keys=[report_id_2],
        back_populates="links_as_target",
    )


class Notification(Base):
    """Alerts sent to health officers."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "idx_notifications_unread",
            "officer_id",
            "sent_at",
            postgresql_where="read_at IS NULL",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    report_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        default=None,
    )
    officer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("officers.id", ondelete="CASCADE"),
        default=None,
    )
    urgency: Mapped[UrgencyLevel] = mapped_column(
        Enum(UrgencyLevel, name="urgency_level", create_type=False),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), default=["dashboard"])
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    sent_at: Mapped[datetime] = mapped_column(server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(default=None)
    dismissed_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    report: Mapped["Report | None"] = relationship(
        "Report",
        back_populates="notifications",
    )
    officer: Mapped["Officer | None"] = relationship(
        "Officer",
        back_populates="notifications",
    )


class AuditLog(Base):
    """Track important system events."""

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(100), default=None)
    changes: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip_address = mapped_column(INET, default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ConversationState(Base):
    """Redis backup for conversation state."""

    __tablename__ = "conversation_states"

    conversation_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    reporter_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reporters.id", ondelete="SET NULL"),
        default=None,
    )
    state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    mode: Mapped[str] = mapped_column(String(20), default="listening")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    reporter: Mapped["Reporter | None"] = relationship(
        "Reporter",
        back_populates="conversation_states",
    )
