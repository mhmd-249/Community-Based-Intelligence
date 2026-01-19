"""
Reports API endpoints.

CRUD operations for health incident reports.
"""

from uuid import UUID

from fastapi import APIRouter, Query

from cbi.api.deps import CurrentOfficer, DB
from cbi.api.schemas import (
    MessageResponse,
    ReportListResponse,
    ReportNoteCreate,
    ReportResponse,
    ReportStatsResponse,
    ReportUpdate,
)
from cbi.config import get_logger
from cbi.db.models import ReportStatus, UrgencyLevel

router = APIRouter()
logger = get_logger(__name__)


@router.get("/", response_model=ReportListResponse)
async def list_reports(
    db: DB,
    officer: CurrentOfficer,
    status: ReportStatus | None = None,
    urgency: UrgencyLevel | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ReportListResponse:
    """
    List reports with optional filtering.

    TODO: Implement in Phase 2
    - Query reports with filters
    - Paginate results
    - Include summary data
    """
    logger.info(
        "Listing reports",
        officer_id=str(officer.id),
        status=status,
        urgency=urgency,
    )

    # Placeholder response
    return ReportListResponse(
        items=[],
        total=0,
        page=page,
        page_size=page_size,
        pages=0,
    )


@router.get("/stats", response_model=ReportStatsResponse)
async def get_report_stats(
    db: DB,
    officer: CurrentOfficer,
    days: int = Query(7, ge=1, le=90),
) -> ReportStatsResponse:
    """
    Get report statistics for dashboard.

    TODO: Implement in Phase 2
    - Query aggregated stats
    - Group by disease, urgency
    """
    logger.info("Getting report stats", officer_id=str(officer.id), days=days)

    # Placeholder response
    return ReportStatsResponse(
        total=0,
        open=0,
        critical=0,
        resolved=0,
        by_disease={},
        by_urgency={},
    )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: UUID,
    db: DB,
    officer: CurrentOfficer,
) -> ReportResponse:
    """
    Get a single report by ID.

    TODO: Implement in Phase 2
    - Fetch report with relationships
    - Return 404 if not found
    """
    logger.info("Getting report", report_id=str(report_id), officer_id=str(officer.id))

    # Placeholder - raise not implemented for now
    from fastapi import HTTPException

    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/{report_id}", response_model=ReportResponse)
async def update_report(
    report_id: UUID,
    update: ReportUpdate,
    db: DB,
    officer: CurrentOfficer,
) -> ReportResponse:
    """
    Update a report.

    TODO: Implement in Phase 2
    - Validate report exists
    - Apply updates
    - Create audit log entry
    """
    logger.info(
        "Updating report",
        report_id=str(report_id),
        officer_id=str(officer.id),
        updates=update.model_dump(exclude_unset=True),
    )

    from fastapi import HTTPException

    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/{report_id}/notes", response_model=MessageResponse)
async def add_report_note(
    report_id: UUID,
    note: ReportNoteCreate,
    db: DB,
    officer: CurrentOfficer,
) -> MessageResponse:
    """
    Add a note to a report.

    TODO: Implement in Phase 2
    - Validate report exists
    - Store note (in raw_conversation JSONB or separate table)
    - Create audit log entry
    """
    logger.info(
        "Adding note to report",
        report_id=str(report_id),
        officer_id=str(officer.id),
    )

    # Placeholder response
    return MessageResponse(message="Note added successfully")
