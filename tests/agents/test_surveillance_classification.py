"""
Tests for Surveillance Agent classification, urgency, thresholds, and case linking.

Tests the pure functions (calculate_urgency, check_thresholds, _determine_link_type)
directly, and tests the full surveillance_node with mocked LLM and DB.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from cbi.agents.surveillance import (
    THRESHOLDS,
    _determine_link_type,
    _parse_onset_date,
    calculate_urgency,
    check_thresholds,
    surveillance_node,
)
from cbi.agents.state import (
    ConversationMode,
    ConversationState,
)
from cbi.db.models import LinkType

from .conftest import (
    create_mock_anthropic_response,
    make_surveillance_response,
)


# =============================================================================
# calculate_urgency — pure function tests
# =============================================================================


class TestCalculateUrgency:
    """Tests for urgency calculation rules."""

    def test_any_death_is_critical(self):
        """Any reported death should result in CRITICAL urgency."""
        result = calculate_urgency(
            {"suspected_disease": "unknown", "urgency": "low"},
            total_area_cases=1,
            deaths_reported=1,
        )
        assert result == "critical"

    def test_multiple_deaths_critical(self):
        """Multiple deaths should be CRITICAL."""
        result = calculate_urgency(
            {"suspected_disease": "unknown", "urgency": "medium"},
            total_area_cases=5,
            deaths_reported=3,
        )
        assert result == "critical"

    def test_cholera_always_critical(self):
        """Suspected cholera should be CRITICAL even without deaths."""
        result = calculate_urgency(
            {"suspected_disease": "cholera", "urgency": "medium"},
            total_area_cases=1,
            deaths_reported=0,
        )
        assert result == "critical"

    def test_meningitis_always_critical(self):
        """Suspected meningitis should be CRITICAL."""
        result = calculate_urgency(
            {"suspected_disease": "meningitis", "urgency": "low"},
            total_area_cases=1,
            deaths_reported=0,
        )
        assert result == "critical"

    def test_large_cluster_critical(self):
        """10+ cases in area should be CRITICAL."""
        result = calculate_urgency(
            {"suspected_disease": "unknown", "urgency": "medium"},
            total_area_cases=12,
            deaths_reported=0,
        )
        assert result == "critical"

    def test_multiple_cases_high(self):
        """3-9 cases should be HIGH urgency."""
        result = calculate_urgency(
            {"suspected_disease": "malaria", "urgency": "low"},
            total_area_cases=5,
            deaths_reported=0,
        )
        assert result == "high"

    def test_three_cases_exactly_high(self):
        """Exactly 3 cases should be HIGH."""
        result = calculate_urgency(
            {"suspected_disease": "dengue", "urgency": "low"},
            total_area_cases=3,
            deaths_reported=0,
        )
        assert result == "high"

    def test_single_case_medium(self):
        """Single case of common disease should be MEDIUM."""
        result = calculate_urgency(
            {"suspected_disease": "malaria", "urgency": "low"},
            total_area_cases=1,
            deaths_reported=0,
        )
        assert result == "medium"

    def test_llm_urgency_respected_when_higher(self):
        """LLM-suggested urgency should be used if higher than rule-based."""
        result = calculate_urgency(
            {"suspected_disease": "malaria", "urgency": "high"},
            total_area_cases=1,
            deaths_reported=0,
        )
        assert result == "high"

    def test_rule_based_overrides_llm_when_higher(self):
        """Rule-based urgency should override LLM when higher."""
        result = calculate_urgency(
            {"suspected_disease": "cholera", "urgency": "low"},
            total_area_cases=1,
            deaths_reported=0,
        )
        assert result == "critical"

    def test_invalid_llm_urgency_defaults_medium(self):
        """Invalid LLM urgency should be treated as medium."""
        result = calculate_urgency(
            {"suspected_disease": "malaria", "urgency": "invalid_urgency"},
            total_area_cases=1,
            deaths_reported=0,
        )
        assert result == "medium"

    def test_zero_deaths_no_critical_upgrade(self):
        """Zero deaths should not trigger critical from death rule."""
        result = calculate_urgency(
            {"suspected_disease": "malaria", "urgency": "low"},
            total_area_cases=2,
            deaths_reported=0,
        )
        assert result == "medium"

    def test_nine_cases_still_high(self):
        """9 cases should still be HIGH (not CRITICAL)."""
        result = calculate_urgency(
            {"suspected_disease": "unknown", "urgency": "low"},
            total_area_cases=9,
            deaths_reported=0,
        )
        assert result == "high"

    def test_ten_cases_is_critical(self):
        """Exactly 10 cases should be CRITICAL."""
        result = calculate_urgency(
            {"suspected_disease": "unknown", "urgency": "low"},
            total_area_cases=10,
            deaths_reported=0,
        )
        assert result == "critical"


# =============================================================================
# check_thresholds — pure function tests
# =============================================================================


class TestCheckThresholds:
    """Tests for MoH threshold checking."""

    def test_cholera_one_case_triggers_alert(self):
        """Single cholera case should trigger alert."""
        result = check_thresholds("cholera", total_area_cases=1, deaths_count=0)
        assert result["exceeded"] is True
        assert result["alert_type"] == "cluster"

    def test_cholera_three_cases_outbreak(self):
        """3+ cholera cases should trigger outbreak threshold."""
        result = check_thresholds("cholera", total_area_cases=3, deaths_count=0)
        assert result["exceeded"] is True
        assert result["alert_type"] == "suspected_outbreak"

    def test_cholera_death_triggers_outbreak(self):
        """Cholera death should trigger outbreak regardless of count."""
        result = check_thresholds("cholera", total_area_cases=1, deaths_count=1)
        assert result["exceeded"] is True
        assert result["alert_type"] == "suspected_outbreak"

    def test_dengue_below_alert_threshold(self):
        """4 dengue cases (below 5) should not trigger alert."""
        result = check_thresholds("dengue", total_area_cases=4, deaths_count=0)
        assert result["exceeded"] is False
        assert result["alert_type"] == "single_case"

    def test_dengue_at_alert_threshold(self):
        """5 dengue cases should trigger alert."""
        result = check_thresholds("dengue", total_area_cases=5, deaths_count=0)
        assert result["exceeded"] is True
        assert result["alert_type"] == "cluster"

    def test_dengue_outbreak_threshold(self):
        """20+ dengue cases should trigger outbreak."""
        result = check_thresholds("dengue", total_area_cases=20, deaths_count=0)
        assert result["exceeded"] is True
        assert result["alert_type"] == "suspected_outbreak"

    def test_measles_one_case_alert(self):
        """Single measles case should trigger alert."""
        result = check_thresholds("measles", total_area_cases=1, deaths_count=0)
        assert result["exceeded"] is True
        assert result["alert_type"] == "cluster"

    def test_meningitis_one_case_alert(self):
        """Single meningitis case should trigger alert."""
        result = check_thresholds("meningitis", total_area_cases=1, deaths_count=0)
        assert result["exceeded"] is True

    def test_malaria_below_threshold(self):
        """9 malaria cases (below 10) should not trigger alert."""
        result = check_thresholds("malaria", total_area_cases=9, deaths_count=0)
        assert result["exceeded"] is False

    def test_malaria_at_alert_threshold(self):
        """10 malaria cases should trigger alert."""
        result = check_thresholds("malaria", total_area_cases=10, deaths_count=0)
        assert result["exceeded"] is True

    def test_unknown_disease_uses_default(self):
        """Unknown disease should use default thresholds."""
        result = check_thresholds("unknown", total_area_cases=5, deaths_count=0)
        assert result["exceeded"] is True  # Default alert is 5

    def test_unknown_disease_below_threshold(self):
        """4 unknown cases (below 5) should not trigger."""
        result = check_thresholds("unknown", total_area_cases=4, deaths_count=0)
        assert result["exceeded"] is False

    def test_death_critical_for_all_except_malaria(self):
        """Death should be critical for cholera/dengue/measles/meningitis but not malaria."""
        for disease in ["cholera", "dengue", "measles", "meningitis"]:
            result = check_thresholds(disease, total_area_cases=1, deaths_count=1)
            assert result["exceeded"] is True, f"Death should trigger alert for {disease}"

        # Malaria: death alone doesn't trigger (any_death_is_critical=False)
        result = check_thresholds("malaria", total_area_cases=1, deaths_count=1)
        assert result["exceeded"] is False

    def test_threshold_detail_message(self):
        """Threshold result should include descriptive detail message."""
        result = check_thresholds("cholera", total_area_cases=5, deaths_count=0)
        assert "threshold" in result["threshold_detail"].lower() or "cases" in result["threshold_detail"].lower()

    def test_nonexistent_disease_uses_unknown_thresholds(self):
        """Unrecognized disease name should use 'unknown' thresholds."""
        result = check_thresholds("ebola", total_area_cases=5, deaths_count=0)
        assert result["exceeded"] is True  # unknown threshold: alert at 5


# =============================================================================
# _determine_link_type — pure function tests
# =============================================================================


class TestDetermineLinkType:
    """Tests for case linking logic."""

    def test_geographic_link_when_location_matches(self):
        """Cases in the same location should be linked geographically."""
        result = _determine_link_type(
            current_symptoms=["fever"],
            current_location="Kassala",
            related_case={"location_text": "Kassala market area", "symptoms": []},
        )
        assert result == LinkType.geographic

    def test_symptom_link_when_symptoms_overlap(self):
        """Cases sharing symptoms should be linked by symptom."""
        result = _determine_link_type(
            current_symptoms=["fever", "vomiting"],
            current_location="Port Sudan",
            related_case={
                "location_text": "Omdurman",
                "symptoms": ["vomiting", "diarrhea"],
            },
        )
        assert result == LinkType.symptom

    def test_temporal_link_fallback(self):
        """Cases without geographic or symptom overlap link temporally."""
        result = _determine_link_type(
            current_symptoms=["headache"],
            current_location="Khartoum",
            related_case={
                "location_text": "Nyala",
                "symptoms": ["rash"],
            },
        )
        assert result == LinkType.temporal

    def test_geographic_preferred_over_symptom(self):
        """Geographic link should be preferred when both match."""
        result = _determine_link_type(
            current_symptoms=["fever", "vomiting"],
            current_location="Kassala",
            related_case={
                "location_text": "Kassala",
                "symptoms": ["fever"],
            },
        )
        assert result == LinkType.geographic

    def test_no_location_falls_to_symptom(self):
        """Without location data, should check symptom overlap."""
        result = _determine_link_type(
            current_symptoms=["fever"],
            current_location=None,
            related_case={"location_text": "Kassala", "symptoms": ["fever"]},
        )
        assert result == LinkType.symptom

    def test_empty_symptoms_falls_to_temporal(self):
        """Without symptoms or location match, should default to temporal."""
        result = _determine_link_type(
            current_symptoms=[],
            current_location=None,
            related_case={"location_text": "", "symptoms": []},
        )
        assert result == LinkType.temporal


# =============================================================================
# _parse_onset_date — pure function tests
# =============================================================================


class TestParseOnsetDate:
    """Tests for onset date parsing."""

    def test_none_returns_none(self):
        assert _parse_onset_date(None) is None

    def test_date_object_passthrough(self):
        from datetime import date
        d = date(2024, 6, 15)
        assert _parse_onset_date(d) == d

    def test_valid_iso_string(self):
        from datetime import date
        assert _parse_onset_date("2024-06-15") == date(2024, 6, 15)

    def test_invalid_string_returns_none(self):
        assert _parse_onset_date("yesterday") is None

    def test_non_string_non_date_returns_none(self):
        assert _parse_onset_date(12345) is None


# =============================================================================
# surveillance_node — full node tests with mocked LLM + DB
# =============================================================================


@pytest.fixture
def mock_db_session():
    """Mock database session context manager."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_db_queries():
    """Mock all database query functions used by surveillance."""
    with patch("cbi.agents.surveillance.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("cbi.agents.surveillance.find_related_cases", new_callable=AsyncMock) as mock_find, \
             patch("cbi.agents.surveillance.get_case_count_for_area", new_callable=AsyncMock) as mock_count, \
             patch("cbi.agents.surveillance.create_report_from_state", new_callable=AsyncMock) as mock_create, \
             patch("cbi.agents.surveillance.link_reports", new_callable=AsyncMock) as mock_link:
            # Need to import these at the module level in surveillance
            # Actually they're imported inside the try block — let's mock at the queries module level
            yield {
                "session": mock_session,
                "find_related_cases": mock_find,
                "get_case_count_for_area": mock_count,
                "create_report_from_state": mock_create,
                "link_reports": mock_link,
            }


@pytest.mark.asyncio
async def test_surveillance_classifies_cholera(
    patch_surveillance_client,
    complete_state,
):
    """Surveillance correctly classifies cholera-like symptoms."""
    mock_response = make_surveillance_response(
        suspected_disease="cholera",
        confidence=0.85,
        urgency="critical",
        alert_type="suspected_outbreak",
        reasoning="Watery diarrhea and vomiting with deaths - classic cholera presentation",
    )
    patch_surveillance_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response)
    )

    # Mock DB operations to avoid real database calls
    with patch("cbi.agents.surveillance.get_session") as mock_gs:
        mock_gs.side_effect = RuntimeError("DB not initialized")

        result = await surveillance_node(complete_state)

    classification = result["classification"]
    assert classification["suspected_disease"] == "cholera"
    assert classification["confidence"] == 0.85
    # With deaths reported, urgency should be critical
    assert classification["urgency"] == "critical"


@pytest.mark.asyncio
async def test_surveillance_classifies_dengue(
    patch_surveillance_client,
):
    """Surveillance correctly classifies dengue-like symptoms."""
    from cbi.agents.state import create_initial_state, Platform

    state = create_initial_state("conv_dengue_test", "12345", Platform.telegram)
    new = dict(state)
    new["current_mode"] = ConversationMode.complete.value
    new["handoff_to"] = "surveillance"
    new["extracted_data"] = {
        "symptoms": ["high fever", "headache", "joint pain", "rash"],
        "suspected_disease": "dengue",
        "location_text": "Port Sudan",
        "onset_text": "3 days ago",
        "cases_count": 1,
        "deaths_count": 0,
        "location_normalized": None,
        "location_coords": None,
        "onset_date": None,
        "affected_description": None,
        "reporter_relationship": "self",
    }
    state = ConversationState(**new)

    mock_response = make_surveillance_response(
        suspected_disease="dengue",
        confidence=0.75,
        urgency="medium",
        alert_type="single_case",
    )
    patch_surveillance_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response)
    )

    with patch("cbi.agents.surveillance.get_session") as mock_gs:
        mock_gs.side_effect = RuntimeError("DB not initialized")

        result = await surveillance_node(state)

    assert result["classification"]["suspected_disease"] == "dengue"


@pytest.mark.asyncio
async def test_surveillance_unknown_disease(
    patch_surveillance_client,
):
    """Surveillance handles unclear symptoms as 'unknown'."""
    from cbi.agents.state import create_initial_state, Platform

    state = create_initial_state("conv_unknown_test", "12345", Platform.telegram)
    new = dict(state)
    new["current_mode"] = ConversationMode.complete.value
    new["handoff_to"] = "surveillance"
    new["extracted_data"] = {
        "symptoms": ["feeling unwell"],
        "suspected_disease": "unknown",
        "location_text": "my area",
        "onset_text": "recently",
        "cases_count": 1,
        "deaths_count": 0,
        "location_normalized": None,
        "location_coords": None,
        "onset_date": None,
        "affected_description": None,
        "reporter_relationship": None,
    }
    state = ConversationState(**new)

    mock_response = make_surveillance_response(
        suspected_disease="unknown",
        confidence=0.2,
        urgency="low",
        alert_type="rumor",
    )
    patch_surveillance_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response)
    )

    with patch("cbi.agents.surveillance.get_session") as mock_gs:
        mock_gs.side_effect = RuntimeError("DB not initialized")

        result = await surveillance_node(state)

    assert result["classification"]["suspected_disease"] == "unknown"
    assert result["classification"]["confidence"] == 0.2


@pytest.mark.asyncio
async def test_surveillance_deaths_override_urgency(
    patch_surveillance_client,
    complete_state,
):
    """Deaths in report should override LLM urgency to critical."""
    # LLM says "medium" but deaths reported → should be critical
    mock_response = make_surveillance_response(
        suspected_disease="unknown",
        confidence=0.3,
        urgency="medium",
        alert_type="single_case",
    )
    patch_surveillance_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response)
    )

    with patch("cbi.agents.surveillance.get_session") as mock_gs:
        mock_gs.side_effect = RuntimeError("DB not initialized")

        result = await surveillance_node(complete_state)

    # complete_state has deaths_count=2, so urgency should be critical
    assert result["classification"]["urgency"] == "critical"


@pytest.mark.asyncio
async def test_surveillance_handles_api_error(
    patch_surveillance_client,
    complete_state,
):
    """Surveillance handles API errors gracefully with default classification."""
    import anthropic

    patch_surveillance_client.messages.create.side_effect = (
        anthropic.APIConnectionError(request=None)
    )

    result = await surveillance_node(complete_state)

    # Should return default classification, not crash
    classification = result["classification"]
    assert classification["urgency"] == "medium"
    assert classification["suspected_disease"] == "unknown"
    assert "failed" in classification.get("reasoning", "").lower() or "error" in classification.get("reasoning", "").lower()


@pytest.mark.asyncio
async def test_surveillance_handles_unparseable_llm(
    patch_surveillance_client,
    complete_state,
):
    """Surveillance handles non-JSON LLM response with fallback."""
    patch_surveillance_client.messages.create.return_value = (
        create_mock_anthropic_response("I can't classify this report properly.")
    )

    with patch("cbi.agents.surveillance.get_session") as mock_gs:
        mock_gs.side_effect = RuntimeError("DB not initialized")

        result = await surveillance_node(complete_state)

    # Should use fallback classification
    classification = result["classification"]
    assert classification["suspected_disease"] == "unknown"
    assert "reasoning" in classification


# =============================================================================
# Threshold configuration validation
# =============================================================================


class TestThresholdConfig:
    """Validate threshold configuration is correct."""

    def test_all_required_diseases_configured(self):
        """All expected diseases should have thresholds."""
        expected = {"cholera", "dengue", "malaria", "measles", "meningitis", "unknown"}
        assert set(THRESHOLDS.keys()) == expected

    def test_all_thresholds_have_required_keys(self):
        """Each threshold config should have all required fields."""
        required_keys = {"alert_cases", "outbreak_cases", "window_days", "any_death_is_critical"}
        for disease, config in THRESHOLDS.items():
            for key in required_keys:
                assert key in config, f"Missing {key} in threshold for {disease}"

    def test_outbreak_greater_than_alert(self):
        """Outbreak threshold should always be >= alert threshold."""
        for disease, config in THRESHOLDS.items():
            assert config["outbreak_cases"] >= config["alert_cases"], (
                f"Outbreak threshold < alert threshold for {disease}"
            )

    def test_window_days_positive(self):
        """All window_days should be positive."""
        for disease, config in THRESHOLDS.items():
            assert config["window_days"] > 0, f"Non-positive window_days for {disease}"

    def test_cholera_alert_is_one(self):
        """Cholera alert threshold must be 1 (per MoH)."""
        assert THRESHOLDS["cholera"]["alert_cases"] == 1

    def test_cholera_death_is_critical(self):
        """Cholera deaths must be flagged as critical."""
        assert THRESHOLDS["cholera"]["any_death_is_critical"] is True
