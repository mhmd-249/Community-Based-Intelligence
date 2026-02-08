"""
Unit tests for prompt formatting and validation functions.

Tests the prompts module used by the Reporter, Surveillance, and Analyst agents.
"""

import json

import pytest

from cbi.agents.prompts import (
    ANALYST_SYSTEM_PROMPT,
    ARABIC_PHRASES,
    REPORTER_SYSTEM_PROMPT,
    SURVEILLANCE_SYSTEM_PROMPT,
    format_analyst_prompt,
    format_reporter_prompt,
    format_surveillance_prompt,
    validate_analyst_query_response,
    validate_analyst_summary_response,
    validate_reporter_response,
    validate_surveillance_response,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_extracted_data() -> dict:
    """Sample extracted data for prompt formatting."""
    return {
        "symptoms": ["fever", "diarrhea"],
        "location_text": "Khartoum North",
        "onset_text": "three days ago",
        "cases_count": 5,
    }


@pytest.fixture
def sample_report_data() -> dict:
    """Sample report data for surveillance prompt."""
    return {
        "symptoms": ["watery diarrhea", "vomiting", "dehydration"],
        "suspected_disease": "cholera",
        "location_text": "Omdurman market area",
        "onset_text": "two days ago",
        "cases_count": 10,
        "deaths_count": 2,
        "reporter_relationship": "health_worker",
    }


@pytest.fixture
def valid_reporter_response() -> dict:
    """Valid reporter agent response."""
    return {
        "response": "I'm sorry to hear that. Can you tell me where this is happening?",
        "detected_language": "en",
        "health_signal_detected": True,
        "extracted_data": {"symptoms": ["fever"]},
        "transition_to": "investigating",
        "reasoning": "Health signal detected, transitioning to investigation",
    }


@pytest.fixture
def valid_surveillance_response() -> dict:
    """Valid surveillance agent response."""
    return {
        "suspected_disease": "cholera",
        "confidence": 0.85,
        "urgency": "critical",
        "alert_type": "suspected_outbreak",
        "reasoning": "Multiple cases with classic cholera symptoms",
        "key_symptoms": ["watery diarrhea", "vomiting"],
        "recommended_actions": ["Activate outbreak response team"],
    }


@pytest.fixture
def valid_analyst_query_response() -> dict:
    """Valid analyst query response."""
    return {
        "query_understanding": "User wants cholera case count this week",
        "sql": "SELECT COUNT(*) FROM reports WHERE suspected_disease='cholera' AND created_at > NOW() - INTERVAL '7 days'",
        "explanation": "Count of cholera reports in the last 7 days",
        "visualization_type": "stat_card",
    }


# =============================================================================
# Tests for Prompt Formatting with Variables
# =============================================================================


class TestFormatReporterPrompt:
    """Tests for format_reporter_prompt function."""

    def test_formats_with_all_variables(
        self, sample_extracted_data: dict
    ) -> None:
        """Should format prompt with all variables."""
        prompt = format_reporter_prompt(
            mode="investigating",
            language="en",
            extracted_data=sample_extracted_data,
            missing_fields=["affected_description", "reporter_relationship"],
        )

        assert "investigating" in prompt
        assert "en" in prompt
        assert "fever" in prompt
        assert "affected_description" in prompt

    def test_formats_mode_correctly(self) -> None:
        """Should include mode in prompt."""
        prompt = format_reporter_prompt(
            mode="listening",
            language="ar",
            extracted_data={},
            missing_fields=[],
        )

        assert "listening" in prompt

    def test_formats_language_correctly(self) -> None:
        """Should include language in prompt."""
        prompt = format_reporter_prompt(
            mode="listening",
            language="ar",
            extracted_data={},
            missing_fields=[],
        )

        assert "ar" in prompt

    def test_formats_extracted_data_as_json(
        self, sample_extracted_data: dict
    ) -> None:
        """Should format extracted data as JSON."""
        prompt = format_reporter_prompt(
            mode="investigating",
            language="en",
            extracted_data=sample_extracted_data,
            missing_fields=[],
        )

        # Should contain JSON-formatted data
        assert '"symptoms"' in prompt or "'symptoms'" in prompt
        assert "Khartoum North" in prompt

    def test_formats_missing_fields_list(self) -> None:
        """Should format missing fields as comma-separated list."""
        prompt = format_reporter_prompt(
            mode="investigating",
            language="en",
            extracted_data={},
            missing_fields=["symptoms", "location_text", "onset_text"],
        )

        assert "symptoms" in prompt
        assert "location_text" in prompt

    def test_handles_empty_missing_fields(self) -> None:
        """Should handle empty missing fields list."""
        prompt = format_reporter_prompt(
            mode="confirming",
            language="en",
            extracted_data={},
            missing_fields=[],
        )

        assert "None" in prompt

    def test_handles_arabic_in_extracted_data(self) -> None:
        """Should handle Arabic text in extracted data."""
        arabic_data = {
            "symptoms": ["حمى", "إسهال"],
            "location_text": "الخرطوم شمال",
        }

        prompt = format_reporter_prompt(
            mode="investigating",
            language="ar",
            extracted_data=arabic_data,
            missing_fields=[],
        )

        assert "حمى" in prompt
        assert "الخرطوم شمال" in prompt

    def test_returns_string(self) -> None:
        """Should return a string."""
        prompt = format_reporter_prompt(
            mode="listening",
            language="en",
            extracted_data={},
            missing_fields=[],
        )

        assert isinstance(prompt, str)


class TestFormatSurveillancePrompt:
    """Tests for format_surveillance_prompt function."""

    def test_formats_with_report_data(
        self, sample_report_data: dict
    ) -> None:
        """Should format prompt with report data."""
        prompt = format_surveillance_prompt(sample_report_data)

        assert "watery diarrhea" in prompt
        assert "cholera" in prompt
        assert "Omdurman" in prompt

    def test_includes_disease_thresholds(self) -> None:
        """Should include disease threshold information."""
        prompt = format_surveillance_prompt({})

        assert "Cholera" in prompt
        assert "Dengue" in prompt
        assert "1 case" in prompt  # Cholera threshold

    def test_includes_urgency_levels(self) -> None:
        """Should include urgency level definitions."""
        prompt = format_surveillance_prompt({})

        assert "CRITICAL" in prompt
        assert "HIGH" in prompt
        assert "MEDIUM" in prompt
        assert "LOW" in prompt

    def test_returns_string(self, sample_report_data: dict) -> None:
        """Should return a string."""
        prompt = format_surveillance_prompt(sample_report_data)
        assert isinstance(prompt, str)


class TestFormatAnalystPrompt:
    """Tests for format_analyst_prompt function."""

    def test_formats_with_all_parameters(self) -> None:
        """Should format prompt with all parameters."""
        prompt = format_analyst_prompt(
            query="How many cholera cases this week?",
            current_date="2024-01-15",
            user_role="health_officer",
            region_filter="Khartoum",
        )

        assert "cholera" in prompt
        assert "2024-01-15" in prompt
        assert "health_officer" in prompt
        assert "Khartoum" in prompt

    def test_default_user_role(self) -> None:
        """Should use default user role if not provided."""
        prompt = format_analyst_prompt(
            query="Test query",
            current_date="2024-01-15",
        )

        assert "health_officer" in prompt

    def test_handles_none_region_filter(self) -> None:
        """Should handle None region filter."""
        prompt = format_analyst_prompt(
            query="Test query",
            current_date="2024-01-15",
            region_filter=None,
        )

        assert "None (all regions)" in prompt

    def test_includes_database_schema(self) -> None:
        """Should include database schema information."""
        prompt = format_analyst_prompt(
            query="Test",
            current_date="2024-01-15",
        )

        assert "Reports Table" in prompt
        assert "symptoms" in prompt
        assert "suspected_disease" in prompt

    def test_returns_string(self) -> None:
        """Should return a string."""
        prompt = format_analyst_prompt(
            query="Test",
            current_date="2024-01-15",
        )
        assert isinstance(prompt, str)


# =============================================================================
# Tests for Prompt Length Constraints
# =============================================================================


class TestPromptLengthConstraints:
    """Tests for prompt length and content constraints."""

    def test_reporter_prompt_mentions_50_word_limit(self) -> None:
        """Reporter prompt should mention 50 word response limit."""
        assert "50 words" in REPORTER_SYSTEM_PROMPT

    def test_reporter_prompt_mentions_response_limit(
        self, sample_extracted_data: dict
    ) -> None:
        """Formatted reporter prompt should preserve response limit instruction."""
        prompt = format_reporter_prompt(
            mode="investigating",
            language="en",
            extracted_data=sample_extracted_data,
            missing_fields=[],
        )

        assert "50 words" in prompt

    def test_surveillance_prompt_has_disease_classification(self) -> None:
        """Surveillance prompt should have disease classification section."""
        assert "Disease Classification" in SURVEILLANCE_SYSTEM_PROMPT
        assert "cholera" in SURVEILLANCE_SYSTEM_PROMPT.lower()
        assert "dengue" in SURVEILLANCE_SYSTEM_PROMPT.lower()
        assert "malaria" in SURVEILLANCE_SYSTEM_PROMPT.lower()

    def test_analyst_prompt_has_example_queries(self) -> None:
        """Analyst prompt should include example queries."""
        assert "Example Queries" in ANALYST_SYSTEM_PROMPT

    def test_prompts_are_reasonable_length(self) -> None:
        """Prompts should be reasonable length (not too long)."""
        # Reporter prompt
        reporter = format_reporter_prompt(
            mode="listening",
            language="en",
            extracted_data={},
            missing_fields=[],
        )
        assert len(reporter) < 10000  # Reasonable limit

        # Surveillance prompt
        surveillance = format_surveillance_prompt({})
        assert len(surveillance) < 10000

        # Analyst prompt
        analyst = format_analyst_prompt(
            query="test",
            current_date="2024-01-01",
        )
        assert len(analyst) < 10000


# =============================================================================
# Tests for validate_reporter_response
# =============================================================================


class TestValidateReporterResponse:
    """Tests for validate_reporter_response function."""

    def test_valid_response_passes(
        self, valid_reporter_response: dict
    ) -> None:
        """Valid response should pass validation."""
        is_valid, errors = validate_reporter_response(valid_reporter_response)

        assert is_valid is True
        assert errors == []

    def test_missing_response_field(self) -> None:
        """Should fail if 'response' field is missing."""
        response = {
            "detected_language": "en",
            "health_signal_detected": True,
        }

        is_valid, errors = validate_reporter_response(response)

        assert is_valid is False
        assert any("response" in e for e in errors)

    def test_missing_detected_language(self) -> None:
        """Should fail if 'detected_language' field is missing."""
        response = {
            "response": "Hello",
            "health_signal_detected": True,
        }

        is_valid, errors = validate_reporter_response(response)

        assert is_valid is False
        assert any("detected_language" in e for e in errors)

    def test_missing_health_signal_detected(self) -> None:
        """Should fail if 'health_signal_detected' field is missing."""
        response = {
            "response": "Hello",
            "detected_language": "en",
        }

        is_valid, errors = validate_reporter_response(response)

        assert is_valid is False
        assert any("health_signal_detected" in e for e in errors)

    def test_response_exceeds_500_chars(self) -> None:
        """Should fail if response exceeds 500 characters."""
        response = {
            "response": "x" * 501,
            "detected_language": "en",
            "health_signal_detected": False,
        }

        is_valid, errors = validate_reporter_response(response)

        assert is_valid is False
        assert any("500 character" in e for e in errors)

    def test_invalid_detected_language(self) -> None:
        """Should fail for invalid language code."""
        response = {
            "response": "Hello",
            "detected_language": "fr",  # Invalid - only ar/en
            "health_signal_detected": True,
        }

        is_valid, errors = validate_reporter_response(response)

        assert is_valid is False
        assert any("ar" in e or "en" in e for e in errors)

    def test_invalid_transition_to(self) -> None:
        """Should fail for invalid transition mode."""
        response = {
            "response": "Hello",
            "detected_language": "en",
            "health_signal_detected": True,
            "transition_to": "invalid_mode",
        }

        is_valid, errors = validate_reporter_response(response)

        assert is_valid is False
        assert any("transition_to" in e for e in errors)

    def test_valid_transition_modes(self) -> None:
        """Should accept valid transition modes."""
        valid_modes = ["listening", "investigating", "confirming", "complete"]

        for mode in valid_modes:
            response = {
                "response": "Hello",
                "detected_language": "en",
                "health_signal_detected": True,
                "transition_to": mode,
            }

            is_valid, _ = validate_reporter_response(response)
            assert is_valid is True, f"Mode {mode} should be valid"

    def test_null_transition_to_is_valid(self) -> None:
        """Should accept null/None transition_to."""
        response = {
            "response": "Hello",
            "detected_language": "en",
            "health_signal_detected": True,
            "transition_to": None,
        }

        is_valid, errors = validate_reporter_response(response)
        assert is_valid is True


# =============================================================================
# Tests for validate_surveillance_response
# =============================================================================


class TestValidateSurveillanceResponse:
    """Tests for validate_surveillance_response function."""

    def test_valid_response_passes(
        self, valid_surveillance_response: dict
    ) -> None:
        """Valid response should pass validation."""
        is_valid, errors = validate_surveillance_response(valid_surveillance_response)

        assert is_valid is True
        assert errors == []

    def test_missing_suspected_disease(self) -> None:
        """Should fail if 'suspected_disease' is missing."""
        response = {
            "confidence": 0.8,
            "urgency": "high",
            "alert_type": "cluster",
        }

        is_valid, errors = validate_surveillance_response(response)

        assert is_valid is False
        assert any("suspected_disease" in e for e in errors)

    def test_missing_confidence(self) -> None:
        """Should fail if 'confidence' is missing."""
        response = {
            "suspected_disease": "cholera",
            "urgency": "high",
            "alert_type": "cluster",
        }

        is_valid, errors = validate_surveillance_response(response)

        assert is_valid is False
        assert any("confidence" in e for e in errors)

    def test_invalid_confidence_range(self) -> None:
        """Should fail if confidence is outside 0-1 range."""
        response = {
            "suspected_disease": "cholera",
            "confidence": 1.5,  # Invalid
            "urgency": "high",
            "alert_type": "cluster",
        }

        is_valid, errors = validate_surveillance_response(response)

        assert is_valid is False
        assert any("confidence" in e for e in errors)

    def test_invalid_suspected_disease(self) -> None:
        """Should fail for invalid disease type."""
        response = {
            "suspected_disease": "ebola",  # Invalid
            "confidence": 0.8,
            "urgency": "high",
            "alert_type": "cluster",
        }

        is_valid, errors = validate_surveillance_response(response)

        assert is_valid is False
        assert any("suspected_disease" in e for e in errors)

    def test_valid_disease_types(self) -> None:
        """Should accept all valid disease types."""
        valid_diseases = [
            "cholera",
            "dengue",
            "malaria",
            "measles",
            "meningitis",
            "unknown",
        ]

        for disease in valid_diseases:
            response = {
                "suspected_disease": disease,
                "confidence": 0.8,
                "urgency": "high",
                "alert_type": "cluster",
            }

            is_valid, _ = validate_surveillance_response(response)
            assert is_valid is True, f"Disease {disease} should be valid"

    def test_invalid_urgency(self) -> None:
        """Should fail for invalid urgency level."""
        response = {
            "suspected_disease": "cholera",
            "confidence": 0.8,
            "urgency": "extreme",  # Invalid
            "alert_type": "cluster",
        }

        is_valid, errors = validate_surveillance_response(response)

        assert is_valid is False
        assert any("urgency" in e for e in errors)

    def test_valid_urgency_levels(self) -> None:
        """Should accept all valid urgency levels."""
        valid_urgencies = ["critical", "high", "medium", "low"]

        for urgency in valid_urgencies:
            response = {
                "suspected_disease": "cholera",
                "confidence": 0.8,
                "urgency": urgency,
                "alert_type": "cluster",
            }

            is_valid, _ = validate_surveillance_response(response)
            assert is_valid is True, f"Urgency {urgency} should be valid"

    def test_invalid_alert_type(self) -> None:
        """Should fail for invalid alert type."""
        response = {
            "suspected_disease": "cholera",
            "confidence": 0.8,
            "urgency": "high",
            "alert_type": "pandemic",  # Invalid
        }

        is_valid, errors = validate_surveillance_response(response)

        assert is_valid is False
        assert any("alert_type" in e for e in errors)

    def test_valid_alert_types(self) -> None:
        """Should accept all valid alert types."""
        valid_types = ["suspected_outbreak", "cluster", "single_case", "rumor"]

        for alert_type in valid_types:
            response = {
                "suspected_disease": "cholera",
                "confidence": 0.8,
                "urgency": "high",
                "alert_type": alert_type,
            }

            is_valid, _ = validate_surveillance_response(response)
            assert is_valid is True, f"Alert type {alert_type} should be valid"


# =============================================================================
# Tests for validate_analyst_query_response
# =============================================================================


class TestValidateAnalystQueryResponse:
    """Tests for validate_analyst_query_response function."""

    def test_valid_response_passes(
        self, valid_analyst_query_response: dict
    ) -> None:
        """Valid response should pass validation."""
        is_valid, errors = validate_analyst_query_response(
            valid_analyst_query_response
        )

        assert is_valid is True
        assert errors == []

    def test_invalid_query_type(self) -> None:
        """Should fail for invalid query type."""
        response = {"query_type": "invalid_type"}

        is_valid, errors = validate_analyst_query_response(response)

        assert is_valid is False
        assert any("query_type" in e for e in errors)

    def test_valid_query_types(self) -> None:
        """Should accept all valid query types."""
        valid_types = [
            "case_count",
            "trend",
            "comparison",
            "geographic",
            "timeline",
            "summary",
            "threshold_check",
        ]

        for query_type in valid_types:
            response = {"query_type": query_type}
            is_valid, _ = validate_analyst_query_response(response)
            assert is_valid is True, f"Query type {query_type} should be valid"

    def test_sql_must_start_with_select(self) -> None:
        """SQL should start with SELECT."""
        response = {
            "sql": "DELETE FROM reports",  # Invalid
        }

        is_valid, errors = validate_analyst_query_response(response)

        assert is_valid is False
        assert any("SELECT" in e for e in errors)

    def test_sql_with_with_clause(self) -> None:
        """SQL can start with WITH (CTE)."""
        response = {
            "sql": "WITH recent AS (SELECT * FROM reports) SELECT * FROM recent",
        }

        is_valid, errors = validate_analyst_query_response(response)
        assert is_valid is True

    def test_invalid_visualization_type(self) -> None:
        """Should fail for invalid visualization type."""
        response = {"visualization_type": "scatter_plot"}  # Invalid

        is_valid, errors = validate_analyst_query_response(response)

        assert is_valid is False
        assert any("visualization_type" in e for e in errors)

    def test_valid_visualization_types(self) -> None:
        """Should accept all valid visualization types."""
        valid_types = [
            "bar_chart",
            "line_chart",
            "map",
            "table",
            "stat_card",
            "none",
        ]

        for viz_type in valid_types:
            response = {"visualization_type": viz_type}
            is_valid, _ = validate_analyst_query_response(response)
            assert is_valid is True, f"Visualization {viz_type} should be valid"


# =============================================================================
# Tests for validate_analyst_summary_response
# =============================================================================


class TestValidateAnalystSummaryResponse:
    """Tests for validate_analyst_summary_response function."""

    def test_valid_response_passes(self) -> None:
        """Valid summary response should pass."""
        response = {
            "summary": "Weekly summary of health reports",
            "risk_assessment": "medium",
        }

        is_valid, errors = validate_analyst_summary_response(response)

        assert is_valid is True
        assert errors == []

    def test_missing_summary(self) -> None:
        """Should fail if summary is missing."""
        response = {"risk_assessment": "high"}

        is_valid, errors = validate_analyst_summary_response(response)

        assert is_valid is False
        assert any("summary" in e for e in errors)

    def test_empty_summary(self) -> None:
        """Should fail if summary is empty."""
        response = {"summary": ""}

        is_valid, errors = validate_analyst_summary_response(response)

        assert is_valid is False
        assert any("summary" in e for e in errors)

    def test_invalid_risk_assessment(self) -> None:
        """Should fail for invalid risk assessment."""
        response = {
            "summary": "Test summary",
            "risk_assessment": "extreme",  # Invalid
        }

        is_valid, errors = validate_analyst_summary_response(response)

        assert is_valid is False
        assert any("risk_assessment" in e for e in errors)

    def test_valid_risk_assessments(self) -> None:
        """Should accept all valid risk assessments."""
        valid_risks = ["low", "medium", "high", "critical"]

        for risk in valid_risks:
            response = {
                "summary": "Test summary",
                "risk_assessment": risk,
            }
            is_valid, _ = validate_analyst_summary_response(response)
            assert is_valid is True, f"Risk {risk} should be valid"


# =============================================================================
# Tests for Arabic Phrases
# =============================================================================


class TestArabicPhrases:
    """Tests for ARABIC_PHRASES constant."""

    def test_contains_greeting(self) -> None:
        """Should contain Arabic greeting."""
        assert "greeting" in ARABIC_PHRASES
        assert "مرحباً" in ARABIC_PHRASES["greeting"]

    def test_contains_thank_you(self) -> None:
        """Should contain Arabic thank you."""
        assert "thank_you" in ARABIC_PHRASES
        assert "شكراً" in ARABIC_PHRASES["thank_you"]

    def test_all_values_are_arabic(self) -> None:
        """All phrase values should contain Arabic characters."""
        arabic_range = range(0x0600, 0x06FF + 1)

        for key, value in ARABIC_PHRASES.items():
            has_arabic = any(ord(c) in arabic_range for c in value)
            assert has_arabic, f"Phrase '{key}' should contain Arabic characters"

    def test_common_phrases_present(self) -> None:
        """Common phrases should be present."""
        expected_keys = [
            "greeting",
            "thank_you",
            "sorry_to_hear",
            "where_happening",
            "when_started",
        ]

        for key in expected_keys:
            assert key in ARABIC_PHRASES, f"Missing phrase: {key}"
