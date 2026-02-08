"""
Pytest configuration and shared fixtures for agent tests.

Provides mock Anthropic client, test conversation states,
and helpers to create structured LLM responses.
"""

import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cbi.agents.state import (
    ConversationMode,
    ConversationState,
    ExtractedData,
    Language,
    MessageRole,
    Platform,
    add_message_to_state,
    create_initial_state,
)


# =============================================================================
# Mock LLM Response Helpers
# =============================================================================


def make_reporter_response(
    response_text: str,
    language: str = "en",
    health_signal: bool = False,
    transition_to: str | None = None,
    extracted_data: dict | None = None,
    reasoning: str = "",
) -> str:
    """
    Build a JSON response string mimicking the Reporter Agent's expected format.

    Args:
        response_text: The user-facing message
        language: Detected language (ar/en)
        health_signal: Whether a health signal was detected
        transition_to: Mode to transition to (or None)
        extracted_data: Extracted MVS data dict
        reasoning: Internal reasoning note

    Returns:
        JSON string of the response
    """
    payload = {
        "response": response_text,
        "detected_language": language,
        "health_signal_detected": health_signal,
        "extracted_data": extracted_data or {},
        "transition_to": transition_to,
        "reasoning": reasoning,
    }
    return json.dumps(payload, ensure_ascii=False)


def make_surveillance_response(
    suspected_disease: str = "unknown",
    confidence: float = 0.5,
    urgency: str = "medium",
    alert_type: str = "single_case",
    reasoning: str = "",
    recommended_actions: list[str] | None = None,
    follow_up_questions: list[str] | None = None,
) -> str:
    """
    Build a JSON response string mimicking the Surveillance Agent's expected format.

    Args:
        suspected_disease: Disease classification
        confidence: Confidence score 0-1
        urgency: Urgency level
        alert_type: Alert type classification
        reasoning: Classification reasoning
        recommended_actions: List of recommended actions
        follow_up_questions: List of follow-up questions

    Returns:
        JSON string of the response
    """
    payload = {
        "suspected_disease": suspected_disease,
        "confidence": confidence,
        "urgency": urgency,
        "alert_type": alert_type,
        "reasoning": reasoning,
        "key_symptoms": [],
        "recommended_actions": recommended_actions or [],
        "follow_up_questions": follow_up_questions or [],
        "linked_reports": [],
        "data_quality_notes": "",
    }
    return json.dumps(payload, ensure_ascii=False)


def make_analyst_summary_response(
    summary: str = "Situation analysis complete.",
    key_points: list[str] | None = None,
    risk_assessment: str = "medium",
    recommendations: list[str] | None = None,
) -> str:
    """Build a JSON response string mimicking the Analyst Agent summary format."""
    payload = {
        "summary": summary,
        "key_points": key_points or ["Point 1"],
        "threshold_status": "Within thresholds",
        "recommendations": recommendations or ["Monitor situation"],
        "risk_assessment": risk_assessment,
    }
    return json.dumps(payload, ensure_ascii=False)


# =============================================================================
# Mock Anthropic Client
# =============================================================================


def _make_content_block(text: str) -> MagicMock:
    """Create a mock content block with a text attribute."""
    block = MagicMock()
    block.text = text
    return block


def create_mock_anthropic_response(text: str, stop_reason: str = "end_turn") -> MagicMock:
    """
    Create a mock response object matching anthropic.types.Message structure.

    Args:
        text: The response text
        stop_reason: Stop reason (end_turn, max_tokens, etc.)

    Returns:
        Mock response object with .content and .stop_reason
    """
    response = MagicMock()
    response.content = [_make_content_block(text)]
    response.stop_reason = stop_reason
    return response


@pytest.fixture
def mock_anthropic_client():
    """
    Fixture providing a mock AsyncAnthropic client.

    The client's messages.create method is an AsyncMock that can be
    configured per-test with side_effect or return_value.

    Usage:
        def test_something(mock_anthropic_client):
            mock_anthropic_client.messages.create.return_value = (
                create_mock_anthropic_response(make_reporter_response(...))
            )
    """
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock()
    return client


@pytest.fixture
def patch_reporter_client(mock_anthropic_client):
    """Patch the reporter agent's get_anthropic_client to return mock."""
    with patch(
        "cbi.agents.reporter.get_anthropic_client",
        return_value=mock_anthropic_client,
    ):
        yield mock_anthropic_client


@pytest.fixture
def patch_surveillance_client(mock_anthropic_client):
    """Patch the surveillance agent's get_anthropic_client to return mock."""
    with patch(
        "cbi.agents.surveillance.get_anthropic_client",
        return_value=mock_anthropic_client,
    ):
        yield mock_anthropic_client


@pytest.fixture
def patch_analyst_client(mock_anthropic_client):
    """Patch the analyst agent's get_anthropic_client to return mock."""
    with patch(
        "cbi.agents.analyst.get_anthropic_client",
        return_value=mock_anthropic_client,
    ):
        yield mock_anthropic_client


# =============================================================================
# Test Conversation States
# =============================================================================


@pytest.fixture
def fresh_state() -> ConversationState:
    """A brand-new conversation state in listening mode."""
    return create_initial_state(
        conversation_id="conv_test_001",
        phone="736514658",
        platform=Platform.telegram,
    )


@pytest.fixture
def listening_state_with_message() -> ConversationState:
    """Listening-mode state with one user message already added."""
    state = create_initial_state(
        conversation_id="conv_test_002",
        phone="736514658",
        platform=Platform.telegram,
    )
    return add_message_to_state(state, MessageRole.user, "Hello")


@pytest.fixture
def investigating_state() -> ConversationState:
    """State in investigating mode with some data collected."""
    state = create_initial_state(
        conversation_id="conv_test_003",
        phone="736514658",
        platform=Platform.telegram,
    )
    state = add_message_to_state(
        state, MessageRole.user, "People are sick with diarrhea in my village"
    )
    state = add_message_to_state(
        state,
        MessageRole.assistant,
        "I'm sorry to hear that. Can you tell me where this is happening?",
    )
    # Update mode and extracted data
    new = dict(state)
    new["current_mode"] = ConversationMode.investigating.value
    new["language"] = Language.en.value
    new["extracted_data"] = {
        **state["extracted_data"],
        "symptoms": ["diarrhea"],
        "suspected_disease": "unknown",
    }
    return ConversationState(**new)


@pytest.fixture
def confirming_state() -> ConversationState:
    """State in confirming mode with all MVS data collected."""
    state = create_initial_state(
        conversation_id="conv_test_004",
        phone="736514658",
        platform=Platform.telegram,
    )
    # Simulate a multi-turn conversation
    state = add_message_to_state(
        state, MessageRole.user, "Many people are sick with vomiting and diarrhea"
    )
    state = add_message_to_state(
        state, MessageRole.assistant, "Where is this happening?"
    )
    state = add_message_to_state(state, MessageRole.user, "Kassala, near the market")
    state = add_message_to_state(
        state, MessageRole.assistant, "When did the symptoms start?"
    )
    state = add_message_to_state(state, MessageRole.user, "Since two days ago")
    state = add_message_to_state(
        state, MessageRole.assistant, "How many people are affected?"
    )
    state = add_message_to_state(state, MessageRole.user, "About 10 people, 2 died")

    new = dict(state)
    new["current_mode"] = ConversationMode.confirming.value
    new["language"] = Language.en.value
    new["extracted_data"] = {
        "symptoms": ["vomiting", "diarrhea"],
        "suspected_disease": "cholera",
        "location_text": "Kassala, near the market",
        "location_normalized": None,
        "location_coords": None,
        "onset_text": "two days ago",
        "onset_date": None,
        "cases_count": 10,
        "deaths_count": 2,
        "affected_description": None,
        "reporter_relationship": None,
    }
    new["classification"] = {
        **new.get("classification", {}),
        "data_completeness": 0.85,
    }
    return ConversationState(**new)


@pytest.fixture
def complete_state(confirming_state) -> ConversationState:
    """State after user confirms — ready for handoff to surveillance."""
    state = add_message_to_state(
        confirming_state, MessageRole.user, "Yes, that is correct"
    )
    new = dict(state)
    new["current_mode"] = ConversationMode.complete.value
    new["handoff_to"] = "surveillance"
    return ConversationState(**new)


@pytest.fixture
def arabic_investigating_state() -> ConversationState:
    """Arabic conversation in investigating mode."""
    state = create_initial_state(
        conversation_id="conv_test_ar_001",
        phone="736514658",
        platform=Platform.telegram,
    )
    state = add_message_to_state(
        state, MessageRole.user, "في ناس كتير مرضى بالإسهال في قريتي"
    )
    state = add_message_to_state(
        state, MessageRole.assistant, "آسف لسماع ذلك. أين يحدث هذا؟"
    )
    new = dict(state)
    new["current_mode"] = ConversationMode.investigating.value
    new["language"] = Language.ar.value
    new["extracted_data"] = {
        **state["extracted_data"],
        "symptoms": ["إسهال"],
        "suspected_disease": "unknown",
    }
    return ConversationState(**new)
