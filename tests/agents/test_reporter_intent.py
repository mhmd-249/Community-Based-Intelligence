"""
Golden test cases for Reporter Agent intent detection.

Tests that the Reporter Agent correctly identifies health signals
that SHOULD trigger investigation mode, and correctly ignores
messages that should NOT trigger investigation.

Uses mocked LLM responses to test the agent's state transitions.
"""

import json

import pytest

from cbi.agents.reporter import reporter_node
from cbi.agents.state import (
    ConversationMode,
    ConversationState,
    Language,
    MessageRole,
    Platform,
    add_message_to_state,
    create_initial_state,
)

from .conftest import (
    create_mock_anthropic_response,
    make_reporter_response,
)


# =============================================================================
# Golden Test Cases: SHOULD trigger investigation
# =============================================================================

SHOULD_TRIGGER_EN = [
    pytest.param(
        "My neighbor has severe diarrhea since yesterday",
        {"symptoms": ["diarrhea"], "onset_text": "yesterday"},
        id="en-neighbor-diarrhea",
    ),
    pytest.param(
        "Three children in my village are vomiting",
        {"symptoms": ["vomiting"], "cases_count": 3},
        id="en-children-vomiting",
    ),
    pytest.param(
        "Two people died from unknown illness",
        {"deaths_count": 2},
        id="en-deaths-unknown-illness",
    ),
    pytest.param(
        "Many people sick with fever in Kassala",
        {"symptoms": ["fever"], "location_text": "Kassala"},
        id="en-fever-kassala",
    ),
    pytest.param(
        "My whole family has been having watery diarrhea and vomiting for 3 days",
        {"symptoms": ["watery diarrhea", "vomiting"], "onset_text": "3 days"},
        id="en-family-cholera-symptoms",
    ),
    pytest.param(
        "There is a disease spreading in my community, people have high fever and rash",
        {"symptoms": ["high fever", "rash"]},
        id="en-community-fever-rash",
    ),
    pytest.param(
        "Several kids under 5 are very sick with bloody diarrhea",
        {"symptoms": ["bloody diarrhea"]},
        id="en-kids-bloody-diarrhea",
    ),
    pytest.param(
        "My brother was bitten by mosquito and now has very high fever and joint pain",
        {"symptoms": ["high fever", "joint pain"], "reporter_relationship": "family"},
        id="en-dengue-symptoms",
    ),
]

SHOULD_TRIGGER_AR = [
    pytest.param(
        "جاري عنده إسهال شديد من أمس",
        {"symptoms": ["إسهال شديد"], "onset_text": "أمس"},
        id="ar-neighbor-diarrhea",
    ),
    pytest.param(
        "ثلاثة أطفال في قريتي يتقيأون",
        {"symptoms": ["قيء"], "cases_count": 3},
        id="ar-children-vomiting",
    ),
    pytest.param(
        "مات شخصين من مرض مجهول",
        {"deaths_count": 2},
        id="ar-deaths-unknown",
    ),
    pytest.param(
        "ناس كتير مرضى بالحمى في كسلا",
        {"symptoms": ["حمى"], "location_text": "كسلا"},
        id="ar-fever-kassala",
    ),
    pytest.param(
        "عائلتي كلها عندها إسهال مائي وقيء من ثلاثة أيام",
        {"symptoms": ["إسهال مائي", "قيء"], "onset_text": "ثلاثة أيام"},
        id="ar-family-cholera-symptoms",
    ),
    pytest.param(
        "في مرض منتشر في المنطقة، الناس عندهم حمى شديدة وطفح جلدي",
        {"symptoms": ["حمى شديدة", "طفح جلدي"]},
        id="ar-community-fever-rash",
    ),
]


# =============================================================================
# Golden Test Cases: Should NOT trigger investigation
# =============================================================================

SHOULD_NOT_TRIGGER = [
    pytest.param(
        "What are the symptoms of cholera?",
        id="en-question-symptoms",
    ),
    pytest.param(
        "I had malaria last year",
        id="en-past-event",
    ),
    pytest.param(
        "I heard there's disease in Egypt",
        id="en-foreign-location",
    ),
    pytest.param(
        "How do I prevent dengue?",
        id="en-prevention-question",
    ),
    pytest.param(
        "Hello, how are you?",
        id="en-greeting",
    ),
    pytest.param(
        "Thank you for the information",
        id="en-thanks",
    ),
    pytest.param(
        "What does the health ministry recommend for clean water?",
        id="en-general-health-question",
    ),
    pytest.param(
        "We had a cholera outbreak in 2020 in our area",
        id="en-past-outbreak",
    ),
    pytest.param(
        "ما هي أعراض الكوليرا؟",
        id="ar-question-symptoms",
    ),
    pytest.param(
        "كان عندي ملاريا السنة الماضية",
        id="ar-past-event",
    ),
    pytest.param(
        "كيف أمنع حمى الضنك؟",
        id="ar-prevention-question",
    ),
    pytest.param(
        "مرحبا، كيف حالك؟",
        id="ar-greeting",
    ),
]


# =============================================================================
# Tests: Health signals SHOULD trigger investigation (English)
# =============================================================================


@pytest.mark.parametrize("user_message,expected_data", SHOULD_TRIGGER_EN)
@pytest.mark.asyncio
async def test_should_trigger_investigation_en(
    patch_reporter_client,
    fresh_state,
    user_message: str,
    expected_data: dict,
):
    """Reporter Agent SHOULD detect health signal and transition to investigating."""
    # Configure mock to return a response that transitions to investigating
    mock_response_text = make_reporter_response(
        response_text="I'm sorry to hear that. Can you tell me more?",
        language="en",
        health_signal=True,
        transition_to="investigating",
        extracted_data=expected_data,
        reasoning="Health signal detected - active health incident reported.",
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    # Add user message and run the reporter node
    state = add_message_to_state(fresh_state, MessageRole.user, user_message)
    result = await reporter_node(state)

    # Verify mode transition to investigating
    assert result["current_mode"] == ConversationMode.investigating.value
    assert result.get("pending_response") is not None
    assert len(result.get("pending_response", "")) > 0

    # Verify LLM was called
    patch_reporter_client.messages.create.assert_called_once()

    # Verify extracted data was merged
    extracted = result.get("extracted_data", {})
    for key, value in expected_data.items():
        if isinstance(value, list):
            assert len(extracted.get(key, [])) > 0, f"Expected {key} to be non-empty"
        elif isinstance(value, int):
            assert extracted.get(key) == value, f"Expected {key}={value}"
        elif isinstance(value, str):
            assert extracted.get(key) is not None, f"Expected {key} to be set"


# =============================================================================
# Tests: Health signals SHOULD trigger investigation (Arabic)
# =============================================================================


@pytest.mark.parametrize("user_message,expected_data", SHOULD_TRIGGER_AR)
@pytest.mark.asyncio
async def test_should_trigger_investigation_ar(
    patch_reporter_client,
    fresh_state,
    user_message: str,
    expected_data: dict,
):
    """Reporter Agent SHOULD detect Arabic health signal and transition to investigating."""
    mock_response_text = make_reporter_response(
        response_text="آسف لسماع ذلك. هل يمكنك إخباري بالمزيد؟",
        language="ar",
        health_signal=True,
        transition_to="investigating",
        extracted_data=expected_data,
        reasoning="Health signal detected in Arabic conversation.",
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(fresh_state, MessageRole.user, user_message)
    result = await reporter_node(state)

    assert result["current_mode"] == ConversationMode.investigating.value
    assert result.get("pending_response") is not None

    # Verify language was detected as Arabic
    assert result.get("language") == Language.ar.value


# =============================================================================
# Tests: Messages that should NOT trigger investigation
# =============================================================================


@pytest.mark.parametrize("user_message", SHOULD_NOT_TRIGGER)
@pytest.mark.asyncio
async def test_should_not_trigger_investigation(
    patch_reporter_client,
    fresh_state,
    user_message: str,
):
    """Reporter Agent should stay in listening mode for non-health-signal messages."""
    mock_response_text = make_reporter_response(
        response_text="Hello! How can I help you today?",
        language="en",
        health_signal=False,
        transition_to=None,  # Stay in current mode
        extracted_data={},
        reasoning="No health signal detected. General conversation.",
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(fresh_state, MessageRole.user, user_message)
    result = await reporter_node(state)

    # Should remain in listening mode
    assert result["current_mode"] == ConversationMode.listening.value
    assert result.get("pending_response") is not None


# =============================================================================
# Tests: Mode transition correctness
# =============================================================================


@pytest.mark.asyncio
async def test_transition_listening_to_investigating(
    patch_reporter_client,
    fresh_state,
):
    """Verify correct state transition from listening to investigating."""
    mock_response_text = make_reporter_response(
        response_text="That sounds concerning. Where is this happening?",
        language="en",
        health_signal=True,
        transition_to="investigating",
        extracted_data={"symptoms": ["fever", "vomiting"]},
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(
        fresh_state, MessageRole.user, "People are sick with fever and vomiting"
    )
    result = await reporter_node(state)

    assert result["current_mode"] == ConversationMode.investigating.value
    assert result["extracted_data"]["symptoms"] == ["fever", "vomiting"]
    # Should have 2 messages: user + assistant
    assert len(result["messages"]) == 2
    assert result["messages"][-1]["role"] == MessageRole.assistant.value


@pytest.mark.asyncio
async def test_transition_investigating_to_confirming(
    patch_reporter_client,
    investigating_state,
):
    """Verify transition from investigating to confirming when enough data collected."""
    mock_response_text = make_reporter_response(
        response_text="Let me confirm: diarrhea cases in Kassala since yesterday. Is this correct?",
        language="en",
        health_signal=True,
        transition_to="confirming",
        extracted_data={
            "location_text": "Kassala",
            "onset_text": "yesterday",
            "cases_count": 5,
        },
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(
        investigating_state,
        MessageRole.user,
        "It's in Kassala, started yesterday, about 5 people",
    )
    result = await reporter_node(state)

    assert result["current_mode"] == ConversationMode.confirming.value
    assert result["extracted_data"]["location_text"] == "Kassala"
    assert result["extracted_data"]["cases_count"] == 5


@pytest.mark.asyncio
async def test_transition_confirming_to_complete(
    patch_reporter_client,
    confirming_state,
):
    """Verify transition from confirming to complete when user confirms."""
    mock_response_text = make_reporter_response(
        response_text="Thank you. Your report has been submitted to health officers.",
        language="en",
        health_signal=True,
        transition_to="complete",
        extracted_data={},
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(
        confirming_state, MessageRole.user, "Yes, that is correct"
    )
    result = await reporter_node(state)

    assert result["current_mode"] == ConversationMode.complete.value
    assert result.get("handoff_to") == "surveillance"


@pytest.mark.asyncio
async def test_stay_investigating_when_data_incomplete(
    patch_reporter_client,
    investigating_state,
):
    """Verify agent stays in investigating when more data is needed."""
    mock_response_text = make_reporter_response(
        response_text="When did the symptoms start?",
        language="en",
        health_signal=True,
        transition_to="investigating",  # Stay investigating
        extracted_data={"location_text": "near the river"},
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(
        investigating_state, MessageRole.user, "It's near the river"
    )
    result = await reporter_node(state)

    assert result["current_mode"] == ConversationMode.investigating.value
    assert "location_text" in result["extracted_data"]


# =============================================================================
# Tests: Error handling in reporter
# =============================================================================


@pytest.mark.asyncio
async def test_reporter_handles_unparseable_response(
    patch_reporter_client,
    fresh_state,
):
    """Reporter gracefully handles non-JSON LLM response."""
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response("This is not JSON at all!")
    )

    state = add_message_to_state(
        fresh_state, MessageRole.user, "People are sick"
    )
    result = await reporter_node(state)

    # Should not crash — uses raw text as response
    assert result.get("pending_response") is not None
    assert result["current_mode"] == ConversationMode.listening.value


@pytest.mark.asyncio
async def test_reporter_handles_api_connection_error(
    patch_reporter_client,
    fresh_state,
):
    """Reporter handles API connection failures gracefully."""
    import anthropic

    patch_reporter_client.messages.create.side_effect = (
        anthropic.APIConnectionError(request=None)
    )

    state = add_message_to_state(
        fresh_state, MessageRole.user, "People are sick"
    )
    result = await reporter_node(state)

    # Should set error state with apologetic message
    assert result["current_mode"] == ConversationMode.error.value
    assert result.get("error") is not None
    assert result.get("pending_response") is not None


@pytest.mark.asyncio
async def test_reporter_handles_rate_limit(
    patch_reporter_client,
    fresh_state,
):
    """Reporter handles rate limit errors gracefully."""
    import anthropic
    import httpx

    mock_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    mock_response = httpx.Response(
        status_code=429, text="Rate limited", request=mock_request
    )
    patch_reporter_client.messages.create.side_effect = (
        anthropic.RateLimitError(
            message="Rate limited",
            response=mock_response,
            body=None,
        )
    )

    state = add_message_to_state(
        fresh_state, MessageRole.user, "People are sick"
    )
    result = await reporter_node(state)

    assert result["current_mode"] == ConversationMode.error.value
    assert "rate_limit" in result.get("error", "")


# =============================================================================
# Tests: Language detection integration
# =============================================================================


@pytest.mark.asyncio
async def test_language_detected_arabic_first_message(
    patch_reporter_client,
    fresh_state,
):
    """Language should be detected as Arabic from first message."""
    mock_response_text = make_reporter_response(
        response_text="مرحباً! كيف يمكنني مساعدتك؟",
        language="ar",
        health_signal=False,
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(
        fresh_state, MessageRole.user, "مرحبا، محتاج مساعدة"
    )
    result = await reporter_node(state)

    assert result["language"] == Language.ar.value


@pytest.mark.asyncio
async def test_language_detected_english_first_message(
    patch_reporter_client,
    fresh_state,
):
    """Language should be detected as English from first message."""
    mock_response_text = make_reporter_response(
        response_text="Hello! How can I help you?",
        language="en",
        health_signal=False,
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(
        fresh_state, MessageRole.user, "Hi, I need help"
    )
    result = await reporter_node(state)

    assert result["language"] == Language.en.value


# =============================================================================
# Tests: Response quality assertions
# =============================================================================


@pytest.mark.asyncio
async def test_response_under_500_chars(
    patch_reporter_client,
    fresh_state,
):
    """Reporter responses should be under 500 characters."""
    mock_response_text = make_reporter_response(
        response_text="I'm sorry to hear that. Where is this happening?",
        language="en",
        health_signal=True,
        transition_to="investigating",
        extracted_data={"symptoms": ["fever"]},
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(
        fresh_state, MessageRole.user, "People have fever in my area"
    )
    result = await reporter_node(state)

    assert len(result.get("pending_response", "")) <= 500


@pytest.mark.asyncio
async def test_empty_message_handling(
    patch_reporter_client,
    fresh_state,
):
    """Reporter handles empty/whitespace messages gracefully."""
    mock_response_text = make_reporter_response(
        response_text="Hello! How can I help you?",
        language="en",
        health_signal=False,
    )
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(mock_response_text)
    )

    state = add_message_to_state(fresh_state, MessageRole.user, "")
    result = await reporter_node(state)

    # Should not crash
    assert result.get("pending_response") is not None
