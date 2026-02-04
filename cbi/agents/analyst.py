"""
Analyst Agent for CBI.

Handles natural language database queries from health officers and generates
situation summaries when disease thresholds are exceeded.

Uses Claude Sonnet for superior reasoning in query understanding and
data interpretation tasks.
"""

import asyncio
import json
import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

import anthropic

from cbi.agents.reporter import parse_json_response as extract_json
from cbi.agents.state import ConversationState
from cbi.config import get_logger, get_settings
from cbi.config.llm_config import get_llm_config
from cbi.db.models import (
    DiseaseType,
)
from cbi.db.session import get_session

logger = get_logger(__name__)


# =============================================================================
# Security Configuration - Allowed Tables and Columns
# =============================================================================

# Whitelist of tables that can be queried
ALLOWED_TABLES = frozenset({
    "reports",
    "notifications",
    "report_links",
})

# Whitelist of columns per table that can be accessed
ALLOWED_COLUMNS = {
    "reports": frozenset({
        "id",
        "symptoms",
        "suspected_disease",
        "location_text",
        "location_normalized",
        "onset_date",
        "cases_count",
        "deaths_count",
        "urgency",
        "alert_type",
        "status",
        "created_at",
        "updated_at",
        "data_completeness",
        "confidence_score",
        "affected_groups",
        "reporter_relation",
    }),
    "notifications": frozenset({
        "id",
        "report_id",
        "urgency",
        "title",
        "sent_at",
        "read_at",
    }),
    "report_links": frozenset({
        "report_id_1",
        "report_id_2",
        "link_type",
        "confidence",
        "created_at",
    }),
}

# SQL keywords that are NOT allowed (write operations)
FORBIDDEN_SQL_KEYWORDS = frozenset({
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "CREATE",
    "ALTER",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "EXECUTE",
    "EXEC",
    "INTO",
    "SET",
    "MERGE",
    "CALL",
    "REPLACE",
})

# Query types that the analyst can handle
QueryType = Literal[
    "case_count",
    "trend",
    "comparison",
    "geographic",
    "timeline",
    "summary",
    "threshold_check",
]

# Query execution timeout in seconds
QUERY_TIMEOUT_SECONDS = 30


# =============================================================================
# Helper Functions
# =============================================================================


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Create and return an async Anthropic client."""
    settings = get_settings()
    return anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
    )


def validate_sql_query(sql: str) -> tuple[bool, str]:
    """
    Validate that a SQL query is safe to execute.

    Checks:
    1. Only SELECT statements allowed
    2. No forbidden keywords (INSERT, UPDATE, DELETE, etc.)
    3. Only queries allowed tables
    4. No SQL injection patterns

    Args:
        sql: SQL query string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Normalize SQL for checking
    sql_upper = sql.upper().strip()

    # Must start with SELECT or WITH (for CTEs)
    if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
        return False, "Query must be a SELECT statement"

    # Check for forbidden keywords
    # Use word boundary matching to avoid false positives
    for keyword in FORBIDDEN_SQL_KEYWORDS:
        # Match keyword as a whole word
        pattern = rf"\b{keyword}\b"
        if re.search(pattern, sql_upper):
            return False, f"Forbidden SQL keyword: {keyword}"

    # Check for semicolons (prevent query chaining)
    # Allow one at the end only
    semicolon_count = sql.count(";")
    if semicolon_count > 1:
        return False, "Multiple statements not allowed"
    if semicolon_count == 1 and not sql.strip().endswith(";"):
        return False, "Semicolon only allowed at end of query"

    # Check for SQL injection patterns
    injection_patterns = [
        r"--",  # SQL comment
        r"/\*",  # Block comment start
        r"\*/",  # Block comment end
        r";\s*SELECT",  # Chained SELECT
        r"UNION\s+ALL\s+SELECT",  # UNION injection (allow regular UNION)
    ]
    for pattern in injection_patterns:
        if re.search(pattern, sql_upper):
            return False, f"Potential SQL injection pattern detected: {pattern}"

    # Verify tables are in whitelist
    # First, extract CTE names from WITH clause (they are valid aliases)
    cte_names: set[str] = set()
    if sql_upper.startswith("WITH"):
        # Pattern to match CTE names: WITH name AS (...), name2 AS (...)
        cte_pattern = r"\bWITH\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\("
        cte_match = re.search(cte_pattern, sql_upper)
        if cte_match:
            cte_names.add(cte_match.group(1).lower())
        # Also check for additional CTEs after commas
        additional_ctes = r",\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\("
        cte_names.update(m.lower() for m in re.findall(additional_ctes, sql_upper))

    # Extract table names from FROM and JOIN clauses
    table_pattern = r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)"
    tables_found = re.findall(table_pattern, sql_upper)
    for table in tables_found:
        table_lower = table.lower()
        # Skip CTE names - they're aliases, not actual tables
        if table_lower in cte_names:
            continue
        if table_lower not in ALLOWED_TABLES:
            return False, f"Table not allowed: {table}"

    return True, ""


def get_schema_context() -> str:
    """
    Generate schema documentation for the LLM to understand available data.

    Returns:
        String describing the database schema
    """
    return """
## Database Schema for Queries

### reports table
- id: UUID - Unique report identifier
- symptoms: TEXT[] - Array of reported symptoms
- suspected_disease: ENUM('cholera', 'dengue', 'malaria', 'measles', 'meningitis', 'unknown')
- location_text: TEXT - Raw location description from reporter
- location_normalized: VARCHAR - Standardized location name
- onset_date: DATE - When symptoms started
- cases_count: INTEGER - Number of people affected
- deaths_count: INTEGER - Number of deaths reported
- urgency: ENUM('critical', 'high', 'medium', 'low')
- alert_type: ENUM('suspected_outbreak', 'cluster', 'single_case', 'rumor')
- status: ENUM('open', 'investigating', 'resolved', 'false_alarm')
- created_at: TIMESTAMP - When report was created
- data_completeness: FLOAT - Data quality score (0-1)
- confidence_score: FLOAT - Classification confidence (0-1)
- affected_groups: TEXT - Description of affected population
- reporter_relation: ENUM('self', 'family', 'neighbor', 'health_worker', 'community_leader', 'other')

### Common Query Patterns:
- Filter by disease: WHERE suspected_disease = 'cholera'
- Filter by time: WHERE created_at >= NOW() - INTERVAL '7 days'
- Filter by urgency: WHERE urgency = 'critical'
- Filter by location: WHERE location_normalized ILIKE '%Khartoum%'
- Count cases: SELECT COUNT(*) FROM reports WHERE ...
- Group by disease: GROUP BY suspected_disease
- Group by date: GROUP BY DATE(created_at)

### Sudan Locations:
States: Khartoum, Gezira, River Nile, North Darfur, South Darfur, West Darfur, East Darfur, Central Darfur, Kassala, Red Sea, North Kordofan, South Kordofan, West Kordofan, Blue Nile, White Nile, Sennar, Al Qadarif
Major cities: Khartoum, Omdurman, Bahri, Port Sudan, Kassala, Nyala, El Fasher, El Obeid, Wad Madani
"""


def format_query_response(
    results: list[dict],
    intent: dict,
    summary: str,
) -> dict:
    """
    Format query results into a structured response.

    Args:
        results: Raw query results as list of dicts
        intent: Parsed query intent
        summary: Human-readable summary from LLM

    Returns:
        Formatted response dict with data and visualization config
    """
    query_type = intent.get("query_type", "summary")

    # Determine visualization type based on query type
    visualization_type = "table"  # default
    visualization_config = {}

    if query_type == "trend":
        visualization_type = "line_chart"
        visualization_config = {
            "title": intent.get("title", "Disease Trend"),
            "x_axis": "date",
            "y_axis": "count",
        }
    elif query_type == "comparison":
        visualization_type = "bar_chart"
        visualization_config = {
            "title": intent.get("title", "Comparison"),
            "x_axis": "period",
            "y_axis": "count",
        }
    elif query_type == "geographic":
        visualization_type = "map"
        visualization_config = {
            "title": intent.get("title", "Geographic Distribution"),
            "marker_field": "location",
            "value_field": "count",
        }
    elif query_type == "case_count":
        if len(results) > 1:
            visualization_type = "bar_chart"
            visualization_config = {
                "title": intent.get("title", "Case Counts"),
                "x_axis": "category",
                "y_axis": "count",
            }
        else:
            visualization_type = "stat_card"
            visualization_config = {
                "title": intent.get("title", "Total Cases"),
            }

    return {
        "success": True,
        "query_type": query_type,
        "summary": summary,
        "data": results,
        "total_records": len(results),
        "visualization_type": visualization_type,
        "visualization_config": visualization_config,
        "generated_at": datetime.utcnow().isoformat(),
    }


# =============================================================================
# Query Processing Pipeline
# =============================================================================


async def parse_query_intent(query: str) -> dict:
    """
    Parse a natural language query to extract intent and parameters.

    Uses Claude to classify the query type and extract relevant parameters
    like disease type, location, time range, etc.

    Args:
        query: Natural language query from health officer

    Returns:
        Dict with query_type, parameters, and understanding
    """
    config = get_llm_config("analyst")
    client = get_anthropic_client()

    intent_prompt = f"""Analyze this health data query and extract the intent.

Query: "{query}"

Classify the query into one of these types:
- case_count: Counting cases (e.g., "How many cholera cases this week?")
- trend: Time-based patterns (e.g., "Show me dengue trends")
- comparison: Comparing periods or regions (e.g., "Compare this week vs last week")
- geographic: Location-based analysis (e.g., "Where are the hotspots?")
- timeline: Event timing (e.g., "When did the outbreak start?")
- summary: General overview (e.g., "What's the current situation?")
- threshold_check: Check against MoH thresholds

Extract these parameters if mentioned:
- disease: cholera, dengue, malaria, measles, meningitis, or null if not specified
- location: Location name or null
- time_range_days: Number of days to look back (default 7)
- start_date: Specific start date if mentioned (YYYY-MM-DD)
- end_date: Specific end date if mentioned (YYYY-MM-DD)
- compare_to: "previous_period" or specific comparison target
- urgency_filter: critical, high, medium, low, or null
- status_filter: open, investigating, resolved, or null

Respond with JSON:
```json
{{
  "query_type": "case_count|trend|comparison|geographic|timeline|summary|threshold_check",
  "understanding": "What you understood the user wants",
  "parameters": {{
    "disease": "disease_name or null",
    "location": "location_name or null",
    "time_range_days": 7,
    "start_date": "YYYY-MM-DD or null",
    "end_date": "YYYY-MM-DD or null",
    "compare_to": "previous_period or null",
    "urgency_filter": "level or null",
    "status_filter": "status or null"
  }},
  "title": "Short title for visualization"
}}
```"""

    try:
        response = await client.messages.create(
            model=config.model,
            max_tokens=1000,
            temperature=0.1,
            messages=[{"role": "user", "content": intent_prompt}],
        )

        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

        parsed = extract_json(response_text)
        if parsed is None:
            logger.warning(
                "Failed to parse intent response",
                response_preview=response_text[:200],
            )
            return {
                "query_type": "summary",
                "understanding": query,
                "parameters": {"time_range_days": 7},
                "title": "Query Results",
            }

        return parsed

    except Exception as e:
        logger.error("Error parsing query intent", error=str(e))
        return {
            "query_type": "summary",
            "understanding": query,
            "parameters": {"time_range_days": 7},
            "title": "Query Results",
            "error": str(e),
        }


async def generate_sql(intent: dict) -> tuple[str, dict]:
    """
    Generate a safe, parameterized SQL query from parsed intent.

    Uses Claude to generate SQL based on the schema context and intent,
    then validates the generated query for safety.

    Args:
        intent: Parsed query intent from parse_query_intent()

    Returns:
        Tuple of (sql_query, parameters_dict)

    Raises:
        ValueError: If generated SQL fails validation
    """
    config = get_llm_config("analyst")
    client = get_anthropic_client()

    schema_context = get_schema_context()
    params = intent.get("parameters", {})

    # Build parameter context
    param_context = []
    if params.get("disease"):
        param_context.append(f"Disease: {params['disease']}")
    if params.get("location"):
        param_context.append(f"Location: {params['location']}")
    if params.get("time_range_days"):
        param_context.append(f"Time range: {params['time_range_days']} days")
    if params.get("urgency_filter"):
        param_context.append(f"Urgency: {params['urgency_filter']}")
    if params.get("status_filter"):
        param_context.append(f"Status: {params['status_filter']}")

    sql_prompt = f"""Generate a PostgreSQL SELECT query for this request.

{schema_context}

Query Intent: {intent.get('understanding', '')}
Query Type: {intent.get('query_type', 'summary')}
Parameters: {', '.join(param_context) if param_context else 'None specified'}

Requirements:
1. ONLY use SELECT statements - no modifications
2. Use parameterized queries with :param_name syntax for user inputs
3. Include appropriate WHERE clauses for filtering
4. Add ORDER BY for consistent results
5. Use LIMIT 1000 to prevent huge result sets
6. For time-based queries, use created_at column
7. For counting, use COUNT(*) or SUM(cases_count) as appropriate

Respond with JSON:
```json
{{
  "sql": "SELECT ... FROM reports WHERE ... ORDER BY ... LIMIT ...",
  "params": {{
    "param_name": "value"
  }},
  "explanation": "What this query does"
}}
```"""

    try:
        response = await client.messages.create(
            model=config.model,
            max_tokens=1500,
            temperature=0.1,
            messages=[{"role": "user", "content": sql_prompt}],
        )

        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

        parsed = extract_json(response_text)
        if parsed is None:
            logger.warning(
                "Failed to parse SQL generation response",
                response_preview=response_text[:200],
            )
            raise ValueError("Could not generate SQL query")

        sql = parsed.get("sql", "")
        sql_params = parsed.get("params", {})

        # Validate the generated SQL
        is_valid, error = validate_sql_query(sql)
        if not is_valid:
            logger.warning(
                "Generated SQL failed validation",
                sql_preview=sql[:200],
                error=error,
            )
            raise ValueError(f"Generated SQL is not safe: {error}")

        logger.debug(
            "Generated SQL query",
            sql_preview=sql[:100],
            param_count=len(sql_params),
        )

        return sql, sql_params

    except anthropic.APIError as e:
        logger.error("API error generating SQL", error=str(e))
        raise ValueError(f"Failed to generate SQL: {e}") from e


async def execute_query(
    sql: str,
    params: dict,
    officer_id: UUID | None = None,
) -> list[dict]:
    """
    Execute a validated SQL query with timeout and audit logging.

    Args:
        sql: Validated SQL query string
        params: Query parameters dict
        officer_id: ID of officer making the query (for audit)

    Returns:
        List of result dicts

    Raises:
        asyncio.TimeoutError: If query exceeds timeout
        Exception: For database errors
    """
    from sqlalchemy import text

    from cbi.db.queries import create_audit_log

    logger.debug(
        "Executing analyst query",
        sql_preview=sql[:100],
        param_count=len(params),
    )

    async def _execute():
        async with get_session() as session:
            # Execute the query
            result = await session.execute(text(sql), params)
            rows = result.fetchall()
            columns = result.keys()

            # Convert to list of dicts
            results = [dict(zip(columns, row, strict=True)) for row in rows]

            # Create audit log entry
            if officer_id:
                await create_audit_log(
                    session,
                    entity_type="analyst_query",
                    entity_id=officer_id,
                    action="execute_query",
                    actor_type="officer",
                    actor_id=str(officer_id),
                    changes={
                        "sql_preview": sql[:200],
                        "param_count": len(params),
                        "result_count": len(results),
                    },
                )

            return results

    try:
        # Execute with timeout
        results = await asyncio.wait_for(
            _execute(),
            timeout=QUERY_TIMEOUT_SECONDS,
        )

        logger.info(
            "Query executed successfully",
            result_count=len(results),
        )

        return results

    except TimeoutError:
        logger.error(
            "Query execution timed out",
            timeout_seconds=QUERY_TIMEOUT_SECONDS,
        )
        raise

    except Exception as e:
        logger.error("Query execution failed", error=str(e))
        raise


async def format_results(
    results: list[dict],
    intent: dict,
) -> dict:
    """
    Generate a human-readable summary and format results for visualization.

    Uses Claude to interpret the raw query results and generate insights.

    Args:
        results: Raw query results
        intent: Original query intent

    Returns:
        Formatted response with summary and visualization config
    """
    config = get_llm_config("analyst")
    client = get_anthropic_client()

    # Limit results for LLM context
    results_sample = results[:50] if len(results) > 50 else results

    format_prompt = f"""Analyze these health data query results and provide a summary.

Query Intent: {intent.get('understanding', '')}
Query Type: {intent.get('query_type', 'summary')}
Total Records: {len(results)}

Results (sample):
{json.dumps(results_sample, indent=2, default=str)}

Provide:
1. A clear, concise summary (2-3 sentences) of what the data shows
2. Key insights or findings (bullet points)
3. Any concerning patterns or anomalies
4. Recommendations if applicable

Respond with JSON:
```json
{{
  "summary": "Clear summary of findings",
  "insights": ["Insight 1", "Insight 2"],
  "concerns": ["Concern if any"],
  "recommendations": ["Recommendation if any"],
  "data_quality_notes": "Notes on data completeness or issues"
}}
```"""

    try:
        response = await client.messages.create(
            model=config.model,
            max_tokens=1500,
            temperature=0.2,
            messages=[{"role": "user", "content": format_prompt}],
        )

        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

        parsed = extract_json(response_text)
        summary_text = "Query completed successfully."

        if parsed:
            summary_text = parsed.get("summary", summary_text)
            insights = parsed.get("insights", [])
            if insights:
                summary_text += " " + " ".join(insights[:2])

        # Serialize results for JSON response (handle dates, UUIDs, etc.)
        serialized_results = []
        for row in results:
            serialized_row = {}
            for key, value in row.items():
                if isinstance(value, (datetime, date)):
                    serialized_row[key] = value.isoformat()
                elif isinstance(value, UUID):
                    serialized_row[key] = str(value)
                elif hasattr(value, "value"):  # Enum
                    serialized_row[key] = value.value
                else:
                    serialized_row[key] = value
            serialized_results.append(serialized_row)

        return format_query_response(serialized_results, intent, summary_text)

    except Exception as e:
        logger.error("Error formatting results", error=str(e))
        # Return basic response on error
        return format_query_response(
            results[:100],
            intent,
            f"Retrieved {len(results)} records.",
        )


# =============================================================================
# Main Entry Points
# =============================================================================


async def process_query(
    query: str,
    officer_id: UUID,
    region_filter: str | None = None,
) -> dict:
    """
    Main entry point for natural language database queries.

    Processes a query through the full pipeline:
    1. Parse query intent
    2. Generate SQL
    3. Execute query
    4. Format results

    Args:
        query: Natural language query from health officer
        officer_id: UUID of the officer making the query
        region_filter: Optional region to filter results

    Returns:
        Dict with success status, results, summary, and visualization config
    """
    logger.info(
        "Processing analyst query",
        officer_id=str(officer_id),
        query_preview=query[:100],
    )

    try:
        # Step 1: Parse query intent
        intent = await parse_query_intent(query)
        logger.debug(
            "Parsed query intent",
            query_type=intent.get("query_type"),
            understanding=intent.get("understanding"),
        )

        # Add region filter if specified
        if region_filter:
            intent.setdefault("parameters", {})["location"] = region_filter

        # Step 2: Generate SQL
        sql, params = await generate_sql(intent)

        # Step 3: Execute query
        results = await execute_query(sql, params, officer_id)

        # Step 4: Format results
        response = await format_results(results, intent)
        response["query"] = query
        response["intent"] = intent

        logger.info(
            "Query processing complete",
            officer_id=str(officer_id),
            result_count=len(results),
            query_type=intent.get("query_type"),
        )

        return response

    except ValueError as e:
        logger.warning(
            "Query processing failed - validation error",
            officer_id=str(officer_id),
            error=str(e),
        )
        return {
            "success": False,
            "error": str(e),
            "error_type": "validation_error",
            "query": query,
        }

    except TimeoutError:
        logger.error(
            "Query processing failed - timeout",
            officer_id=str(officer_id),
        )
        return {
            "success": False,
            "error": "Query timed out. Try a more specific query.",
            "error_type": "timeout",
            "query": query,
        }

    except Exception as e:
        logger.exception(
            "Query processing failed - unexpected error",
            officer_id=str(officer_id),
            error=str(e),
        )
        return {
            "success": False,
            "error": "An error occurred processing your query.",
            "error_type": "internal_error",
            "query": query,
        }


async def analyst_node(state: ConversationState) -> ConversationState:
    """
    Analyst Agent LangGraph node.

    Called when the Surveillance Agent triggers it after a threshold is exceeded.
    Generates a situation summary for the notification.

    Args:
        state: ConversationState from the Surveillance Agent

    Returns:
        Updated ConversationState with analyst summary added
    """
    conversation_id = state.get("conversation_id", "unknown")
    classification = state.get("classification", {})
    extracted_data = state.get("extracted_data", {})

    logger.info(
        "Analyst agent generating situation summary",
        conversation_id=conversation_id,
    )

    try:
        # Get context for the summary
        disease = classification.get("suspected_disease", "unknown")
        urgency = classification.get("urgency", "medium")
        alert_type = classification.get("alert_type", "single_case")
        location = extracted_data.get("location_text") or extracted_data.get(
            "location_normalized"
        )

        # Query for related recent cases
        related_data = await _get_situation_context(disease, location)

        # Generate situation summary using LLM
        summary = await _generate_situation_summary(
            disease=disease,
            urgency=urgency,
            alert_type=alert_type,
            location=location,
            extracted_data=extracted_data,
            related_data=related_data,
        )

        # Update state with analyst output
        new_state = dict(state)
        new_state["analyst_summary"] = summary
        new_state["updated_at"] = datetime.utcnow().isoformat()

        logger.info(
            "Analyst agent completed",
            conversation_id=conversation_id,
            summary_length=len(summary.get("summary", "")),
        )

        return ConversationState(**new_state)

    except Exception as e:
        logger.exception(
            "Error in analyst node",
            conversation_id=conversation_id,
            error=str(e),
        )
        # Return state unchanged on error - don't block the pipeline
        new_state = dict(state)
        new_state["analyst_summary"] = {
            "summary": "Situation analysis unavailable.",
            "error": str(e),
        }
        return ConversationState(**new_state)


async def _get_situation_context(
    disease: str,
    location: str | None,
) -> dict:
    """
    Get contextual data for generating a situation summary.

    Queries recent cases of the same disease and in the same area.

    Args:
        disease: Disease type
        location: Location text

    Returns:
        Dict with case counts, trends, and related cases
    """
    from cbi.db.queries import (
        count_reports_by_disease,
        get_case_count_for_area,
        get_detailed_report_stats,
    )

    context = {
        "total_cases_7_days": 0,
        "total_cases_30_days": 0,
        "area_cases_7_days": 0,
        "stats": {},
    }

    try:
        disease_enum = DiseaseType(disease) if disease != "unknown" else None
    except ValueError:
        disease_enum = None

    try:
        async with get_session() as session:
            # Get overall stats
            context["stats"] = await get_detailed_report_stats(session, days=7)

            # Get disease-specific counts
            if disease_enum:
                context["total_cases_7_days"] = await count_reports_by_disease(
                    session, disease_enum, days=7
                )
                context["total_cases_30_days"] = await count_reports_by_disease(
                    session, disease_enum, days=30
                )

            # Get area-specific counts
            if location and disease_enum:
                context["area_cases_7_days"] = await get_case_count_for_area(
                    session,
                    disease=disease_enum,
                    location_text=location,
                    days=7,
                )

    except Exception as e:
        logger.warning("Error getting situation context", error=str(e))

    return context


async def _generate_situation_summary(
    disease: str,
    urgency: str,
    alert_type: str,
    location: str | None,
    extracted_data: dict,
    related_data: dict,
) -> dict:
    """
    Generate a situation summary using Claude.

    Args:
        disease: Suspected disease
        urgency: Urgency level
        alert_type: Alert type
        location: Location text
        extracted_data: Extracted report data
        related_data: Context from database queries

    Returns:
        Dict with summary, recommendations, and alerts
    """
    config = get_llm_config("analyst")
    client = get_anthropic_client()

    summary_prompt = f"""Generate a situation summary for a health alert.

## Current Report
- Suspected Disease: {disease}
- Urgency: {urgency}
- Alert Type: {alert_type}
- Location: {location or 'Unknown'}
- Symptoms: {', '.join(extracted_data.get('symptoms', [])) or 'Not specified'}
- Cases Reported: {extracted_data.get('cases_count', 1)}
- Deaths Reported: {extracted_data.get('deaths_count', 0)}

## Context
- Total {disease} cases in past 7 days: {related_data.get('total_cases_7_days', 0)}
- Total {disease} cases in past 30 days: {related_data.get('total_cases_30_days', 0)}
- Cases in this area (7 days): {related_data.get('area_cases_7_days', 0)}

## Overall Statistics (7 days)
- Total reports: {related_data.get('stats', {}).get('total', 0)}
- Open reports: {related_data.get('stats', {}).get('open', 0)}
- Critical reports: {related_data.get('stats', {}).get('critical', 0)}

Generate a brief but informative summary suitable for a health officer notification.

Respond with JSON:
```json
{{
  "summary": "2-3 sentence situation summary",
  "key_points": ["Point 1", "Point 2"],
  "threshold_status": "Description of any threshold exceedances",
  "recommendations": ["Immediate action 1", "Action 2"],
  "risk_assessment": "low|medium|high|critical"
}}
```"""

    try:
        response = await client.messages.create(
            model=config.model,
            max_tokens=1000,
            temperature=0.2,
            messages=[{"role": "user", "content": summary_prompt}],
        )

        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

        parsed = extract_json(response_text)
        if parsed:
            parsed["generated_at"] = datetime.utcnow().isoformat()
            return parsed

        # Fallback response
        return {
            "summary": f"{urgency.upper()} alert: {disease} case(s) reported in {location or 'unknown location'}.",
            "key_points": [
                f"New {alert_type.replace('_', ' ')} detected",
                f"Urgency level: {urgency}",
            ],
            "recommendations": ["Investigate reported cases", "Monitor for additional cases"],
            "risk_assessment": urgency,
            "generated_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Error generating situation summary", error=str(e))
        return {
            "summary": f"New {disease} alert - {urgency} urgency",
            "error": str(e),
            "generated_at": datetime.utcnow().isoformat(),
        }


# =============================================================================
# Convenience Functions for Common Queries
# =============================================================================


async def get_disease_summary(
    disease: str,
    days: int = 7,
) -> dict:
    """
    Get a summary of cases for a specific disease.

    Args:
        disease: Disease name
        days: Number of days to look back

    Returns:
        Dict with case counts and trend information
    """
    from cbi.db.queries import count_reports_by_disease, get_reports_by_disease

    try:
        disease_enum = DiseaseType(disease)
    except ValueError:
        return {"error": f"Unknown disease: {disease}"}

    try:
        async with get_session() as session:
            count = await count_reports_by_disease(session, disease_enum, days=days)
            recent_reports = await get_reports_by_disease(
                session, disease_enum, days=days, limit=10
            )

            # Calculate trend (compare to previous period)
            previous_count = await count_reports_by_disease(
                session, disease_enum, days=days * 2
            )
            previous_period_count = previous_count - count

            if previous_period_count > 0:
                change_pct = ((count - previous_period_count) / previous_period_count) * 100
                trend = "increasing" if change_pct > 10 else "decreasing" if change_pct < -10 else "stable"
            else:
                trend = "new" if count > 0 else "stable"
                change_pct = 100 if count > 0 else 0

            return {
                "disease": disease,
                "period_days": days,
                "case_count": count,
                "previous_period_count": previous_period_count,
                "trend": trend,
                "change_percentage": round(change_pct, 1),
                "recent_reports": len(recent_reports),
                "locations": list({
                    r.location_normalized or r.location_text
                    for r in recent_reports
                    if r.location_normalized or r.location_text
                }),
            }

    except Exception as e:
        logger.error("Error getting disease summary", error=str(e))
        return {"error": str(e)}


async def get_geographic_hotspots(
    days: int = 7,
    min_cases: int = 3,
) -> list[dict]:
    """
    Identify geographic hotspots with multiple cases.

    Args:
        days: Number of days to look back
        min_cases: Minimum cases to be considered a hotspot

    Returns:
        List of hotspot dicts with location and case info
    """
    from sqlalchemy import text

    sql = """
    SELECT
        COALESCE(location_normalized, location_text) as location,
        suspected_disease,
        COUNT(*) as case_count,
        SUM(COALESCE(cases_count, 1)) as total_affected,
        SUM(COALESCE(deaths_count, 0)) as total_deaths,
        MAX(urgency) as max_urgency
    FROM reports
    WHERE created_at >= NOW() - INTERVAL ':days days'
      AND (location_normalized IS NOT NULL OR location_text IS NOT NULL)
    GROUP BY COALESCE(location_normalized, location_text), suspected_disease
    HAVING COUNT(*) >= :min_cases
    ORDER BY case_count DESC
    LIMIT 20
    """

    try:
        async with get_session() as session:
            result = await session.execute(
                text(sql),
                {"days": days, "min_cases": min_cases},
            )
            rows = result.fetchall()

            hotspots = []
            for row in rows:
                hotspots.append({
                    "location": row[0],
                    "disease": row[1].value if hasattr(row[1], "value") else row[1],
                    "report_count": row[2],
                    "total_affected": row[3],
                    "total_deaths": row[4],
                    "max_urgency": row[5].value if hasattr(row[5], "value") else row[5],
                })

            return hotspots

    except Exception as e:
        logger.error("Error getting geographic hotspots", error=str(e))
        return []


# =============================================================================
# Visualization Types and Prompts
# =============================================================================

VisualizationType = Literal[
    "line_chart",
    "bar_chart",
    "map",
    "heatmap",
    "timeline",
]

# Visualization prompt templates for each chart type
LINE_CHART_PROMPT = """Generate a Recharts LineChart component for the following health data.

Data:
{data}

Requirements:
1. Use Recharts library components (LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer)
2. Include proper axis labels based on the data
3. Add a legend if there are multiple series
4. Use appropriate colors for different lines (use health-related colors: blues for cases, reds for deaths)
5. Make the chart responsive using ResponsiveContainer
6. Format dates nicely on X-axis if date data is present
7. Add tooltips with meaningful labels

Return ONLY the JSX code for the chart component, wrapped in a ResponsiveContainer.
Do not include imports or component definition - just the JSX.

Example format:
```jsx
<ResponsiveContainer width="100%" height={{400}}>
  <LineChart data={{{{data}}}}>
    ...
  </LineChart>
</ResponsiveContainer>
```
"""

BAR_CHART_PROMPT = """Generate a Recharts BarChart component for the following health data.

Data:
{data}

Chart Configuration:
- Type: {chart_variant} (stacked or grouped)
- Title: {title}

Requirements:
1. Use Recharts library components (BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer)
2. Include proper axis labels
3. Add a legend
4. Use health-related colors:
   - Critical: #ef4444 (red)
   - High: #f97316 (orange)
   - Medium: #eab308 (yellow)
   - Low: #22c55e (green)
   - Cases: #3b82f6 (blue)
   - Deaths: #dc2626 (dark red)
5. Make the chart responsive
6. Add tooltips

Return ONLY the JSX code wrapped in ResponsiveContainer.
"""

MAP_PROMPT = """Generate a React Leaflet map component for the following health report data.

Data:
{data}

Requirements:
1. Use React Leaflet components (MapContainer, TileLayer, Marker, Popup, CircleMarker)
2. Center the map on Sudan (approximately lat: 15.5, lng: 32.5)
3. Set appropriate zoom level to show all markers
4. Color code markers by urgency:
   - Critical: red (#ef4444)
   - High: orange (#f97316)
   - Medium: yellow (#eab308)
   - Low: green (#22c55e)
5. Include popup with case details:
   - Location name
   - Disease type
   - Case count
   - Urgency level
6. Use CircleMarker with radius proportional to case count (min 8, max 30)

Return ONLY the JSX code for the map component.
Do not include imports - just the JSX starting with <MapContainer>.

Example format:
```jsx
<MapContainer center={{[15.5, 32.5]}} zoom={{6}} style={{{{ height: '500px', width: '100%' }}}}>
  <TileLayer url="https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png" />
  ...markers...
</MapContainer>
```
"""

HEATMAP_PROMPT = """Generate a geographic heatmap visualization for the following health case density data.

Data:
{data}

Requirements:
1. Use React Leaflet with leaflet.heat plugin
2. Center on Sudan (lat: 15.5, lng: 32.5)
3. Configure heatmap options:
   - radius: 25
   - blur: 15
   - maxZoom: 10
   - gradient: {{ 0.4: 'blue', 0.6: 'lime', 0.8: 'yellow', 1.0: 'red' }}
4. Weight points by case count
5. Include a legend showing the intensity scale

Return ONLY the JSX code for the heatmap component.
"""

TIMELINE_PROMPT = """Generate a timeline visualization showing the progression of health events.

Data:
{data}

Requirements:
1. Use a vertical timeline layout
2. Show events in chronological order
3. Include for each event:
   - Date/time
   - Disease type
   - Location
   - Case count
   - Urgency (with color indicator)
4. Use icons or colored dots to indicate urgency level
5. Make it scrollable if there are many events

Return ONLY the JSX code for the timeline component using Tailwind CSS for styling.
Use div elements with appropriate Tailwind classes - no external timeline library needed.
"""

# Arabic translations for situation summaries
SITUATION_SUMMARY_AR = {
    "overview": "نظرة عامة على الوضع",
    "cases_reported": "الحالات المبلغ عنها",
    "deaths_reported": "الوفيات المبلغ عنها",
    "geographic_spread": "الانتشار الجغرافي",
    "risk_assessment": "تقييم المخاطر",
    "recommendations": "التوصيات",
    "critical": "حرج",
    "high": "مرتفع",
    "medium": "متوسط",
    "low": "منخفض",
    "increasing": "متزايد",
    "decreasing": "متناقص",
    "stable": "مستقر",
}


# =============================================================================
# Visualization Generation Functions
# =============================================================================


async def generate_visualization(
    data: list[dict],
    viz_type: VisualizationType,
    title: str = "Health Data Visualization",
    chart_variant: str = "grouped",
) -> dict:
    """
    Generate visualization code using Claude.

    Calls Claude Sonnet to generate frontend-ready visualization code
    based on the data and visualization type.

    Args:
        data: List of data dictionaries to visualize
        viz_type: Type of visualization (line_chart, bar_chart, map, heatmap, timeline)
        title: Title for the visualization
        chart_variant: For bar charts - 'stacked' or 'grouped'

    Returns:
        Dict with:
        - success: bool
        - code: Generated JSX code string
        - viz_type: The visualization type
        - error: Error message if failed
    """
    logger.info(
        "Generating visualization",
        viz_type=viz_type,
        data_count=len(data),
    )

    # Select appropriate prompt template
    prompt_templates = {
        "line_chart": LINE_CHART_PROMPT,
        "bar_chart": BAR_CHART_PROMPT,
        "map": MAP_PROMPT,
        "heatmap": HEATMAP_PROMPT,
        "timeline": TIMELINE_PROMPT,
    }

    template = prompt_templates.get(viz_type)
    if not template:
        return {
            "success": False,
            "error": f"Unknown visualization type: {viz_type}",
            "viz_type": viz_type,
        }

    # Format data for the prompt
    # Limit data size to avoid token limits
    data_sample = data[:100] if len(data) > 100 else data
    data_str = json.dumps(data_sample, indent=2, default=str)

    # Format the prompt
    prompt = template.format(
        data=data_str,
        title=title,
        chart_variant=chart_variant,
    )

    try:
        config = get_llm_config("analyst")
        client = get_anthropic_client()

        response = await client.messages.create(
            model=config.model,
            max_tokens=2000,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract the code from response
        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

        # Extract JSX code from markdown code blocks if present
        code = response_text
        jsx_match = re.search(r"```(?:jsx|javascript|tsx)?\s*\n?(.*?)\n?```", response_text, re.DOTALL)
        if jsx_match:
            code = jsx_match.group(1).strip()

        logger.info(
            "Visualization generated successfully",
            viz_type=viz_type,
            code_length=len(code),
        )

        return {
            "success": True,
            "code": code,
            "viz_type": viz_type,
            "title": title,
            "data_points": len(data),
        }

    except anthropic.APIError as e:
        logger.error("API error generating visualization", error=str(e))
        return {
            "success": False,
            "error": f"Failed to generate visualization: {e}",
            "viz_type": viz_type,
        }
    except Exception as e:
        logger.exception("Unexpected error generating visualization", error=str(e))
        return {
            "success": False,
            "error": "An error occurred generating the visualization",
            "viz_type": viz_type,
        }


async def generate_chart_config(
    data: list[dict],
    viz_type: VisualizationType,
    title: str = "Health Data",
) -> dict:
    """
    Generate chart configuration without code generation.

    Returns a configuration object that the frontend can use with
    its existing chart components, rather than generating code.

    Args:
        data: List of data dictionaries
        viz_type: Type of visualization
        title: Chart title

    Returns:
        Dict with chart configuration for frontend rendering
    """
    # Determine data structure and create config
    if not data:
        return {
            "type": viz_type,
            "title": title,
            "data": [],
            "config": {},
        }

    # Analyze data to determine appropriate configuration
    sample = data[0]
    keys = list(sample.keys())

    # Common config
    config = {
        "type": viz_type,
        "title": title,
        "data": data,
    }

    if viz_type == "line_chart":
        # Find date/time field for x-axis
        x_axis = next((k for k in keys if "date" in k.lower() or "time" in k.lower()), keys[0])
        # Find numeric fields for y-axis
        y_fields = [k for k in keys if k != x_axis and isinstance(sample.get(k), (int, float))]
        config["config"] = {
            "xAxis": x_axis,
            "yAxis": y_fields[:5],  # Limit to 5 series
            "colors": ["#3b82f6", "#ef4444", "#22c55e", "#f97316", "#8b5cf6"],
        }

    elif viz_type == "bar_chart":
        # Find category field
        category = next((k for k in keys if "disease" in k.lower() or "location" in k.lower() or "name" in k.lower()), keys[0])
        # Find numeric fields
        values = [k for k in keys if k != category and isinstance(sample.get(k), (int, float))]
        config["config"] = {
            "category": category,
            "values": values[:3],
            "colors": {
                "cases_count": "#3b82f6",
                "deaths_count": "#ef4444",
                "report_count": "#22c55e",
            },
        }

    elif viz_type == "map":
        # Find coordinate fields
        lat_field = next((k for k in keys if "lat" in k.lower()), None)
        lon_field = next((k for k in keys if "lon" in k.lower() or "lng" in k.lower()), None)
        config["config"] = {
            "center": [15.5, 32.5],  # Sudan
            "zoom": 6,
            "latField": lat_field,
            "lonField": lon_field,
            "urgencyField": "urgency" if "urgency" in keys else None,
            "labelField": "location" if "location" in keys else keys[0],
        }

    elif viz_type == "heatmap":
        config["config"] = {
            "center": [15.5, 32.5],
            "zoom": 6,
            "weightField": "cases_count" if "cases_count" in keys else "count",
            "radius": 25,
            "blur": 15,
        }

    elif viz_type == "timeline":
        date_field = next((k for k in keys if "date" in k.lower() or "time" in k.lower() or "created" in k.lower()), keys[0])
        config["config"] = {
            "dateField": date_field,
            "titleField": "suspected_disease" if "suspected_disease" in keys else keys[0],
            "descriptionFields": ["location_text", "cases_count", "urgency"],
        }

    return config


async def generate_situation_summary(
    report_id: UUID,
    related_cases: list[dict],
    classification: dict,
    language: str = "en",
) -> dict:
    """
    Generate a comprehensive situation summary for a health report.

    Creates a detailed text summary suitable for notifications to health officers,
    including situation overview, case trends, geographic spread, and recommendations.

    Args:
        report_id: UUID of the primary report
        related_cases: List of related case dicts from find_related_cases
        classification: Classification dict with disease, urgency, alert_type
        language: 'en' for English, 'ar' for Arabic

    Returns:
        Dict with:
        - summary: Main summary text
        - overview: Current situation overview
        - case_stats: Case count and trend information
        - geographic_spread: Affected locations
        - risk_assessment: Risk level and justification
        - recommendations: List of recommended actions
        - language: Language code
        - generated_at: Timestamp
    """
    logger.info(
        "Generating situation summary",
        report_id=str(report_id),
        related_cases_count=len(related_cases),
        language=language,
    )

    # Extract key information
    disease = classification.get("suspected_disease", "unknown")
    urgency = classification.get("urgency", "medium")
    alert_type = classification.get("alert_type", "single_case")
    confidence = classification.get("confidence", 0.0)

    # Calculate statistics from related cases
    total_cases = sum(c.get("cases_count", 1) for c in related_cases) if related_cases else 1
    total_deaths = sum(c.get("deaths_count", 0) for c in related_cases) if related_cases else 0
    locations = list({c.get("location_text", "Unknown") for c in related_cases if c.get("location_text")})

    # Determine trend based on case dates
    trend = "stable"
    if len(related_cases) >= 3:
        # Simple trend: compare first half vs second half
        sorted_cases = sorted(related_cases, key=lambda x: x.get("created_at", datetime.min))
        mid = len(sorted_cases) // 2
        first_half = sum(c.get("cases_count", 1) for c in sorted_cases[:mid])
        second_half = sum(c.get("cases_count", 1) for c in sorted_cases[mid:])
        if second_half > first_half * 1.2:
            trend = "increasing"
        elif second_half < first_half * 0.8:
            trend = "decreasing"

    # Build prompt for LLM
    summary_prompt = f"""Generate a comprehensive situation summary for a health alert.

## Report Details
- Report ID: {report_id}
- Disease: {disease}
- Urgency Level: {urgency}
- Alert Type: {alert_type}
- Classification Confidence: {confidence:.0%}

## Statistics
- Total Cases: {total_cases}
- Total Deaths: {total_deaths}
- Related Reports: {len(related_cases)}
- Affected Locations: {', '.join(locations[:5]) if locations else 'Unknown'}
- Trend: {trend}

## Related Cases (last 5)
{json.dumps(related_cases[:5], indent=2, default=str) if related_cases else 'No related cases'}

Generate a {"comprehensive Arabic" if language == "ar" else "comprehensive English"} situation summary with:
1. **Overview**: 2-3 sentences describing the current situation
2. **Case Statistics**: Key numbers and trends
3. **Geographic Spread**: Where cases are concentrated
4. **Risk Assessment**: Detailed risk evaluation (low/medium/high/critical) with justification
5. **Recommended Actions**: 3-5 specific, actionable recommendations for health officers

{"Respond in Arabic (العربية)." if language == "ar" else "Respond in English."}

Respond with JSON:
```json
{{
  "overview": "Current situation description",
  "case_stats": {{
    "total_cases": {total_cases},
    "total_deaths": {total_deaths},
    "trend": "{trend}",
    "trend_description": "Description of the trend"
  }},
  "geographic_spread": {{
    "affected_locations": ["location1", "location2"],
    "hotspots": "Description of geographic concentration"
  }},
  "risk_assessment": {{
    "level": "{urgency}",
    "justification": "Why this risk level",
    "key_factors": ["factor1", "factor2"]
  }},
  "recommendations": [
    "Specific recommendation 1",
    "Specific recommendation 2"
  ],
  "summary": "Executive summary in 2-3 sentences"
}}
```
"""

    try:
        config = get_llm_config("analyst")
        client = get_anthropic_client()

        response = await client.messages.create(
            model=config.model,
            max_tokens=2000,
            temperature=0.3,
            messages=[{"role": "user", "content": summary_prompt}],
        )

        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

        parsed = extract_json(response_text)

        if parsed:
            parsed["report_id"] = str(report_id)
            parsed["language"] = language
            parsed["generated_at"] = datetime.utcnow().isoformat()
            parsed["related_cases_count"] = len(related_cases)

            logger.info(
                "Situation summary generated",
                report_id=str(report_id),
                summary_length=len(parsed.get("summary", "")),
            )

            return parsed

        # Fallback response if parsing fails
        logger.warning("Failed to parse situation summary response")
        return _create_fallback_summary(
            report_id, disease, urgency, alert_type, total_cases, total_deaths, locations, trend, language
        )

    except Exception as e:
        logger.exception("Error generating situation summary", error=str(e))
        return _create_fallback_summary(
            report_id, disease, urgency, alert_type, total_cases, total_deaths, locations, trend, language
        )


def _create_fallback_summary(
    report_id: UUID,
    disease: str,
    urgency: str,
    alert_type: str,
    total_cases: int,
    total_deaths: int,
    locations: list[str],
    trend: str,
    language: str,
) -> dict:
    """Create a fallback summary when LLM fails."""
    if language == "ar":
        ar = SITUATION_SUMMARY_AR
        summary = f"{ar['overview']}: تم الإبلاغ عن حالات {disease} في {', '.join(locations[:3]) if locations else 'مواقع غير محددة'}."
        overview = f"تنبيه {ar[urgency]}: {total_cases} حالة مبلغ عنها مع {total_deaths} وفاة."
    else:
        summary = f"Situation Overview: {disease.title()} cases reported in {', '.join(locations[:3]) if locations else 'unspecified locations'}."
        overview = f"{urgency.upper()} Alert: {total_cases} cases reported with {total_deaths} deaths."

    return {
        "report_id": str(report_id),
        "summary": summary,
        "overview": overview,
        "case_stats": {
            "total_cases": total_cases,
            "total_deaths": total_deaths,
            "trend": trend,
            "trend_description": f"Cases are {trend}",
        },
        "geographic_spread": {
            "affected_locations": locations[:5],
            "hotspots": locations[0] if locations else "Unknown",
        },
        "risk_assessment": {
            "level": urgency,
            "justification": f"Based on {alert_type.replace('_', ' ')} classification",
            "key_factors": [f"{total_cases} cases", f"{total_deaths} deaths", trend],
        },
        "recommendations": [
            "Investigate reported cases immediately",
            "Coordinate with local health facilities",
            "Monitor for additional cases in the area",
        ],
        "language": language,
        "generated_at": datetime.utcnow().isoformat(),
        "related_cases_count": 0,
    }


async def get_report_situation_summary(
    report_id: UUID,
    language: str = "en",
) -> dict:
    """
    Get or generate a situation summary for a specific report.

    Fetches the report and related cases from the database,
    then generates a comprehensive summary.

    Args:
        report_id: UUID of the report
        language: 'en' or 'ar'

    Returns:
        Situation summary dict
    """
    from cbi.db.queries import get_linked_reports, get_report_by_id

    try:
        async with get_session() as session:
            # Get the report
            report = await get_report_by_id(session, report_id)
            if not report:
                return {
                    "error": f"Report not found: {report_id}",
                    "report_id": str(report_id),
                }

            # Get related cases
            related = await get_linked_reports(session, report_id)

            # Build classification dict from report
            classification = {
                "suspected_disease": (
                    report.suspected_disease.value
                    if hasattr(report.suspected_disease, "value")
                    else report.suspected_disease
                ),
                "urgency": (
                    report.urgency.value
                    if hasattr(report.urgency, "value")
                    else report.urgency
                ),
                "alert_type": (
                    report.alert_type.value
                    if hasattr(report.alert_type, "value")
                    else report.alert_type
                ),
                "confidence": report.confidence_score or 0.0,
            }

            # Generate summary
            return await generate_situation_summary(
                report_id=report_id,
                related_cases=related,
                classification=classification,
                language=language,
            )

    except Exception as e:
        logger.exception("Error getting report situation summary", error=str(e))
        return {
            "error": str(e),
            "report_id": str(report_id),
        }
