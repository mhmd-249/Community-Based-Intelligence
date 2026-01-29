"""
Notification Service for CBI.

Creates, sends, and manages notifications for health officers.
Supports multiple delivery channels (dashboard, email, WhatsApp)
and generates bilingual content (Arabic + English).

Uses Redis pub/sub for real-time dashboard notifications.
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from cbi.agents.state import Classification
from cbi.config import get_logger
from cbi.db.models import (
    AuditLog,
    Notification,
    Officer,
    Report,
    UrgencyLevel,
)

logger = get_logger(__name__)

# Redis pub/sub channel for dashboard real-time updates
DASHBOARD_CHANNEL = "notifications:dashboard"

# Urgency ordering for query sorting (higher number = more urgent)
_URGENCY_SORT_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

# Channel mapping by urgency level
CHANNELS_BY_URGENCY: dict[str, list[str]] = {
    "critical": ["dashboard", "whatsapp", "email"],
    "high": ["dashboard", "email"],
    "medium": ["dashboard"],
    "low": ["dashboard"],
}

# Disease names in Arabic
_DISEASE_AR: dict[str, str] = {
    "cholera": "الكوليرا",
    "dengue": "حمى الضنك",
    "malaria": "الملاريا",
    "measles": "الحصبة",
    "meningitis": "التهاب السحايا",
    "unknown": "مرض غير محدد",
}

# Urgency labels in Arabic
_URGENCY_AR: dict[str, str] = {
    "critical": "حرج",
    "high": "مرتفع",
    "medium": "متوسط",
    "low": "منخفض",
}

# Recommended actions by urgency
_DEFAULT_ACTIONS: dict[str, list[str]] = {
    "critical": [
        "Immediate field investigation required",
        "Alert regional health coordinator",
        "Prepare rapid response team",
    ],
    "high": [
        "Investigate within 24 hours",
        "Notify district health officer",
    ],
    "medium": [
        "Review and assess within 48 hours",
    ],
    "low": [
        "Monitor and follow up as needed",
    ],
}


# =============================================================================
# Notification Content Generation
# =============================================================================


def _generate_title(
    disease: str,
    urgency: str,
    *,
    language: str = "en",
) -> str:
    """
    Generate a notification title based on disease and urgency.

    Args:
        disease: Disease type string
        urgency: Urgency level string
        language: Language code ('en' or 'ar')

    Returns:
        Formatted notification title
    """
    if language == "ar":
        disease_name = _DISEASE_AR.get(disease, disease)
        urgency_label = _URGENCY_AR.get(urgency, urgency)
        return f"⚠️ تنبيه صحي [{urgency_label}]: {disease_name}"

    urgency_upper = urgency.upper()
    disease_display = disease.replace("_", " ").title()
    return f"⚠️ Health Alert [{urgency_upper}]: {disease_display}"


def _generate_body(
    classification: dict[str, Any],
    report: Report | None = None,
    *,
    language: str = "en",
) -> str:
    """
    Generate notification body with case details and recommended actions.

    Args:
        classification: Classification dict with disease, urgency, etc.
        report: Optional Report model for additional details
        language: Language code ('en' or 'ar')

    Returns:
        Formatted notification body
    """
    disease = classification.get("suspected_disease", "unknown")
    urgency = classification.get("urgency", "medium")
    confidence = classification.get("confidence", 0.0)
    actions = classification.get("recommended_actions", [])

    # Fall back to default actions if none provided
    if not actions:
        actions = _DEFAULT_ACTIONS.get(urgency, [])

    if language == "ar":
        return _generate_body_ar(disease, urgency, confidence, actions, report)

    return _generate_body_en(disease, urgency, confidence, actions, report)


def _generate_body_en(
    disease: str,
    urgency: str,
    confidence: float,
    actions: list[str],
    report: Report | None,
) -> str:
    """Generate English notification body."""
    lines = []

    # Disease and confidence
    disease_display = disease.replace("_", " ").title()
    lines.append(f"Suspected Disease: {disease_display}")
    lines.append(f"Confidence: {confidence:.0%}")
    lines.append(f"Urgency: {urgency.upper()}")

    # Report details if available
    if report:
        if report.location_text:
            lines.append(f"Location: {report.location_text}")
        if report.symptoms:
            lines.append(f"Symptoms: {', '.join(report.symptoms)}")
        lines.append(f"Cases: {report.cases_count}")
        if report.deaths_count > 0:
            lines.append(f"Deaths: {report.deaths_count}")

    # Recommended actions
    if actions:
        lines.append("")
        lines.append("Recommended Actions:")
        for i, action in enumerate(actions, 1):
            lines.append(f"  {i}. {action}")

    return "\n".join(lines)


def _generate_body_ar(
    disease: str,
    urgency: str,
    confidence: float,
    actions: list[str],
    report: Report | None,
) -> str:
    """Generate Arabic notification body."""
    lines = []

    disease_name = _DISEASE_AR.get(disease, disease)
    urgency_label = _URGENCY_AR.get(urgency, urgency)

    lines.append(f"المرض المشتبه: {disease_name}")
    lines.append(f"درجة الثقة: {confidence:.0%}")
    lines.append(f"مستوى الطوارئ: {urgency_label}")

    if report:
        if report.location_text:
            lines.append(f"الموقع: {report.location_text}")
        if report.symptoms:
            lines.append(f"الأعراض: {', '.join(report.symptoms)}")
        lines.append(f"عدد الحالات: {report.cases_count}")
        if report.deaths_count > 0:
            lines.append(f"عدد الوفيات: {report.deaths_count}")

    if actions:
        lines.append("")
        lines.append("الإجراءات الموصى بها:")
        for i, action in enumerate(actions, 1):
            lines.append(f"  {i}. {action}")

    return "\n".join(lines)


# =============================================================================
# Notification Service Functions
# =============================================================================


async def create_notification(
    session: AsyncSession,
    report_id: UUID,
    officer_id: UUID | None,
    urgency: str,
    classification: Classification | dict,
) -> UUID:
    """
    Create a notification record for a health officer.

    Generates bilingual title and body, determines delivery channels
    based on urgency, and inserts the notification into the database.

    Args:
        session: Async database session
        report_id: UUID of the associated report
        officer_id: UUID of the target officer (None for broadcast)
        urgency: Urgency level string (critical/high/medium/low)
        classification: Classification model or dict with disease data

    Returns:
        UUID of the created notification
    """
    # Convert Classification model to dict if needed
    if hasattr(classification, "model_dump"):
        classification_data = classification.model_dump()
    elif isinstance(classification, dict):
        classification_data = classification
    else:
        classification_data = {}

    # Load the report for additional context
    report: Report | None = None
    try:
        result = await session.execute(
            select(Report).where(Report.id == report_id)
        )
        report = result.scalar_one_or_none()
    except Exception as e:
        logger.warning(
            "Could not load report for notification",
            report_id=str(report_id),
            error=str(e),
        )

    # Determine officer language preference (default: English)
    officer_language = "en"
    if officer_id:
        try:
            result = await session.execute(
                select(Officer).where(Officer.id == officer_id)
            )
            officer = result.scalar_one_or_none()
            # Officer model has no language field; default to English
            # Future: add preferred_language to Officer model
            if officer and officer.region:
                # Officers in Sudan default to Arabic
                officer_language = "ar"
        except Exception:
            pass

    # Generate bilingual content
    title_en = _generate_title(
        classification_data.get("suspected_disease", "unknown"),
        urgency,
        language="en",
    )
    title_ar = _generate_title(
        classification_data.get("suspected_disease", "unknown"),
        urgency,
        language="ar",
    )
    body_en = _generate_body(classification_data, report, language="en")
    body_ar = _generate_body(classification_data, report, language="ar")

    # Use officer's preferred language for primary content
    title = title_ar if officer_language == "ar" else title_en
    body = body_ar if officer_language == "ar" else body_en

    # Determine channels based on urgency
    channels = CHANNELS_BY_URGENCY.get(urgency, ["dashboard"])

    # Validate urgency enum
    try:
        urgency_enum = UrgencyLevel(urgency)
    except ValueError:
        urgency_enum = UrgencyLevel.medium

    # Build metadata with both language versions
    metadata = {
        "title_en": title_en,
        "title_ar": title_ar,
        "body_en": body_en,
        "body_ar": body_ar,
        "classification": classification_data,
        "report_id": str(report_id),
    }

    notification = Notification(
        report_id=report_id,
        officer_id=officer_id,
        urgency=urgency_enum,
        title=title,
        body=body,
        channels=channels,
        metadata_=metadata,
    )

    session.add(notification)
    await session.flush()

    logger.info(
        "Notification created",
        notification_id=str(notification.id),
        report_id=str(report_id),
        officer_id=str(officer_id) if officer_id else None,
        urgency=urgency,
        channels=channels,
    )

    return notification.id


async def send_notification(notification_id: UUID) -> None:
    """
    Load a notification and dispatch it to all configured channels.

    For each channel in the notification:
    - dashboard: Publishes via Redis pub/sub for real-time display
    - email: Queues an email (placeholder for future implementation)
    - whatsapp: Sends a template message to the officer (placeholder)

    Args:
        notification_id: UUID of the notification to send
    """
    from cbi.db.session import get_session

    async with get_session() as session:
        result = await session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        notification = result.scalar_one_or_none()

        if notification is None:
            logger.error(
                "Notification not found for sending",
                notification_id=str(notification_id),
            )
            return

        channels = notification.channels or ["dashboard"]
        metadata = notification.metadata_ or {}

        notification_data = {
            "id": str(notification.id),
            "report_id": str(notification.report_id) if notification.report_id else None,
            "officer_id": str(notification.officer_id) if notification.officer_id else None,
            "urgency": (
                notification.urgency.value
                if hasattr(notification.urgency, "value")
                else notification.urgency
            ),
            "title": notification.title,
            "body": notification.body,
            "channels": channels,
            "title_en": metadata.get("title_en", notification.title),
            "title_ar": metadata.get("title_ar", ""),
            "body_en": metadata.get("body_en", notification.body),
            "body_ar": metadata.get("body_ar", ""),
            "sent_at": notification.sent_at.isoformat() if notification.sent_at else None,
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
        }

        for channel in channels:
            try:
                if channel == "dashboard":
                    await publish_to_dashboard(notification_data)
                elif channel == "email":
                    # Placeholder: email integration to be implemented
                    logger.info(
                        "Email notification queued (not yet implemented)",
                        notification_id=str(notification_id),
                        officer_id=str(notification.officer_id),
                    )
                elif channel == "whatsapp":
                    # Placeholder: WhatsApp template message to officer
                    logger.info(
                        "WhatsApp notification queued (not yet implemented)",
                        notification_id=str(notification_id),
                        officer_id=str(notification.officer_id),
                    )
                else:
                    logger.warning(
                        "Unknown notification channel",
                        channel=channel,
                        notification_id=str(notification_id),
                    )
            except Exception as e:
                logger.error(
                    "Failed to send notification via channel",
                    channel=channel,
                    notification_id=str(notification_id),
                    error=str(e),
                )

    logger.info(
        "Notification dispatched",
        notification_id=str(notification_id),
        channels=channels,
    )


async def publish_to_dashboard(notification: dict) -> None:
    """
    Publish a notification to the Redis pub/sub channel for real-time dashboard display.

    The dashboard frontend listens on the 'notifications:dashboard' channel
    via Socket.io / WebSocket bridge.

    Args:
        notification: Full notification data dict including id, urgency,
                      title, body, and bilingual content
    """
    from cbi.services.message_queue import get_redis_client

    try:
        client = await get_redis_client()
        payload = json.dumps(notification, ensure_ascii=False, default=str)

        subscribers = await client.publish(DASHBOARD_CHANNEL, payload)

        logger.debug(
            "Published notification to dashboard",
            notification_id=notification.get("id"),
            channel=DASHBOARD_CHANNEL,
            subscribers=subscribers,
        )
    except Exception as e:
        logger.error(
            "Failed to publish notification to dashboard",
            notification_id=notification.get("id"),
            error=str(e),
        )
        raise


async def mark_as_read(
    session: AsyncSession,
    notification_id: UUID,
    officer_id: UUID,
) -> bool:
    """
    Mark a notification as read and log the action in audit_logs.

    Args:
        session: Async database session
        notification_id: UUID of the notification to mark
        officer_id: UUID of the officer marking it read

    Returns:
        True if the notification was marked read, False if not found or already read
    """
    result = await session.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.officer_id == officer_id,
            )
        )
    )
    notification = result.scalar_one_or_none()

    if notification is None:
        logger.warning(
            "Notification not found or not owned by officer",
            notification_id=str(notification_id),
            officer_id=str(officer_id),
        )
        return False

    if notification.read_at is not None:
        logger.debug(
            "Notification already read",
            notification_id=str(notification_id),
        )
        return False

    notification.read_at = datetime.utcnow()
    await session.flush()

    # Log in audit_logs
    audit = AuditLog(
        entity_type="notification",
        entity_id=notification_id,
        action="mark_as_read",
        actor_type="officer",
        actor_id=str(officer_id),
        changes={
            "read_at": notification.read_at.isoformat(),
            "report_id": str(notification.report_id) if notification.report_id else None,
        },
    )
    session.add(audit)
    await session.flush()

    logger.info(
        "Notification marked as read",
        notification_id=str(notification_id),
        officer_id=str(officer_id),
    )

    return True


async def get_unread_notifications(
    session: AsyncSession,
    officer_id: UUID,
    *,
    limit: int = 50,
) -> list[dict]:
    """
    Get all unread notifications for an officer.

    Results are ordered by urgency (critical first) then by creation time
    (most recent first).

    Args:
        session: Async database session
        officer_id: UUID of the officer
        limit: Maximum number of notifications to return

    Returns:
        List of notification dicts with id, report_id, urgency, title,
        body, channels, metadata, sent_at, created_at
    """
    # Order by urgency priority, then by most recent
    urgency_order = case(
        (Notification.urgency == UrgencyLevel.critical, 0),
        (Notification.urgency == UrgencyLevel.high, 1),
        (Notification.urgency == UrgencyLevel.medium, 2),
        (Notification.urgency == UrgencyLevel.low, 3),
        else_=4,
    )

    result = await session.execute(
        select(Notification)
        .where(
            and_(
                Notification.officer_id == officer_id,
                Notification.read_at.is_(None),
            )
        )
        .order_by(urgency_order, desc(Notification.created_at))
        .limit(limit)
    )
    notifications = list(result.scalars().all())

    return [
        {
            "id": str(n.id),
            "report_id": str(n.report_id) if n.report_id else None,
            "urgency": (
                n.urgency.value if hasattr(n.urgency, "value") else n.urgency
            ),
            "title": n.title,
            "body": n.body,
            "channels": n.channels or [],
            "metadata": n.metadata_ or {},
            "sent_at": n.sent_at.isoformat() if n.sent_at else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]
