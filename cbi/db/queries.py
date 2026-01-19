"""
Database queries for CBI.

Common query patterns for reports, reporters, officers, and notifications.
All queries use async SQLAlchemy patterns.
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cbi.db.models import (
    DiseaseType,
    Notification,
    Officer,
    Report,
    ReportLink,
    Reporter,
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
    query = select(Report).where(Report.status == ReportStatus.OPEN)

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
                Report.status == ReportStatus.OPEN,
                Report.created_at >= since,
            )
        )
    )
    open_count = open_result.scalar_one()

    # Critical reports
    critical_result = await session.execute(
        select(func.count(Report.id)).where(
            and_(
                Report.urgency == UrgencyLevel.CRITICAL,
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
