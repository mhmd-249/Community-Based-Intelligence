"""
Database queries for CBI.

Common query patterns for reports, reporters, officers, and notifications.
All queries use async SQLAlchemy patterns.
"""

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, cast, desc, func, or_, select
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, array as pg_array
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cbi.db.models import (
    AlertType,
    AuditLog,
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


# =============================================================================
# Reporter Queries
# =============================================================================


async def get_reporter_by_phone_hash(
    session: AsyncSession,
    phone_hash: str,
) -> Reporter | None:
    """Find a reporter by their phone hash."""
    result = await session.execute(
        select(Reporter).where(Reporter.phone_hash == phone_hash)
    )
    return result.scalar_one_or_none()


async def create_reporter(
    session: AsyncSession,
    phone_hash: str,
    phone_encrypted: bytes,
    preferred_language: str = "ar",
) -> Reporter:
    """Create a new reporter."""
    reporter = Reporter(
        phone_hash=phone_hash,
        phone_encrypted=phone_encrypted,
        preferred_language=preferred_language,
    )
    session.add(reporter)
    await session.flush()
    return reporter


async def get_or_create_reporter(
    session: AsyncSession,
    phone_hash: str,
    phone_encrypted: bytes,
    preferred_language: str = "ar",
) -> tuple[Reporter, bool]:
    """Get existing reporter or create new one. Returns (reporter, created)."""
    reporter = await get_reporter_by_phone_hash(session, phone_hash)
    if reporter:
        return reporter, False
    reporter = await create_reporter(
        session, phone_hash, phone_encrypted, preferred_language
    )
    return reporter, True


# =============================================================================
# Report Queries
# =============================================================================


async def get_report_by_id(
    session: AsyncSession,
    report_id: UUID,
) -> Report | None:
    """Get a report by ID with eagerly loaded relationships."""
    result = await session.execute(
        select(Report)
        .where(Report.id == report_id)
        .options(selectinload(Report.reporter), selectinload(Report.officer))
    )
    return result.scalar_one_or_none()


async def get_report_by_conversation(
    session: AsyncSession,
    conversation_id: str,
) -> Report | None:
    """Get the most recent report for a conversation."""
    result = await session.execute(
        select(Report)
        .where(Report.conversation_id == conversation_id)
        .order_by(desc(Report.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_open_reports(
    session: AsyncSession,
    *,
    urgency: UrgencyLevel | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Report]:
    """Get open reports, optionally filtered by urgency."""
    query = select(Report).where(Report.status == ReportStatus.open)

    if urgency:
        query = query.where(Report.urgency == urgency)

    query = query.order_by(desc(Report.created_at)).limit(limit).offset(offset)

    result = await session.execute(query)
    return list(result.scalars().all())


async def get_reports_by_disease(
    session: AsyncSession,
    disease: DiseaseType,
    *,
    days: int = 7,
    limit: int = 100,
) -> list[Report]:
    """Get recent reports for a specific disease."""
    since = datetime.utcnow() - timedelta(days=days)
    result = await session.execute(
        select(Report)
        .where(
            and_(
                Report.suspected_disease == disease,
                Report.created_at >= since,
            )
        )
        .order_by(desc(Report.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def count_reports_by_disease(
    session: AsyncSession,
    disease: DiseaseType,
    *,
    days: int = 7,
) -> int:
    """Count reports for a disease within a time window."""
    since = datetime.utcnow() - timedelta(days=days)
    result = await session.execute(
        select(func.count(Report.id)).where(
            and_(
                Report.suspected_disease == disease,
                Report.created_at >= since,
            )
        )
    )
    return result.scalar_one()


async def get_reports_near_location(
    session: AsyncSession,
    latitude: float,
    longitude: float,
    radius_km: float = 10.0,
    *,
    days: int = 7,
    limit: int = 50,
) -> list[Report]:
    """Get reports within a radius of a location."""
    since = datetime.utcnow() - timedelta(days=days)
    point = f"SRID=4326;POINT({longitude} {latitude})"

    result = await session.execute(
        select(Report)
        .where(
            and_(
                Report.location_point.isnot(None),
                Report.created_at >= since,
                func.ST_DWithin(
                    Report.location_point,
                    func.ST_GeogFromText(point),
                    radius_km * 1000,  # Convert km to meters
                ),
            )
        )
        .order_by(desc(Report.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


# =============================================================================
# Officer Queries
# =============================================================================


async def get_officer_by_email(
    session: AsyncSession,
    email: str,
) -> Officer | None:
    """Get an officer by email."""
    result = await session.execute(
        select(Officer).where(Officer.email == email.lower())
    )
    return result.scalar_one_or_none()


async def get_officer_by_id(
    session: AsyncSession,
    officer_id: UUID,
) -> Officer | None:
    """Get an officer by ID."""
    result = await session.execute(select(Officer).where(Officer.id == officer_id))
    return result.scalar_one_or_none()


async def get_officers_by_region(
    session: AsyncSession,
    region: str,
) -> list[Officer]:
    """Get all active officers in a region."""
    result = await session.execute(
        select(Officer).where(
            and_(
                Officer.region == region,
                Officer.is_active.is_(True),
            )
        )
    )
    return list(result.scalars().all())


# =============================================================================
# Notification Queries
# =============================================================================


async def get_unread_notifications(
    session: AsyncSession,
    officer_id: UUID,
    *,
    limit: int = 50,
) -> list[Notification]:
    """Get unread notifications for an officer."""
    result = await session.execute(
        select(Notification)
        .where(
            and_(
                Notification.officer_id == officer_id,
                Notification.read_at.is_(None),
            )
        )
        .order_by(desc(Notification.sent_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_notification_read(
    session: AsyncSession,
    notification_id: UUID,
) -> bool:
    """Mark a notification as read. Returns True if updated."""
    result = await session.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notification = result.scalar_one_or_none()
    if notification and notification.read_at is None:
        notification.read_at = datetime.utcnow()
        await session.flush()
        return True
    return False


async def create_notification(
    session: AsyncSession,
    *,
    report_id: UUID | None = None,
    officer_id: UUID | None = None,
    urgency: UrgencyLevel,
    title: str,
    body: str,
    channels: list[str] | None = None,
    metadata: dict | None = None,
) -> UUID:
    """
    Create a notification for a health officer.

    Args:
        session: Async database session
        report_id: Associated report ID (optional)
        officer_id: Target officer ID (optional, None = all officers)
        urgency: Urgency level
        title: Notification title
        body: Notification body text
        channels: Delivery channels (default: ["dashboard"])
        metadata: Additional metadata

    Returns:
        UUID of the created notification
    """
    notification = Notification(
        report_id=report_id,
        officer_id=officer_id,
        urgency=urgency,
        title=title,
        body=body,
        channels=channels or ["dashboard"],
        metadata_=metadata or {},
    )
    session.add(notification)
    await session.flush()
    return notification.id


async def create_notifications_for_all_officers(
    session: AsyncSession,
    *,
    report_id: UUID | None = None,
    urgency: UrgencyLevel,
    title: str,
    body: str,
    metadata: dict | None = None,
) -> list[UUID]:
    """
    Create notifications for all active officers.

    Args:
        session: Async database session
        report_id: Associated report ID
        urgency: Urgency level
        title: Notification title
        body: Notification body text
        metadata: Additional metadata

    Returns:
        List of created notification UUIDs
    """
    result = await session.execute(
        select(Officer).where(Officer.is_active.is_(True))
    )
    officers = list(result.scalars().all())

    notification_ids = []
    for officer in officers:
        notification = Notification(
            report_id=report_id,
            officer_id=officer.id,
            urgency=urgency,
            title=title,
            body=body,
            channels=["dashboard"],
            metadata_=metadata or {},
        )
        session.add(notification)
        await session.flush()
        notification_ids.append(notification.id)

    return notification_ids


# =============================================================================
# Report Link Queries
# =============================================================================


async def get_linked_reports(
    session: AsyncSession,
    report_id: UUID,
) -> list[dict]:
    """
    Get all reports linked to a given report.

    Returns dicts that include link metadata (link_type, confidence)
    alongside report data.

    Args:
        session: Async database session
        report_id: Report ID to find links for

    Returns:
        List of dicts with: id, symptoms, suspected_disease, cases_count,
        created_at, location_text, link_type, confidence
    """
    # Get links where this report is either source or target
    result = await session.execute(
        select(ReportLink).where(
            (ReportLink.report_id_1 == report_id)
            | (ReportLink.report_id_2 == report_id)
        )
    )
    links = list(result.scalars().all())

    if not links:
        return []

    # Build a map of linked_id -> link metadata
    link_map: dict[UUID, dict] = {}
    for link in links:
        linked_id = (
            link.report_id_2
            if link.report_id_1 == report_id
            else link.report_id_1
        )
        link_map[linked_id] = {
            "link_type": (
                link.link_type.value
                if hasattr(link.link_type, "value")
                else link.link_type
            ),
            "confidence": link.confidence,
        }

    # Fetch the linked reports
    result = await session.execute(
        select(Report).where(Report.id.in_(link_map.keys()))
    )
    reports = list(result.scalars().all())

    linked: list[dict] = []
    for report in reports:
        meta = link_map.get(report.id, {})
        linked.append({
            "id": report.id,
            "symptoms": report.symptoms or [],
            "suspected_disease": (
                report.suspected_disease.value
                if hasattr(report.suspected_disease, "value")
                else report.suspected_disease
            ),
            "cases_count": report.cases_count,
            "created_at": report.created_at,
            "location_text": report.location_text,
            "link_type": meta.get("link_type"),
            "confidence": meta.get("confidence"),
        })

    return linked


# =============================================================================
# Statistics Queries
# =============================================================================


async def get_report_stats(
    session: AsyncSession,
    *,
    days: int = 7,
) -> dict[str, int]:
    """Get report statistics for dashboard."""
    since = datetime.utcnow() - timedelta(days=days)

    # Total reports in window
    total_result = await session.execute(
        select(func.count(Report.id)).where(Report.created_at >= since)
    )
    total = total_result.scalar_one()

    # Open reports
    open_result = await session.execute(
        select(func.count(Report.id)).where(
            and_(
                Report.status == ReportStatus.open,
                Report.created_at >= since,
            )
        )
    )
    open_count = open_result.scalar_one()

    # Critical reports
    critical_result = await session.execute(
        select(func.count(Report.id)).where(
            and_(
                Report.urgency == UrgencyLevel.critical,
                Report.created_at >= since,
            )
        )
    )
    critical = critical_result.scalar_one()

    return {
        "total": total,
        "open": open_count,
        "critical": critical,
        "resolved": total - open_count,
    }


# =============================================================================
# Surveillance Agent Queries
# =============================================================================


async def find_related_cases(
    session: AsyncSession,
    location: str | None = None,
    location_coords: tuple[float, float] | None = None,
    symptoms: list[str] | None = None,
    window_days: int = 7,
    radius_km: float = 10.0,
    *,
    suspected_disease: DiseaseType | None = None,
    exclude_report_id: UUID | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Find related cases by geographic, temporal, and symptom proximity.

    Uses PostGIS ST_DWithin for geographic matching when coordinates are
    available, falls back to fuzzy text matching on location_normalized otherwise.

    Filters to only open/investigating reports within the time window.
    Calculates a symptom overlap score for each result.

    Args:
        session: Async database session
        location: Location text for fuzzy matching
        location_coords: (latitude, longitude) tuple for geographic proximity
        symptoms: List of symptoms for overlap matching
        window_days: Time window in days
        radius_km: Search radius in kilometers
        suspected_disease: Filter by disease type (None matches all)
        exclude_report_id: Report ID to exclude (the current report)
        limit: Maximum results to return

    Returns:
        List of dicts with: id, symptoms, suspected_disease, cases_count,
        created_at, symptom_overlap_score, location_text
    """
    since = datetime.utcnow() - timedelta(days=window_days)
    conditions = [
        Report.created_at >= since,
        Report.status.in_([ReportStatus.open, ReportStatus.investigating]),
    ]

    if exclude_report_id is not None:
        conditions.append(Report.id != exclude_report_id)

    if suspected_disease is not None and suspected_disease != DiseaseType.unknown:
        conditions.append(Report.suspected_disease == suspected_disease)

    # Geographic filtering
    if location_coords is not None:
        lat, lon = location_coords
        point = f"SRID=4326;POINT({lon} {lat})"
        conditions.append(Report.location_point.isnot(None))
        conditions.append(
            func.ST_DWithin(
                Report.location_point,
                func.ST_GeogFromText(point),
                radius_km * 1000,
            )
        )
    elif location:
        conditions.append(
            or_(
                Report.location_normalized.ilike(f"%{location}%"),
                Report.location_text.ilike(f"%{location}%"),
            )
        )

    # Symptom overlap filtering (at least one shared symptom via && operator)
    if symptoms:
        from sqlalchemy import Text
        conditions.append(
            Report.symptoms.op("&&")(cast(pg_array(symptoms), PG_ARRAY(Text)))
        )

    result = await session.execute(
        select(Report)
        .where(and_(*conditions))
        .order_by(desc(Report.created_at))
        .limit(limit)
    )
    reports = list(result.scalars().all())

    # Calculate symptom overlap score for each result
    query_symptoms = set(symptoms) if symptoms else set()
    related: list[dict] = []
    for report in reports:
        report_symptoms = set(report.symptoms) if report.symptoms else set()
        if query_symptoms and report_symptoms:
            union = query_symptoms | report_symptoms
            overlap = query_symptoms & report_symptoms
            overlap_score = len(overlap) / len(union) if union else 0.0
        else:
            overlap_score = 0.0

        related.append({
            "id": report.id,
            "symptoms": report.symptoms or [],
            "suspected_disease": (
                report.suspected_disease.value
                if hasattr(report.suspected_disease, "value")
                else report.suspected_disease
            ),
            "cases_count": report.cases_count,
            "created_at": report.created_at,
            "symptom_overlap_score": round(overlap_score, 2),
            "location_text": report.location_text,
        })

    return related


async def get_case_count_for_area(
    session: AsyncSession,
    *,
    disease: DiseaseType,
    location_text: str | None = None,
    location_lat: float | None = None,
    location_lon: float | None = None,
    radius_km: float = 25.0,
    days: int = 7,
) -> int:
    """
    Count cases of a disease within a geographic area and time window.

    Used for checking Ministry of Health thresholds.

    Args:
        session: Async database session
        disease: Disease type to count
        location_text: Location text for fuzzy matching
        location_lat: Latitude for geographic proximity
        location_lon: Longitude for geographic proximity
        radius_km: Search radius in kilometers
        days: Time window in days

    Returns:
        Number of matching cases
    """
    since = datetime.utcnow() - timedelta(days=days)
    conditions = [
        Report.suspected_disease == disease,
        Report.created_at >= since,
    ]

    if location_lat is not None and location_lon is not None:
        point = f"SRID=4326;POINT({location_lon} {location_lat})"
        conditions.append(Report.location_point.isnot(None))
        conditions.append(
            func.ST_DWithin(
                Report.location_point,
                func.ST_GeogFromText(point),
                radius_km * 1000,
            )
        )
    elif location_text:
        conditions.append(
            or_(
                Report.location_normalized.ilike(f"%{location_text}%"),
                Report.location_text.ilike(f"%{location_text}%"),
            )
        )

    result = await session.execute(
        select(func.count(Report.id)).where(and_(*conditions))
    )
    return result.scalar_one()


async def link_reports(
    session: AsyncSession,
    report_id_1: UUID,
    report_id_2: UUID,
    link_type: LinkType | str,
    confidence: float,
    *,
    metadata: dict | None = None,
    created_by: str = "surveillance_agent",
) -> ReportLink | None:
    """
    Create a link between two related reports.

    Normalizes UUID ordering to prevent reverse duplicates.
    Handles unique constraint violations gracefully.

    Args:
        session: Async database session
        report_id_1: First report ID
        report_id_2: Second report ID
        link_type: Type of link (geographic, temporal, symptom, manual).
                   Accepts LinkType enum or string value.
        confidence: Confidence score (0.0 to 1.0)
        metadata: Optional metadata dict
        created_by: Creator identifier

    Returns:
        Created ReportLink or None if duplicate or same IDs
    """
    if report_id_1 == report_id_2:
        return None

    # Convert string to LinkType enum if needed
    if isinstance(link_type, str):
        link_type = LinkType(link_type)

    # Normalize ordering to avoid reverse duplicates
    id_1, id_2 = (
        (report_id_1, report_id_2)
        if str(report_id_1) < str(report_id_2)
        else (report_id_2, report_id_1)
    )

    link = ReportLink(
        report_id_1=id_1,
        report_id_2=id_2,
        link_type=link_type,
        confidence=confidence,
        metadata_=metadata or {},
        created_by=created_by,
    )

    try:
        async with session.begin_nested():
            session.add(link)
            await session.flush()
        return link
    except IntegrityError:
        # Savepoint rollback only — does NOT roll back the outer transaction,
        # so previously flushed objects (e.g. the report) are preserved.
        return None


async def create_report(
    session: AsyncSession,
    *,
    conversation_id: str,
    reporter_id: UUID | None = None,
    symptoms: list[str] | None = None,
    suspected_disease: DiseaseType = DiseaseType.unknown,
    reporter_relation: ReporterRelation | None = None,
    location_text: str | None = None,
    location_normalized: str | None = None,
    location_point_wkt: str | None = None,
    onset_text: str | None = None,
    onset_date: date | None = None,
    cases_count: int = 1,
    deaths_count: int = 0,
    affected_groups: str | None = None,
    urgency: UrgencyLevel = UrgencyLevel.medium,
    alert_type: AlertType = AlertType.single_case,
    data_completeness: float = 0.0,
    confidence_score: float | None = None,
    raw_conversation: dict | list | None = None,
    extracted_entities: dict | None = None,
    source: str = "telegram",
) -> Report:
    """
    Create a new health report in the database.

    Args:
        session: Async database session
        conversation_id: Conversation identifier
        reporter_id: Optional reporter UUID
        symptoms: List of reported symptoms
        suspected_disease: Classified disease type
        reporter_relation: Reporter's relationship to cases
        location_text: Raw location description
        location_normalized: Standardized location name
        location_point_wkt: WKT string for PostGIS point (e.g. "SRID=4326;POINT(lon lat)")
        onset_text: Raw timing description
        onset_date: Parsed onset date
        cases_count: Number of cases reported
        deaths_count: Number of deaths reported
        affected_groups: Description of affected population
        urgency: Urgency level classification
        alert_type: Alert type classification
        data_completeness: Data completeness score (0.0-1.0)
        confidence_score: Classification confidence (0.0-1.0)
        raw_conversation: Full conversation history
        extracted_entities: Extracted data entities
        source: Source platform

    Returns:
        Created Report object with server-generated ID
    """
    location_point = None
    if location_point_wkt:
        location_point = func.ST_GeogFromText(location_point_wkt)

    report = Report(
        reporter_id=reporter_id,
        conversation_id=conversation_id,
        symptoms=symptoms or [],
        suspected_disease=suspected_disease,
        reporter_relation=reporter_relation,
        location_text=location_text,
        location_normalized=location_normalized,
        location_point=location_point,
        onset_text=onset_text,
        onset_date=onset_date,
        cases_count=cases_count,
        deaths_count=deaths_count,
        affected_groups=affected_groups,
        urgency=urgency,
        alert_type=alert_type,
        data_completeness=data_completeness,
        confidence_score=confidence_score,
        raw_conversation=raw_conversation or [],
        extracted_entities=extracted_entities or {},
        source=source,
    )
    session.add(report)
    await session.flush()
    return report


async def create_report_from_state(
    session: AsyncSession,
    state: dict,
) -> UUID:
    """
    Create a report from a ConversationState, handling reporter lookup/creation.

    Extracts all relevant fields from the conversation state, finds or creates
    the reporter record, and persists the report.

    Args:
        session: Async database session
        state: ConversationState dict with extracted_data, classification,
               messages, conversation_id, reporter_phone, platform, language

    Returns:
        UUID of the created report
    """
    import hashlib

    from cbi.config import get_settings

    conversation_id = state.get("conversation_id", "")
    extracted_data = state.get("extracted_data", {})
    classification = state.get("classification", {})
    messages = state.get("messages", [])
    platform = state.get("platform", "telegram")
    language = state.get("language", "ar")
    reporter_phone = state.get("reporter_phone", "")

    # Handle Pydantic models
    if hasattr(extracted_data, "model_dump"):
        extracted_data = extracted_data.model_dump()
    if hasattr(classification, "model_dump"):
        classification = classification.model_dump()

    # Get or create reporter by phone hash
    reporter_id = None
    if reporter_phone:
        settings = get_settings()
        salt = settings.phone_hash_salt.get_secret_value()
        phone_hash = hashlib.sha256(f"{salt}{reporter_phone}".encode()).hexdigest()
        phone_encrypted = reporter_phone.encode("utf-8")

        reporter, created = await get_or_create_reporter(
            session,
            phone_hash=phone_hash,
            phone_encrypted=phone_encrypted,
            preferred_language=language,
        )
        reporter_id = reporter.id

        # Update reporter stats
        reporter.total_reports = (reporter.total_reports or 0) + 1
        reporter.last_report_at = datetime.utcnow()
        if created:
            reporter.first_report_at = reporter.last_report_at
        await session.flush()

    # Build location WKT if coordinates available
    location_coords = extracted_data.get("location_coords")
    location_wkt = None
    if location_coords:
        lat, lon = location_coords
        location_wkt = f"SRID=4326;POINT({lon} {lat})"

    # Parse reporter relation
    reporter_relation = None
    relation_str = extracted_data.get("reporter_relationship")
    if relation_str:
        try:
            reporter_relation = ReporterRelation(relation_str)
        except ValueError:
            pass

    # Parse suspected disease
    disease_str = classification.get(
        "suspected_disease",
        extracted_data.get("suspected_disease", "unknown"),
    )
    try:
        suspected_disease = DiseaseType(disease_str)
    except ValueError:
        suspected_disease = DiseaseType.unknown

    # Parse urgency and alert type
    try:
        urgency = UrgencyLevel(classification.get("urgency", "medium"))
    except ValueError:
        urgency = UrgencyLevel.medium

    try:
        alert_type = AlertType(classification.get("alert_type", "single_case"))
    except ValueError:
        alert_type = AlertType.single_case

    # Parse onset date
    onset_date_val = extracted_data.get("onset_date")
    onset_date = None
    if isinstance(onset_date_val, date):
        onset_date = onset_date_val
    elif isinstance(onset_date_val, str):
        try:
            onset_date = date.fromisoformat(onset_date_val)
        except ValueError:
            pass

    # Ensure messages are JSON-serializable (datetime -> isoformat string)
    def _make_json_safe(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: _make_json_safe(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_make_json_safe(item) for item in obj]
        return obj

    safe_messages = _make_json_safe(messages)
    safe_extracted = _make_json_safe(extracted_data)

    report = await create_report(
        session,
        conversation_id=conversation_id,
        reporter_id=reporter_id,
        symptoms=extracted_data.get("symptoms", []),
        suspected_disease=suspected_disease,
        reporter_relation=reporter_relation,
        location_text=extracted_data.get("location_text"),
        location_normalized=extracted_data.get("location_normalized"),
        location_point_wkt=location_wkt,
        onset_text=extracted_data.get("onset_text"),
        onset_date=onset_date,
        cases_count=extracted_data.get("cases_count") or 1,
        deaths_count=extracted_data.get("deaths_count") or 0,
        affected_groups=extracted_data.get("affected_description"),
        urgency=urgency,
        alert_type=alert_type,
        data_completeness=classification.get("data_completeness", 0.0),
        confidence_score=classification.get("confidence"),
        raw_conversation=safe_messages,
        extracted_entities=safe_extracted,
        source=platform,
    )

    return report.id


# =============================================================================
# Dashboard Report Queries
# =============================================================================


async def list_reports_paginated(
    session: AsyncSession,
    *,
    status: ReportStatus | None = None,
    urgency: UrgencyLevel | None = None,
    disease: DiseaseType | None = None,
    region: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Report], int]:
    """
    List reports with filters and pagination.

    Returns a tuple of (reports, total_count) for building paginated responses.

    Args:
        session: Async database session.
        status: Filter by report status.
        urgency: Filter by urgency level.
        disease: Filter by suspected disease.
        region: Filter by location region (matches location_normalized).
        from_date: Include reports created on or after this date.
        to_date: Include reports created on or before this date.
        page: Page number (1-indexed).
        page_size: Number of results per page.

    Returns:
        Tuple of (list of Report objects, total matching count).
    """
    conditions: list = []

    if status is not None:
        conditions.append(Report.status == status)
    if urgency is not None:
        conditions.append(Report.urgency == urgency)
    if disease is not None:
        conditions.append(Report.suspected_disease == disease)
    if region is not None:
        conditions.append(Report.location_normalized.ilike(f"%{region}%"))
    if from_date is not None:
        conditions.append(Report.created_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date is not None:
        conditions.append(Report.created_at <= datetime.combine(to_date, datetime.max.time()))

    where_clause = and_(*conditions) if conditions else True

    # Count total
    count_result = await session.execute(
        select(func.count(Report.id)).where(where_clause)
    )
    total = count_result.scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    result = await session.execute(
        select(Report)
        .where(where_clause)
        .order_by(desc(Report.created_at))
        .limit(page_size)
        .offset(offset)
    )
    reports = list(result.scalars().all())

    return reports, total


async def get_detailed_report_stats(
    session: AsyncSession,
    *,
    days: int = 7,
) -> dict:
    """
    Get report statistics with breakdowns by disease and urgency.

    Args:
        session: Async database session.
        days: Time window in days.

    Returns:
        Dict with total, open, critical, resolved, by_disease, by_urgency.
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Base stats
    total_result = await session.execute(
        select(func.count(Report.id)).where(Report.created_at >= since)
    )
    total = total_result.scalar_one()

    open_result = await session.execute(
        select(func.count(Report.id)).where(
            and_(
                Report.status.in_([ReportStatus.open, ReportStatus.investigating]),
                Report.created_at >= since,
            )
        )
    )
    open_count = open_result.scalar_one()

    critical_result = await session.execute(
        select(func.count(Report.id)).where(
            and_(
                Report.urgency == UrgencyLevel.critical,
                Report.created_at >= since,
            )
        )
    )
    critical = critical_result.scalar_one()

    # By disease
    disease_result = await session.execute(
        select(Report.suspected_disease, func.count(Report.id))
        .where(Report.created_at >= since)
        .group_by(Report.suspected_disease)
    )
    by_disease = {
        row[0].value if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in disease_result.all()
    }

    # By urgency
    urgency_result = await session.execute(
        select(Report.urgency, func.count(Report.id))
        .where(Report.created_at >= since)
        .group_by(Report.urgency)
    )
    by_urgency = {
        row[0].value if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in urgency_result.all()
    }

    return {
        "total": total,
        "open": open_count,
        "critical": critical,
        "resolved": total - open_count,
        "by_disease": by_disease,
        "by_urgency": by_urgency,
    }


async def create_audit_log(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: UUID,
    action: str,
    actor_type: str = "officer",
    actor_id: str | None = None,
    changes: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """
    Create an audit log entry.

    Args:
        session: Async database session.
        entity_type: Type of entity (e.g. "report").
        entity_id: ID of the entity.
        action: Action performed (e.g. "status_change", "note_added").
        actor_type: Type of actor (e.g. "officer", "system").
        actor_id: ID of the actor.
        changes: Dict describing what changed.
        ip_address: Client IP address.

    Returns:
        Created AuditLog instance.
    """
    log = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        changes=changes or {},
    )
    session.add(log)
    await session.flush()
    return log


async def get_audit_logs_for_entity(
    session: AsyncSession,
    entity_type: str,
    entity_id: UUID,
) -> list[AuditLog]:
    """Get all audit log entries for an entity, ordered chronologically."""
    result = await session.execute(
        select(AuditLog)
        .where(
            and_(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
        )
        .order_by(AuditLog.created_at)
    )
    return list(result.scalars().all())


async def get_notifications_for_report(
    session: AsyncSession,
    report_id: UUID,
) -> list[Notification]:
    """Get all notifications associated with a report."""
    result = await session.execute(
        select(Notification)
        .where(Notification.report_id == report_id)
        .order_by(desc(Notification.sent_at))
    )
    return list(result.scalars().all())
