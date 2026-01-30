"""
Reports API endpoints.

CRUD operations and detail views for health incident reports.
"""

import math
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from cbi.api.deps import CurrentOfficer, DB
from cbi.api.schemas import (
    MessageResponse,
    ReportDetailResponse,
    ReportListResponse,
    ReportNoteCreate,
    ReportResponse,
    ReportStatsResponse,
    ReportUpdate,
)
from cbi.api.schemas.reports import (
    InvestigationNote,
    LinkedReportItem,
    NotificationSummary,
    OfficerSummary,
    ReporterSummary,
    ReportListItem,
    TimelineEvent,
)
from cbi.config import get_logger
from cbi.db.models import DiseaseType, ReportStatus, UrgencyLevel
from cbi.db.queries import (
    create_audit_log,
    get_audit_logs_for_entity,
    get_detailed_report_stats,
    get_linked_reports,
    get_notifications_for_report,
    get_report_by_id,
    list_reports_paginated,
)

router = APIRouter()
logger = get_logger(__name__)


def _build_report_response(report) -> ReportResponse:
    """Build a ReportResponse from a Report model instance."""
    reporter_summary = None
    if report.reporter:
        reporter_summary = ReporterSummary(
            id=report.reporter.id,
            preferred_language=report.reporter.preferred_language,
            total_reports=report.reporter.total_reports,
        )

    officer_summary = None
    if report.officer:
        officer_summary = OfficerSummary(
            id=report.officer.id,
            name=report.officer.name,
            region=report.officer.region,
        )

    return ReportResponse(
        id=report.id,
        conversation_id=report.conversation_id,
        status=report.status,
        symptoms=report.symptoms or [],
        suspected_disease=report.suspected_disease,
        reporter_relation=report.reporter_relation,
        location_text=report.location_text,
        location_normalized=report.location_normalized,
        onset_text=report.onset_text,
        onset_date=report.onset_date,
        cases_count=report.cases_count,
        deaths_count=report.deaths_count,
        affected_groups=report.affected_groups,
        urgency=report.urgency,
        alert_type=report.alert_type,
        data_completeness=report.data_completeness,
        confidence_score=report.confidence_score,
        source=report.source,
        resolved_at=report.resolved_at,
        outcome=report.outcome,
        created_at=report.created_at,
        updated_at=report.updated_at,
        reporter=reporter_summary,
        officer=officer_summary,
    )


@router.get("/", response_model=ReportListResponse)
async def list_reports(
    db: DB,
    officer: CurrentOfficer,
    status: ReportStatus | None = None,
    urgency: UrgencyLevel | None = None,
    disease: DiseaseType | None = None,
    region: str | None = None,
    from_date: date | None = Query(None, alias="fromDate"),
    to_date: date | None = Query(None, alias="toDate"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
) -> ReportListResponse:
    """
    List reports with optional filtering and pagination.

    Non-admin officers see only reports in their region.
    """
    # Region filtering: non-admin officers only see their region
    effective_region = region
    if officer.role != "admin" and officer.region:
        effective_region = officer.region

    reports, total = await list_reports_paginated(
        db,
        status=status,
        urgency=urgency,
        disease=disease,
        region=effective_region,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )

    items = [
        ReportListItem(
            id=r.id,
            conversation_id=r.conversation_id,
            status=r.status,
            suspected_disease=r.suspected_disease,
            location_normalized=r.location_normalized,
            urgency=r.urgency,
            alert_type=r.alert_type,
            cases_count=r.cases_count,
            deaths_count=r.deaths_count,
            created_at=r.created_at,
        )
        for r in reports
    ]

    pages = math.ceil(total / page_size) if total > 0 else 0

    logger.info(
        "Listed reports",
        officer_id=str(officer.id),
        total=total,
        page=page,
    )

    return ReportListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/stats", response_model=ReportStatsResponse)
async def get_stats(
    db: DB,
    officer: CurrentOfficer,
    days: int = Query(7, ge=1, le=90),
) -> ReportStatsResponse:
    """Get report statistics for the dashboard."""
    stats = await get_detailed_report_stats(db, days=days)

    logger.info("Report stats fetched", officer_id=str(officer.id), days=days)

    return ReportStatsResponse(
        total=stats["total"],
        open=stats["open"],
        critical=stats["critical"],
        resolved=stats["resolved"],
        by_disease=stats["by_disease"],
        by_urgency=stats["by_urgency"],
    )


@router.get("/{report_id}", response_model=ReportDetailResponse)
async def get_report(
    report_id: UUID,
    db: DB,
    officer: CurrentOfficer,
) -> ReportDetailResponse:
    """
    Get a single report with full details.

    Includes linked reports, notification history, investigation notes,
    raw conversation, and extracted entities.
    """
    report = await get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    # Build base response fields
    base = _build_report_response(report)

    # Investigation notes from JSONB
    notes = [
        InvestigationNote(**n)
        for n in (report.investigation_notes or [])
    ]

    # Linked reports
    linked_data = await get_linked_reports(db, report_id)
    linked = [
        LinkedReportItem(
            id=ld["id"],
            symptoms=ld["symptoms"],
            suspected_disease=ld["suspected_disease"],
            cases_count=ld["cases_count"],
            location_text=ld.get("location_text"),
            created_at=ld["created_at"],
            link_type=ld["link_type"] or "unknown",
            confidence=ld.get("confidence", 0.0),
        )
        for ld in linked_data
    ]

    # Notification history
    notifs = await get_notifications_for_report(db, report_id)
    notification_summaries = [
        NotificationSummary(
            id=n.id,
            urgency=n.urgency,
            title=n.title,
            sent_at=n.sent_at,
            read_at=n.read_at,
        )
        for n in notifs
    ]

    logger.info(
        "Report detail fetched",
        report_id=str(report_id),
        officer_id=str(officer.id),
    )

    return ReportDetailResponse(
        **base.model_dump(),
        investigation_notes=notes,
        linked_reports=linked,
        notifications=notification_summaries,
        raw_conversation=report.raw_conversation or [],
        extracted_entities=report.extracted_entities or {},
    )


@router.patch("/{report_id}", response_model=ReportResponse)
async def update_report(
    report_id: UUID,
    update: ReportUpdate,
    db: DB,
    officer: CurrentOfficer,
) -> ReportResponse:
    """
    Update a report.

    Allowed fields: status, officer_id, investigation_notes, outcome,
    symptoms, suspected_disease, urgency, alert_type, and more.

    Status changes to 'resolved' automatically set resolved_at.
    All changes are logged in audit_logs.
    """
    report = await get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    changes = update.model_dump(exclude_unset=True)
    if not changes:
        return _build_report_response(report)

    old_values: dict = {}

    # Track status change specifically
    old_status = report.status

    # Apply each changed field
    for field, value in changes.items():
        # investigation_notes on the update schema is a text shorthand;
        # it gets appended as a note rather than overwriting the list
        if field == "investigation_notes" and value is not None:
            note_entry = {
                "content": value,
                "officer_id": str(officer.id),
                "officer_name": officer.name,
                "created_at": datetime.utcnow().isoformat(),
            }
            current_notes = list(report.investigation_notes or [])
            current_notes.append(note_entry)
            old_values[field] = len(report.investigation_notes or [])
            report.investigation_notes = current_notes
            continue

        if field == "location":
            # Skip location point updates for now (requires WKT conversion)
            continue

        if hasattr(report, field):
            old_values[field] = getattr(report, field)
            setattr(report, field, value)

    # Auto-set resolved_at when status changes to resolved
    if (
        "status" in changes
        and changes["status"] == ReportStatus.resolved
        and old_status != ReportStatus.resolved
    ):
        report.resolved_at = datetime.utcnow()

    await db.flush()

    # Audit log
    await create_audit_log(
        db,
        entity_type="report",
        entity_id=report_id,
        action="update",
        actor_id=str(officer.id),
        changes={
            "fields": list(changes.keys()),
            "old_status": old_status.value if hasattr(old_status, "value") else str(old_status),
            "new_status": report.status.value if hasattr(report.status, "value") else str(report.status),
        },
    )

    await db.commit()

    logger.info(
        "Report updated",
        report_id=str(report_id),
        officer_id=str(officer.id),
        fields=list(changes.keys()),
    )

    return _build_report_response(report)


@router.post("/{report_id}/notes", response_model=MessageResponse)
async def add_report_note(
    report_id: UUID,
    note: ReportNoteCreate,
    db: DB,
    officer: CurrentOfficer,
) -> MessageResponse:
    """
    Add an investigation note to a report.

    Notes are stored as a JSONB array with timestamps and author info.
    Each addition is logged in audit_logs.
    """
    report = await get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    note_entry = {
        "content": note.content,
        "officer_id": str(officer.id),
        "officer_name": officer.name,
        "created_at": datetime.utcnow().isoformat(),
    }

    current_notes = list(report.investigation_notes or [])
    current_notes.append(note_entry)
    report.investigation_notes = current_notes

    await db.flush()

    # Audit log
    await create_audit_log(
        db,
        entity_type="report",
        entity_id=report_id,
        action="note_added",
        actor_id=str(officer.id),
        changes={"note_content": note.content},
    )

    await db.commit()

    logger.info(
        "Note added to report",
        report_id=str(report_id),
        officer_id=str(officer.id),
    )

    return MessageResponse(message="Note added successfully")


@router.get("/{report_id}/linked", response_model=list[LinkedReportItem])
async def get_linked(
    report_id: UUID,
    db: DB,
    officer: CurrentOfficer,
) -> list[LinkedReportItem]:
    """Get all reports linked to this report with link metadata."""
    report = await get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    linked_data = await get_linked_reports(db, report_id)

    return [
        LinkedReportItem(
            id=ld["id"],
            symptoms=ld["symptoms"],
            suspected_disease=ld["suspected_disease"],
            cases_count=ld["cases_count"],
            location_text=ld.get("location_text"),
            created_at=ld["created_at"],
            link_type=ld["link_type"] or "unknown",
            confidence=ld.get("confidence", 0.0),
        )
        for ld in linked_data
    ]


@router.get("/{report_id}/timeline", response_model=list[TimelineEvent])
async def get_timeline(
    report_id: UUID,
    db: DB,
    officer: CurrentOfficer,
) -> list[TimelineEvent]:
    """
    Get chronological timeline of events for a report.

    Aggregates: report creation, status changes, notes added,
    notifications sent, and linked cases.
    """
    report = await get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    events: list[TimelineEvent] = []

    # 1. Report creation
    events.append(TimelineEvent(
        event_type="created",
        timestamp=report.created_at,
        description=f"Report created from {report.source}",
        metadata={"source": report.source, "conversation_id": report.conversation_id},
    ))

    # 2. Audit log events (status changes, updates, notes)
    audit_logs = await get_audit_logs_for_entity(db, "report", report_id)
    for log in audit_logs:
        if log.action == "update":
            changes = log.changes or {}
            old_s = changes.get("old_status", "")
            new_s = changes.get("new_status", "")
            fields = changes.get("fields", [])

            if old_s != new_s and old_s and new_s:
                events.append(TimelineEvent(
                    event_type="status_change",
                    timestamp=log.created_at,
                    description=f"Status changed from {old_s} to {new_s}",
                    actor=log.actor_id,
                    metadata={"old_status": old_s, "new_status": new_s},
                ))
            else:
                events.append(TimelineEvent(
                    event_type="updated",
                    timestamp=log.created_at,
                    description=f"Updated fields: {', '.join(fields)}",
                    actor=log.actor_id,
                    metadata={"fields": fields},
                ))
        elif log.action == "note_added":
            events.append(TimelineEvent(
                event_type="note_added",
                timestamp=log.created_at,
                description="Investigation note added",
                actor=log.actor_id,
            ))

    # 3. Notifications
    notifs = await get_notifications_for_report(db, report_id)
    for n in notifs:
        events.append(TimelineEvent(
            event_type="notification_sent",
            timestamp=n.sent_at,
            description=n.title,
            metadata={
                "urgency": n.urgency.value if hasattr(n.urgency, "value") else str(n.urgency),
                "read_at": n.read_at.isoformat() if n.read_at else None,
            },
        ))

    # 4. Linked cases
    linked_data = await get_linked_reports(db, report_id)
    for ld in linked_data:
        events.append(TimelineEvent(
            event_type="case_linked",
            timestamp=ld["created_at"],
            description=f"Linked to case ({ld['link_type']} match, confidence {ld.get('confidence', 0):.0%})",
            metadata={
                "linked_report_id": str(ld["id"]),
                "link_type": ld["link_type"],
                "confidence": ld.get("confidence", 0.0),
            },
        ))

    # Sort chronologically
    events.sort(key=lambda e: e.timestamp)

    return events
