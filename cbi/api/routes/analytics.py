"""
Analytics API endpoints.

Natural language queries and visualizations powered by Analyst Agent.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import Field

from cbi.agents.analyst import (
    get_disease_summary,
    get_geographic_hotspots,
    process_query,
)
from cbi.api.deps import DB, CurrentOfficer
from cbi.api.schemas import CamelCaseModel
from cbi.config import get_logger
from cbi.db.queries import get_detailed_report_stats

router = APIRouter()
logger = get_logger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================


class QueryRequest(CamelCaseModel):
    """Natural language query request."""

    query: str = Field(..., min_length=3, max_length=500)
    region_filter: str | None = Field(
        None,
        description="Optional region to filter results",
    )


class QueryResponse(CamelCaseModel):
    """Query response with answer and optional data."""

    success: bool
    answer: str
    data: list[dict[str, Any]] | None = None
    total_records: int | None = None
    visualization_type: str | None = None
    visualization_config: dict[str, Any] | None = None
    query_type: str | None = None
    error: str | None = None
    generated_at: str | None = None


class VisualizeRequest(CamelCaseModel):
    """Visualization request."""

    query: str = Field(..., min_length=3, max_length=500)
    chart_type: str | None = Field(
        None,
        description="Preferred chart type: line, bar, pie, map, table",
    )
    time_range_days: int = Field(7, ge=1, le=365)
    region_filter: str | None = None


class VisualizeResponse(CamelCaseModel):
    """Visualization response with chart data."""

    success: bool
    chart_type: str
    title: str
    data: list[dict[str, Any]]
    config: dict[str, Any]
    generated_at: str


class DiseaseSummaryResponse(CamelCaseModel):
    """Disease-specific summary response."""

    disease: str
    period_days: int
    case_count: int
    previous_period_count: int
    trend: str
    change_percentage: float
    locations: list[str]
    generated_at: str


class HotspotResponse(CamelCaseModel):
    """Geographic hotspot response."""

    location: str
    disease: str
    report_count: int
    total_affected: int
    total_deaths: int
    max_urgency: str


class SituationSummaryResponse(CamelCaseModel):
    """AI-generated situation summary response."""

    summary: str
    period_days: int
    total_reports: int
    open_reports: int
    critical_reports: int
    by_disease: dict[str, int]
    by_urgency: dict[str, int]
    hotspots: list[HotspotResponse]
    generated_at: str


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/query", response_model=QueryResponse)
async def natural_language_query(
    request: QueryRequest,
    _db: DB,  # noqa: ARG001 - Required for dependency injection
    officer: CurrentOfficer,
) -> QueryResponse:
    """
    Execute a natural language query against the database.

    Uses the Analyst Agent to interpret the query and generate SQL.

    Example queries:
    - "How many cholera cases in Khartoum this week?"
    - "Show me the trend of malaria reports over the last month"
    - "Which regions have the highest death rates?"
    - "Compare this week's cases to last week"
    - "What's happening in Darfur?"
    """
    logger.info(
        "Processing analytics query",
        officer_id=str(officer.id),
        query=request.query,
    )

    try:
        # Process query through Analyst Agent
        result = await process_query(
            query=request.query,
            officer_id=officer.id,
            region_filter=request.region_filter,
        )

        if result.get("success"):
            return QueryResponse(
                success=True,
                answer=result.get("summary", "Query completed."),
                data=result.get("data"),
                total_records=result.get("total_records"),
                visualization_type=result.get("visualization_type"),
                visualization_config=result.get("visualization_config"),
                query_type=result.get("intent", {}).get("query_type"),
                generated_at=result.get("generated_at"),
            )
        else:
            return QueryResponse(
                success=False,
                answer=result.get("error", "Query failed"),
                error=result.get("error_type"),
                generated_at=datetime.utcnow().isoformat(),
            )

    except Exception as e:
        logger.exception(
            "Error processing analytics query",
            officer_id=str(officer.id),
            error=str(e),
        )
        return QueryResponse(
            success=False,
            answer="An error occurred processing your query.",
            error=str(e),
            generated_at=datetime.utcnow().isoformat(),
        )


@router.post("/visualize", response_model=VisualizeResponse)
async def generate_visualization(
    request: VisualizeRequest,
    _db: DB,  # noqa: ARG001 - Required for dependency injection
    officer: CurrentOfficer,
) -> VisualizeResponse:
    """
    Generate a visualization based on natural language request.

    Uses the Analyst Agent to determine appropriate chart type and data.

    Example requests:
    - "Show disease distribution as a pie chart"
    - "Map of all reports this week"
    - "Timeline of critical alerts"
    - "Bar chart of cases by region"
    """
    logger.info(
        "Generating visualization",
        officer_id=str(officer.id),
        query=request.query,
        chart_type=request.chart_type,
    )

    try:
        # Process query to get data for visualization
        result = await process_query(
            query=request.query,
            officer_id=officer.id,
            region_filter=request.region_filter,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to generate visualization"),
            )

        # Use requested chart type or let the agent decide
        chart_type = request.chart_type or result.get("visualization_type", "table")
        viz_config = result.get("visualization_config", {})

        return VisualizeResponse(
            success=True,
            chart_type=chart_type,
            title=viz_config.get("title", "Query Results"),
            data=result.get("data", []),
            config=viz_config,
            generated_at=result.get("generated_at", datetime.utcnow().isoformat()),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Error generating visualization",
            officer_id=str(officer.id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="An error occurred generating the visualization",
        ) from e


@router.get("/summary", response_model=SituationSummaryResponse)
async def get_situation_summary(
    db: DB,
    officer: CurrentOfficer,
    days: int = 7,
) -> SituationSummaryResponse:
    """
    Get an AI-generated situation summary.

    Returns overall statistics and highlights for the specified period.
    """
    logger.info(
        "Generating situation summary",
        officer_id=str(officer.id),
        days=days,
    )

    try:
        # Get detailed statistics
        stats = await get_detailed_report_stats(db, days=days)

        # Get geographic hotspots
        hotspots = await get_geographic_hotspots(days=days, min_cases=2)

        # Build summary text
        summary_parts = []
        summary_parts.append(
            f"In the past {days} days, there have been {stats['total']} reports "
            f"with {stats['open']} still open."
        )

        if stats["critical"] > 0:
            summary_parts.append(
                f"There are {stats['critical']} critical reports requiring immediate attention."
            )

        if hotspots:
            top_hotspot = hotspots[0]
            summary_parts.append(
                f"The main hotspot is {top_hotspot['location']} with "
                f"{top_hotspot['report_count']} {top_hotspot['disease']} reports."
            )

        # Convert hotspots to response format
        hotspot_responses = [
            HotspotResponse(
                location=h["location"],
                disease=h["disease"],
                report_count=h["report_count"],
                total_affected=h["total_affected"],
                total_deaths=h["total_deaths"],
                max_urgency=h["max_urgency"],
            )
            for h in hotspots[:10]
        ]

        return SituationSummaryResponse(
            summary=" ".join(summary_parts),
            period_days=days,
            total_reports=stats["total"],
            open_reports=stats["open"],
            critical_reports=stats["critical"],
            by_disease=stats.get("by_disease", {}),
            by_urgency=stats.get("by_urgency", {}),
            hotspots=hotspot_responses,
            generated_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.exception(
            "Error generating situation summary",
            officer_id=str(officer.id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="An error occurred generating the situation summary",
        ) from e


@router.get("/disease/{disease}", response_model=DiseaseSummaryResponse)
async def get_disease_summary_endpoint(
    disease: str,
    _db: DB,  # noqa: ARG001 - Required for dependency injection
    officer: CurrentOfficer,
    days: int = 7,
) -> DiseaseSummaryResponse:
    """
    Get a summary for a specific disease.

    Returns case counts, trends, and affected locations.

    Args:
        disease: Disease name (cholera, dengue, malaria, measles, meningitis)
        days: Number of days to analyze
    """
    logger.info(
        "Fetching disease summary",
        officer_id=str(officer.id),
        disease=disease,
        days=days,
    )

    try:
        result = await get_disease_summary(disease=disease, days=days)

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return DiseaseSummaryResponse(
            disease=result["disease"],
            period_days=result["period_days"],
            case_count=result["case_count"],
            previous_period_count=result["previous_period_count"],
            trend=result["trend"],
            change_percentage=result["change_percentage"],
            locations=result["locations"],
            generated_at=datetime.utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Error fetching disease summary",
            officer_id=str(officer.id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="An error occurred fetching disease summary",
        ) from e


@router.get("/hotspots", response_model=list[HotspotResponse])
async def get_hotspots(
    _db: DB,  # noqa: ARG001 - Required for dependency injection
    officer: CurrentOfficer,
    days: int = 7,
    min_cases: int = 3,
) -> list[HotspotResponse]:
    """
    Get geographic hotspots with multiple cases.

    Returns locations with case clustering that may indicate outbreaks.

    Args:
        days: Number of days to analyze
        min_cases: Minimum cases to be considered a hotspot
    """
    logger.info(
        "Fetching geographic hotspots",
        officer_id=str(officer.id),
        days=days,
        min_cases=min_cases,
    )

    try:
        hotspots = await get_geographic_hotspots(days=days, min_cases=min_cases)

        return [
            HotspotResponse(
                location=h["location"],
                disease=h["disease"],
                report_count=h["report_count"],
                total_affected=h["total_affected"],
                total_deaths=h["total_deaths"],
                max_urgency=h["max_urgency"],
            )
            for h in hotspots
        ]

    except Exception as e:
        logger.exception(
            "Error fetching hotspots",
            officer_id=str(officer.id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="An error occurred fetching hotspots",
        ) from e
