"""
Database queries for CBI.

Common query patterns for reports, reporters, officers, and notifications.
All queries use async SQLAlchemy patterns.
"""

from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cbi.db.models import (
    AlertType,
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
    """Get a report by ID."""
    result = await session.execute(select(Report).where(Report.id == report_id))
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
    from geoalchemy2 import func as geo_func

    since = datetime.utcnow() - timedelta(days=days)
    point = f"SRID=4326;POINT({longitude} {latitude})"

    result = await session.execute(
        select(Report)
        .where(
            and_(
                Report.location_point.isnot(None),
                Report.created_at >= since,
                geo_func.ST_DWithin(
                    Report.location_point,
                    geo_func.ST_GeogFromText(point),
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


# =============================================================================
# Report Link Queries
# =============================================================================


async def get_linked_reports(
    session: AsyncSession,
    report_id: UUID,
) -> list[Report]:
    """Get all reports linked to a given report."""
    # Get links where this report is either source or target
    result = await session.execute(
        select(ReportLink).where(
            (ReportLink.report_id_1 == report_id)
            | (ReportLink.report_id_2 == report_id)
        )
    )
    links = result.scalars().all()

    # Collect all linked report IDs
    linked_ids = set()
    for link in links:
        if link.report_id_1 != report_id:
            linked_ids.add(link.report_id_1)
        if link.report_id_2 != report_id:
            linked_ids.add(link.report_id_2)

    if not linked_ids:
        return []

    # Fetch the linked reports
    result = await session.execute(select(Report).where(Report.id.in_(linked_ids)))
    return list(result.scalars().all())


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
    *,
    suspected_disease: DiseaseType | None = None,
    location_text: str | None = None,
    location_lat: float | None = None,
    location_lon: float | None = None,
    radius_km: float = 25.0,
    symptoms: list[str] | None = None,
    days: int = 14,
    exclude_report_id: UUID | None = None,
    limit: int = 50,
) -> list[Report]:
    """
    Find related cases by geographic, temporal, and symptom proximity.

    Uses PostGIS ST_DWithin for geographic matching when coordinates are
    available, falls back to text-based location matching otherwise.

    Args:
        session: Async database session
        suspected_disease: Filter by disease type (None matches all)
        location_text: Location text for fuzzy matching
        location_lat: Latitude for geographic proximity
        location_lon: Longitude for geographic proximity
        radius_km: Search radius in kilometers
        symptoms: List of symptoms for overlap matching
        days: Time window in days
        exclude_report_id: Report ID to exclude (the current report)
        limit: Maximum results to return

    Returns:
        List of related Report objects
    """
    since = datetime.utcnow() - timedelta(days=days)
    conditions = [Report.created_at >= since]

    if exclude_report_id is not None:
        conditions.append(Report.id != exclude_report_id)

    if suspected_disease is not None and suspected_disease != DiseaseType.unknown:
        conditions.append(Report.suspected_disease == suspected_disease)

    # Geographic filtering
    if location_lat is not None and location_lon is not None:
        from geoalchemy2 import func as geo_func

        point = f"SRID=4326;POINT({location_lon} {location_lat})"
        conditions.append(Report.location_point.isnot(None))
        conditions.append(
            geo_func.ST_DWithin(
                Report.location_point,
                geo_func.ST_GeogFromText(point),
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

    # Symptom overlap filtering
    if symptoms:
        conditions.append(Report.symptoms.overlap(symptoms))

    result = await session.execute(
        select(Report)
        .where(and_(*conditions))
        .order_by(desc(Report.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


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
        from geoalchemy2 import func as geo_func

        point = f"SRID=4326;POINT({location_lon} {location_lat})"
        conditions.append(Report.location_point.isnot(None))
        conditions.append(
            geo_func.ST_DWithin(
                Report.location_point,
                geo_func.ST_GeogFromText(point),
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
    *,
    report_id_1: UUID,
    report_id_2: UUID,
    link_type: LinkType,
    confidence: float,
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
        link_type: Type of link (geographic, temporal, symptom, manual)
        confidence: Confidence score (0.0 to 1.0)
        metadata: Optional metadata dict
        created_by: Creator identifier

    Returns:
        Created ReportLink or None if duplicate or same IDs
    """
    if report_id_1 == report_id_2:
        return None

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
        session.add(link)
        await session.flush()
        return link
    except IntegrityError:
        await session.rollback()
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
        from geoalchemy2 import func as geo_func

        location_point = geo_func.ST_GeogFromText(location_point_wkt)

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
