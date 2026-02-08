"""
Tests for Reporter Agent data extraction logic.

Tests the extract_data_from_response function and how various phrasings
are parsed into structured MVS (Minimum Viable Signal) data.
"""

import pytest

from cbi.agents.reporter import (
    extract_data_from_response,
    reporter_node,
)
from cbi.agents.state import (
    ConversationMode,
    MessageRole,
    add_message_to_state,
)

from .conftest import (
    create_mock_anthropic_response,
    make_reporter_response,
)


# =============================================================================
# extract_data_from_response — direct unit tests
# =============================================================================


class TestExtractDataFromResponse:
    """Tests for the extract_data_from_response helper."""

    def test_extracts_symptoms_list(self):
        """Symptoms list should be extracted and merged."""
        parsed = {
            "extracted_data": {
                "symptoms": ["fever", "vomiting"],
            }
        }
        result = extract_data_from_response(parsed, {})
        assert result["symptoms"] == ["fever", "vomiting"]

    def test_merges_symptoms_without_duplicates(self):
        """New symptoms should be merged with existing, deduplicating."""
        parsed = {
            "extracted_data": {
                "symptoms": ["vomiting", "headache"],
            }
        }
        current = {"symptoms": ["fever", "vomiting"]}
        result = extract_data_from_response(parsed, current)
        assert "fever" in result["symptoms"]
        assert "vomiting" in result["symptoms"]
        assert "headache" in result["symptoms"]
        # No duplicates
        assert result["symptoms"].count("vomiting") == 1

    def test_extracts_location_text(self):
        """Location text should be extracted."""
        parsed = {
            "extracted_data": {
                "location_text": "Kassala, near the market",
            }
        }
        result = extract_data_from_response(parsed, {})
        assert result["location_text"] == "Kassala, near the market"

    def test_extracts_onset_text(self):
        """Onset text should be extracted."""
        parsed = {
            "extracted_data": {
                "onset_text": "since yesterday",
            }
        }
        result = extract_data_from_response(parsed, {})
        assert result["onset_text"] == "since yesterday"

    def test_extracts_cases_count_integer(self):
        """Numeric cases_count should be extracted."""
        parsed = {
            "extracted_data": {
                "cases_count": 5,
            }
        }
        result = extract_data_from_response(parsed, {})
        assert result["cases_count"] == 5

    def test_extracts_deaths_count(self):
        """deaths_count should be extracted."""
        parsed = {
            "extracted_data": {
                "deaths_count": 2,
            }
        }
        result = extract_data_from_response(parsed, {})
        assert result["deaths_count"] == 2

    def test_extracts_reporter_relationship(self):
        """reporter_relationship should be extracted."""
        parsed = {
            "extracted_data": {
                "reporter_relationship": "neighbor",
            }
        }
        result = extract_data_from_response(parsed, {})
        assert result["reporter_relationship"] == "neighbor"

    def test_ignores_null_values(self):
        """Null values should not overwrite existing data."""
        parsed = {
            "extracted_data": {
                "symptoms": None,
                "location_text": None,
                "cases_count": None,
            }
        }
        current = {
            "symptoms": ["fever"],
            "location_text": "Kassala",
            "cases_count": 3,
        }
        result = extract_data_from_response(parsed, current)
        assert result["symptoms"] == ["fever"]
        assert result["location_text"] == "Kassala"
        assert result["cases_count"] == 3

    def test_ignores_empty_strings(self):
        """Empty strings should not overwrite existing data."""
        parsed = {
            "extracted_data": {
                "location_text": "",
                "onset_text": "   ",
            }
        }
        current = {"location_text": "Kassala", "onset_text": "yesterday"}
        result = extract_data_from_response(parsed, current)
        assert result["location_text"] == "Kassala"
        assert result["onset_text"] == "yesterday"

    def test_ignores_empty_lists(self):
        """Empty lists should not overwrite existing symptoms."""
        parsed = {
            "extracted_data": {
                "symptoms": [],
            }
        }
        current = {"symptoms": ["fever"]}
        result = extract_data_from_response(parsed, current)
        assert result["symptoms"] == ["fever"]

    def test_no_extracted_data_returns_current(self):
        """When parsed has no extracted_data, returns current unchanged."""
        parsed = {}
        current = {"symptoms": ["fever"], "location_text": "Kassala"}
        result = extract_data_from_response(parsed, current)
        assert result == current

    def test_empty_extracted_data_returns_current(self):
        """When extracted_data is empty dict, returns current unchanged."""
        parsed = {"extracted_data": {}}
        current = {"symptoms": ["fever"]}
        result = extract_data_from_response(parsed, current)
        assert result == current

    def test_valid_suspected_disease(self):
        """Valid disease types should be extracted and lowercased."""
        for disease in ["cholera", "dengue", "malaria", "measles", "meningitis", "unknown"]:
            parsed = {"extracted_data": {"suspected_disease": disease}}
            result = extract_data_from_response(parsed, {})
            assert result["suspected_disease"] == disease

    def test_invalid_suspected_disease_defaults_to_unknown(self):
        """Invalid disease types should default to 'unknown'."""
        invalid_diseases = ["cold", "برد", "common_cold", "flu", "COVID-19", "ebola"]
        for disease in invalid_diseases:
            parsed = {"extracted_data": {"suspected_disease": disease}}
            result = extract_data_from_response(parsed, {})
            assert result["suspected_disease"] == "unknown", (
                f"Disease '{disease}' should default to 'unknown'"
            )

    def test_case_insensitive_disease_matching(self):
        """Disease type matching should be case-insensitive."""
        for disease in ["Cholera", "DENGUE", "Malaria"]:
            parsed = {"extracted_data": {"suspected_disease": disease}}
            result = extract_data_from_response(parsed, {})
            assert result["suspected_disease"] == disease.lower()

    def test_float_values_extracted(self):
        """Float values (e.g., zero) should be extracted."""
        parsed = {"extracted_data": {"cases_count": 0}}
        result = extract_data_from_response(parsed, {})
        assert result["cases_count"] == 0

    def test_multiple_fields_extracted_simultaneously(self):
        """Multiple fields should be extracted in a single pass."""
        parsed = {
            "extracted_data": {
                "symptoms": ["fever", "rash"],
                "location_text": "Port Sudan",
                "onset_text": "3 days ago",
                "cases_count": 7,
                "deaths_count": 1,
                "suspected_disease": "dengue",
                "reporter_relationship": "health_worker",
            }
        }
        result = extract_data_from_response(parsed, {})
        assert result["symptoms"] == ["fever", "rash"]
        assert result["location_text"] == "Port Sudan"
        assert result["onset_text"] == "3 days ago"
        assert result["cases_count"] == 7
        assert result["deaths_count"] == 1
        assert result["suspected_disease"] == "dengue"
        assert result["reporter_relationship"] == "health_worker"


# =============================================================================
# Symptom extraction via mocked LLM
# =============================================================================

SYMPTOM_EXTRACTION_CASES = [
    pytest.param(
        "People have watery diarrhea and are throwing up",
        ["watery diarrhea", "vomiting"],
        id="en-diarrhea-vomiting",
    ),
    pytest.param(
        "High fever, headache, and pain behind the eyes",
        ["high fever", "headache", "pain behind eyes"],
        id="en-dengue-like",
    ),
    pytest.param(
        "Rash that started on the face and spread to the body",
        ["rash"],
        id="en-measles-like-rash",
    ),
    pytest.param(
        "Severe headache with stiff neck and sensitivity to light",
        ["severe headache", "stiff neck", "sensitivity to light"],
        id="en-meningitis-like",
    ),
    pytest.param(
        "عندهم إسهال مائي وقيء وجفاف",
        ["إسهال مائي", "قيء", "جفاف"],
        id="ar-cholera-like",
    ),
    pytest.param(
        "حمى شديدة وصداع وألم في المفاصل",
        ["حمى شديدة", "صداع", "ألم في المفاصل"],
        id="ar-dengue-like",
    ),
]


@pytest.mark.parametrize("user_message,expected_symptoms", SYMPTOM_EXTRACTION_CASES)
@pytest.mark.asyncio
async def test_symptom_extraction(
    patch_reporter_client,
    investigating_state,
    user_message: str,
    expected_symptoms: list[str],
):
    """Reporter extracts symptoms from various phrasings."""
    lang = "ar" if any("\u0600" <= c <= "\u06ff" for c in user_message) else "en"
    mock_response_text = make_reporter_response(
        response_text="When did these symptoms start?",
        language=lang,
        health_signal=True,
        transition_to="investigating",
        extracted_data={"symptoms": expected_symptoms},
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(investigating_state, MessageRole.user, user_message)
    result = await reporter_node(state)

    extracted = result["extracted_data"]
    # Original symptoms should still be there (merged)
    assert "diarrhea" in extracted["symptoms"] or "إسهال" in extracted["symptoms"]
    # New symptoms should also be present
    for symptom in expected_symptoms:
        assert symptom in extracted["symptoms"]


# =============================================================================
# Location extraction via mocked LLM
# =============================================================================

LOCATION_EXTRACTION_CASES = [
    pytest.param("Kassala", "Kassala", id="specific-city"),
    pytest.param("near the market in Omdurman", "near the market in Omdurman", id="specific-with-detail"),
    pytest.param("my village", "my village", id="vague-village"),
    pytest.param("شرق النيل", "شرق النيل", id="ar-east-nile"),
    pytest.param("قريتنا في شمال دارفور", "قريتنا في شمال دارفور", id="ar-north-darfur"),
    pytest.param("near the river, about 2km from Port Sudan", "near the river, about 2km from Port Sudan", id="relative-location"),
]


@pytest.mark.parametrize("user_input,expected_location", LOCATION_EXTRACTION_CASES)
@pytest.mark.asyncio
async def test_location_extraction(
    patch_reporter_client,
    investigating_state,
    user_input: str,
    expected_location: str,
):
    """Reporter extracts location from vague and specific descriptions."""
    mock_response_text = make_reporter_response(
        response_text="When did the symptoms start?",
        language="en",
        health_signal=True,
        transition_to="investigating",
        extracted_data={"location_text": expected_location},
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(investigating_state, MessageRole.user, user_input)
    result = await reporter_node(state)

    assert result["extracted_data"]["location_text"] == expected_location


# =============================================================================
# Number extraction via mocked LLM
# =============================================================================

NUMBER_EXTRACTION_CASES = [
    pytest.param("three people", 3, id="en-word-three"),
    pytest.param("3 people", 3, id="en-digit-3"),
    pytest.param("about ten people", 10, id="en-word-ten"),
    pytest.param("a few people, maybe 5", 5, id="en-approximate"),
    pytest.param("around twenty families", 20, id="en-word-twenty"),
    pytest.param("ثلاثة أشخاص", 3, id="ar-three"),
    pytest.param("عشرة أشخاص", 10, id="ar-ten"),
    pytest.param("حوالي ٥ أشخاص", 5, id="ar-digit-5"),
    pytest.param("عشرين عائلة", 20, id="ar-twenty"),
]


@pytest.mark.parametrize("user_input,expected_count", NUMBER_EXTRACTION_CASES)
@pytest.mark.asyncio
async def test_number_extraction(
    patch_reporter_client,
    investigating_state,
    user_input: str,
    expected_count: int,
):
    """Reporter extracts case counts from word and digit representations."""
    mock_response_text = make_reporter_response(
        response_text="Thank you. Any deaths reported?",
        language="en",
        health_signal=True,
        transition_to="investigating",
        extracted_data={"cases_count": expected_count},
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(investigating_state, MessageRole.user, user_input)
    result = await reporter_node(state)

    assert result["extracted_data"]["cases_count"] == expected_count


# =============================================================================
# Reporter relationship extraction
# =============================================================================

RELATIONSHIP_CASES = [
    pytest.param("I am sick myself", "self", id="self"),
    pytest.param("My child is sick", "family", id="family"),
    pytest.param("My neighbor told me", "neighbor", id="neighbor"),
    pytest.param("I'm a nurse at the clinic", "health_worker", id="health-worker"),
    pytest.param("As village chief I want to report", "community_leader", id="community-leader"),
]


@pytest.mark.parametrize("user_input,expected_relationship", RELATIONSHIP_CASES)
@pytest.mark.asyncio
async def test_reporter_relationship_extraction(
    patch_reporter_client,
    investigating_state,
    user_input: str,
    expected_relationship: str,
):
    """Reporter extracts the reporter's relationship to the cases."""
    mock_response_text = make_reporter_response(
        response_text="Thank you. Can you tell me more about the symptoms?",
        language="en",
        health_signal=True,
        transition_to="investigating",
        extracted_data={"reporter_relationship": expected_relationship},
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(investigating_state, MessageRole.user, user_input)
    result = await reporter_node(state)

    assert result["extracted_data"]["reporter_relationship"] == expected_relationship


# =============================================================================
# Onset / timing extraction
# =============================================================================

ONSET_EXTRACTION_CASES = [
    pytest.param("yesterday", "yesterday", id="yesterday"),
    pytest.param("since last week", "since last week", id="last-week"),
    pytest.param("3 days ago", "3 days ago", id="3-days-ago"),
    pytest.param("started this morning", "this morning", id="this-morning"),
    pytest.param("من أمس", "من أمس", id="ar-yesterday"),
    pytest.param("من أسبوع", "من أسبوع", id="ar-one-week"),
    pytest.param("من ثلاثة أيام", "من ثلاثة أيام", id="ar-3-days"),
]


@pytest.mark.parametrize("user_input,expected_onset", ONSET_EXTRACTION_CASES)
@pytest.mark.asyncio
async def test_onset_extraction(
    patch_reporter_client,
    investigating_state,
    user_input: str,
    expected_onset: str,
):
    """Reporter extracts onset timing from various phrasings."""
    mock_response_text = make_reporter_response(
        response_text="How many people are affected?",
        language="en",
        health_signal=True,
        transition_to="investigating",
        extracted_data={"onset_text": expected_onset},
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(investigating_state, MessageRole.user, user_input)
    result = await reporter_node(state)

    assert result["extracted_data"]["onset_text"] == expected_onset
