"""
Surveillance Agent for CBI.

Classifies health reports by disease type and urgency, checks Ministry of Health
thresholds, links related cases, and persists reports to the database.

Uses Claude Sonnet for superior reasoning in classification tasks.
"""

import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

import anthropic

from cbi.agents.prompts import (
    format_surveillance_prompt,
    validate_surveillance_response,
)
from cbi.agents.reporter import parse_json_response as extract_json
from cbi.agents.state import ConversationState
from cbi.config import get_logger, get_settings
from cbi.config.llm_config import get_llm_config
from cbi.db.models import (
    AlertType,
    DiseaseType,
    LinkType,
    Report,
    UrgencyLevel,
)
from cbi.db.session import get_session

logger = get_logger(__name__)


# =============================================================================
# Ministry of Health Disease Thresholds
# =============================================================================

THRESHOLDS: dict[str, dict[str, Any]] = {
    "cholera": {
        "alert_cases": 1,
        "outbreak_cases": 3,
        "window_days": 7,
        "any_death_is_critical": True,
    },
    "dengue": {
        "alert_cases": 5,
        "outbreak_cases": 20,
        "window_days": 7,
        "any_death_is_critical": True,
    },
    "malaria": {
        "alert_cases": 10,
        "outbreak_cases": 50,
        "window_days": 7,
        "any_death_is_critical": False,
    },
    "measles": {
        "alert_cases": 1,
        "outbreak_cases": 5,
        "window_days": 14,
        "any_death_is_critical": True,
    },
    "meningitis": {
        "alert_cases": 1,
        "outbreak_cases": 3,
        "window_days": 7,
        "any_death_is_critical": True,
    },
    "unknown": {
        "alert_cases": 5,
        "outbreak_cases": 10,
        "window_days": 7,
        "any_death_is_critical": True,
    },
}

# Urgency levels ordered from lowest to highest for comparison
_URGENCY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


# =============================================================================
# Helper Functions
# =============================================================================


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Create and return an async Anthropic client."""
    settings = get_settings()
    return anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
    )


def calculate_urgency(
    classification_data: dict[str, Any],
    total_area_cases: int,
    deaths_reported: int,
) -> str:
    """
    Calculate urgency level based on classification, area case count, and deaths.

    Takes the higher of rule-based urgency and LLM-suggested urgency.

    Priority rules (highest to lowest):
    1. Any death reported -> CRITICAL
    2. Suspected cholera or meningitis -> CRITICAL
    3. Large cluster (10+ cases) -> CRITICAL
    4. Multiple cases (3-9) -> HIGH
    5. Single notifiable disease case -> MEDIUM
    6. Default -> LLM suggestion

    Args:
        classification_data: Classification dict from LLM response
        total_area_cases: Total case count in the geographic area within window
        deaths_reported: Number of deaths reported in this report

    Returns:
        Urgency level string (critical/high/medium/low)
    """
    # Rule-based urgency
    if deaths_reported > 0:
        rule_urgency = "critical"
    elif classification_data.get("suspected_disease") in ("cholera", "meningitis"):
        rule_urgency = "critical"
    elif total_area_cases >= 10:
        rule_urgency = "critical"
    elif total_area_cases >= 3:
        rule_urgency = "high"
    else:
        rule_urgency = "medium"

    # LLM-suggested urgency
    llm_urgency = classification_data.get("urgency", "medium")
    if llm_urgency not in _URGENCY_ORDER:
        llm_urgency = "medium"

    # Return the higher of the two
    if _URGENCY_ORDER.get(rule_urgency, 1) >= _URGENCY_ORDER.get(llm_urgency, 1):
        return rule_urgency
    return llm_urgency


def check_thresholds(
    disease: str,
    total_area_cases: int,
    deaths_count: int,
) -> dict[str, Any]:
    """
    Check Ministry of Health thresholds for a disease.

    Args:
        disease: Disease type string
        total_area_cases: Current case count in area (including this report)
        deaths_count: Deaths reported in this report

    Returns:
        Dict with exceeded (bool), alert_type (str), threshold_detail (str)
    """
    threshold = THRESHOLDS.get(disease, THRESHOLDS["unknown"])

    if total_area_cases >= threshold["outbreak_cases"]:
        return {
            "exceeded": True,
            "alert_type": "suspected_outbreak",
            "threshold_detail": (
                f"Outbreak threshold exceeded: {total_area_cases} cases "
                f"(threshold: {threshold['outbreak_cases']}) within "
                f"{threshold['window_days']} days"
            ),
        }

    if deaths_count > 0 and threshold["any_death_is_critical"]:
        return {
            "exceeded": True,
            "alert_type": "suspected_outbreak",
            "threshold_detail": (
                f"Death reported for {disease} - immediate alert triggered"
            ),
        }

    if total_area_cases >= threshold["alert_cases"]:
        return {
            "exceeded": True,
            "alert_type": "cluster",
            "threshold_detail": (
                f"Alert threshold reached: {total_area_cases} cases "
                f"(threshold: {threshold['alert_cases']}) within "
                f"{threshold['window_days']} days"
            ),
        }

    return {
        "exceeded": False,
        "alert_type": "single_case",
        "threshold_detail": f"Below alert threshold for {disease}",
    }


def _determine_link_type(
    current_symptoms: list[str],
    current_location: str | None,
    related_report: Report,
) -> LinkType:
    """
    Determine the strongest link type between the current report and a related one.

    Args:
        current_symptoms: Symptoms from the current report
        current_location: Location text from the current report
        related_report: The related Report object

    Returns:
        LinkType enum value
    """
    # Check geographic match
    if current_location and related_report.location_normalized:
        if current_location.lower() in related_report.location_normalized.lower():
            return LinkType.geographic
    if current_location and related_report.location_text:
        if current_location.lower() in related_report.location_text.lower():
            return LinkType.geographic

    # Check symptom overlap
    if current_symptoms and related_report.symptoms:
        overlap = set(current_symptoms) & set(related_report.symptoms)
        if overlap:
            return LinkType.symptom

    # Default to temporal (related cases are in the same time window by query design)
    return LinkType.temporal


def _parse_onset_date(value: Any) -> date | None:
    """
    Safely parse an onset date from various formats.

    Args:
        value: Date value (str, date, or None)

    Returns:
        Parsed date or None
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


# =============================================================================
# Main Surveillance Node
# =============================================================================


async def surveillance_node(state: ConversationState) -> ConversationState:
    """
    Surveillance Agent LangGraph node.

    Classifies health reports, checks disease thresholds, links related cases,
    and persists reports to the database.

    Args:
        state: ConversationState from the completed Reporter Agent conversation

    Returns:
        Updated ConversationState with classification data populated
    """
    conversation_id = state.get("conversation_id", "unknown")
    extracted_data = state.get("extracted_data", {})
    messages = state.get("messages", [])
    platform = state.get("platform", "telegram")

    # Convert Pydantic model to dict if needed for JSON serialization
    if hasattr(extracted_data, "model_dump"):
        extracted_data = extracted_data.model_dump()

    logger.info(
        "Surveillance agent processing report",
        conversation_id=conversation_id,
    )

    try:
        # -----------------------------------------------------------------
        # Step 1: Call Claude Sonnet for classification
        # -----------------------------------------------------------------
        config = get_llm_config("surveillance")
        client = get_anthropic_client()

        system_prompt = format_surveillance_prompt(extracted_data)
        report_summary = json.dumps(extracted_data, ensure_ascii=False, default=str)

        logger.debug(
            "Calling Claude API for classification",
            conversation_id=conversation_id,
            model=config.model,
        )

        response = await client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"Classify this health report:\n{report_summary}",
                }
            ],
        )

        # Extract response text
        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

        logger.debug(
            "Received surveillance classification response",
            conversation_id=conversation_id,
            response_length=len(response_text),
        )

        # -----------------------------------------------------------------
        # Step 2: Parse and validate response
        # -----------------------------------------------------------------
        parsed = extract_json(response_text)

        if parsed is None:
            logger.warning(
                "Failed to parse surveillance response",
                conversation_id=conversation_id,
                response_preview=response_text[:200],
            )
            parsed = {
                "suspected_disease": "unknown",
                "confidence": 0.0,
                "urgency": "medium",
                "alert_type": "single_case",
                "reasoning": "Failed to parse LLM classification response",
                "recommended_actions": ["Manual review required"],
                "follow_up_questions": [],
            }
        else:
            is_valid, errors = validate_surveillance_response(parsed)
            if not is_valid:
                logger.warning(
                    "Surveillance response validation issues",
                    conversation_id=conversation_id,
                    errors=errors,
                )

        # -----------------------------------------------------------------
        # Step 3: Database operations (non-fatal on failure)
        # -----------------------------------------------------------------
        report_id: UUID | None = None
        related_cases: list[Report] = []
        total_area_cases = 0
        threshold_result: dict[str, Any] = {
            "exceeded": False,
            "alert_type": "single_case",
            "threshold_detail": "",
        }

        disease_str = parsed.get("suspected_disease", "unknown")
        deaths = extracted_data.get("deaths_count", 0) or 0
        location_text = extracted_data.get("location_text")
        location_coords = extracted_data.get("location_coords")
        lat = location_coords[0] if location_coords else None
        lon = location_coords[1] if location_coords else None
        symptoms = extracted_data.get("symptoms", [])

        try:
            from cbi.db.queries import (
                create_report,
                find_related_cases,
                get_case_count_for_area,
                link_reports,
            )

            async with get_session() as session:
                # 3a. Find related cases
                try:
                    disease_enum = DiseaseType(disease_str)
                except ValueError:
                    disease_enum = DiseaseType.unknown

                related_cases = await find_related_cases(
                    session,
                    suspected_disease=(
                        disease_enum
                        if disease_enum != DiseaseType.unknown
                        else None
                    ),
                    location_text=location_text,
                    location_lat=lat,
                    location_lon=lon,
                    symptoms=symptoms,
                )

                logger.debug(
                    "Found related cases",
                    conversation_id=conversation_id,
                    related_count=len(related_cases),
                )

                # 3b. Get area case count for threshold checking
                total_area_cases = await get_case_count_for_area(
                    session,
                    disease=disease_enum,
                    location_text=location_text,
                    location_lat=lat,
                    location_lon=lon,
                    days=THRESHOLDS.get(
                        disease_str, THRESHOLDS["unknown"]
                    )["window_days"],
                )

                # 3c. Check thresholds (include current report in count)
                threshold_result = check_thresholds(
                    disease_str, total_area_cases + 1, deaths
                )

                # 3d. Calculate final urgency
                final_urgency = calculate_urgency(
                    parsed, total_area_cases + 1, deaths
                )

                # Override alert_type if threshold exceeded
                if threshold_result["exceeded"]:
                    parsed["alert_type"] = threshold_result["alert_type"]
                    if threshold_result.get("threshold_detail"):
                        existing_reasoning = parsed.get("reasoning", "")
                        parsed["reasoning"] = (
                            f"{existing_reasoning} | "
                            f"THRESHOLD: {threshold_result['threshold_detail']}"
                        )

                parsed["urgency"] = final_urgency

                # 3e. Create the report in the database
                location_wkt = None
                if lat is not None and lon is not None:
                    location_wkt = f"SRID=4326;POINT({lon} {lat})"

                reporter_relation = None
                relation_str = extracted_data.get("reporter_relationship")
                if relation_str:
                    try:
                        from cbi.db.models import ReporterRelation

                        reporter_relation = ReporterRelation(relation_str)
                    except ValueError:
                        pass

                report = await create_report(
                    session,
                    conversation_id=conversation_id,
                    symptoms=symptoms or [],
                    suspected_disease=disease_enum,
                    reporter_relation=reporter_relation,
                    location_text=location_text,
                    location_normalized=extracted_data.get(
                        "location_normalized"
                    ),
                    location_point_wkt=location_wkt,
                    onset_text=extracted_data.get("onset_text"),
                    onset_date=_parse_onset_date(
                        extracted_data.get("onset_date")
                    ),
                    cases_count=extracted_data.get("cases_count") or 1,
                    deaths_count=deaths,
                    affected_groups=extracted_data.get(
                        "affected_description"
                    ),
                    urgency=UrgencyLevel(final_urgency),
                    alert_type=AlertType(
                        parsed.get("alert_type", "single_case")
                    ),
                    data_completeness=state.get("classification", {}).get(
                        "data_completeness", 0.0
                    ),
                    confidence_score=parsed.get("confidence"),
                    raw_conversation=messages,
                    extracted_entities=extracted_data,
                    source=platform,
                )
                report_id = report.id

                # 3f. Link related cases
                for related in related_cases:
                    link_type = _determine_link_type(
                        symptoms, location_text, related
                    )
                    await link_reports(
                        session,
                        report_id_1=report_id,
                        report_id_2=related.id,
                        link_type=link_type,
                        confidence=0.7,
                        metadata={
                            "auto_linked": True,
                            "agent": "surveillance",
                        },
                    )

                logger.info(
                    "Report persisted to database",
                    conversation_id=conversation_id,
                    report_id=str(report_id),
                    related_cases_linked=len(related_cases),
                    total_area_cases=total_area_cases,
                    threshold_exceeded=threshold_result["exceeded"],
                )

        except Exception as e:
            logger.error(
                "Database error in surveillance agent",
                conversation_id=conversation_id,
                error=str(e),
            )
            # Don't fail the pipeline - classification still updates state
            # Apply threshold check with what we have
            threshold_result = check_thresholds(disease_str, 1, deaths)
            final_urgency = calculate_urgency(parsed, 1, deaths)
            parsed["urgency"] = final_urgency
            if threshold_result["exceeded"]:
                parsed["alert_type"] = threshold_result["alert_type"]

        # -----------------------------------------------------------------
        # Step 4: Build classification and update state
        # -----------------------------------------------------------------
        classification = {
            "suspected_disease": parsed.get("suspected_disease", "unknown"),
            "confidence": parsed.get("confidence", 0.0),
            "data_completeness": state.get("classification", {}).get(
                "data_completeness", 0.0
            ),
            "urgency": parsed.get("urgency", "medium"),
            "alert_type": parsed.get("alert_type", "single_case"),
            "reasoning": parsed.get("reasoning"),
            "recommended_actions": parsed.get("recommended_actions", []),
            "follow_up_questions": parsed.get("follow_up_questions", []),
        }

        new_state = dict(state)
        new_state["classification"] = classification
        new_state["updated_at"] = datetime.utcnow().isoformat()

        logger.info(
            "Surveillance agent completed",
            conversation_id=conversation_id,
            urgency=classification["urgency"],
            alert_type=classification["alert_type"],
            suspected_disease=classification["suspected_disease"],
            confidence=classification["confidence"],
            report_id=str(report_id) if report_id else None,
            related_cases=len(related_cases),
            threshold_exceeded=threshold_result.get("exceeded", False),
        )

        return ConversationState(**new_state)

    except anthropic.APIConnectionError as e:
        logger.error(
            "Surveillance API connection error",
            conversation_id=conversation_id,
            error=str(e),
        )
        return _handle_surveillance_error(state, "connection_error")

    except anthropic.RateLimitError as e:
        logger.error(
            "Surveillance rate limit exceeded",
            conversation_id=conversation_id,
            error=str(e),
        )
        return _handle_surveillance_error(state, "rate_limit")

    except anthropic.APIStatusError as e:
        logger.error(
            "Surveillance API status error",
            conversation_id=conversation_id,
            status_code=e.status_code,
            error=str(e),
        )
        return _handle_surveillance_error(state, "api_error")

    except Exception as e:
        logger.exception(
            "Unexpected error in surveillance agent",
            conversation_id=conversation_id,
            error=str(e),
        )
        return _handle_surveillance_error(state, "unexpected_error")


def _handle_surveillance_error(
    state: ConversationState,
    error_type: str,
) -> ConversationState:
    """
    Handle surveillance errors gracefully.

    Unlike reporter errors, surveillance errors don't send messages to users.
    Instead, they set a default medium-urgency classification so the pipeline
    continues and a notification is still created for manual review.

    Args:
        state: Current conversation state
        error_type: Type of error that occurred

    Returns:
        Updated state with default classification (NOT error state)
    """
    classification = dict(state.get("classification", {}))
    classification["urgency"] = "medium"
    classification["alert_type"] = "single_case"
    classification["suspected_disease"] = "unknown"
    classification["reasoning"] = (
        f"Classification failed: {error_type}. Manual review required."
    )
    classification["recommended_actions"] = [
        "Manual review required - automated classification failed"
    ]

    new_state = dict(state)
    new_state["classification"] = classification
    new_state["updated_at"] = datetime.utcnow().isoformat()

    logger.warning(
        "Surveillance agent returning default classification due to error",
        conversation_id=state.get("conversation_id", "unknown"),
        error_type=error_type,
    )

    return ConversationState(**new_state)
