"""
Tests for complete conversation flows through the agent pipeline.

Simulates multi-turn conversations from first message through
report completion, including mode transitions, data accumulation,
and handoff to surveillance.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cbi.agents.reporter import reporter_node
from cbi.agents.state import (
    ConversationMode,
    ConversationState,
    HandoffTarget,
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
# Helper: drive multi-turn conversation
# =============================================================================


async def drive_conversation(
    mock_client: MagicMock,
    state: ConversationState,
    turns: list[tuple[str, str]],
) -> ConversationState:
    """
    Drive a multi-turn conversation through the reporter node.

    Args:
        mock_client: The mocked Anthropic client
        state: Starting state
        turns: List of (user_message, mock_llm_response_json) pairs

    Returns:
        Final conversation state
    """
    for user_msg, llm_response_json in turns:
        mock_client.messages.create.return_value = (
            create_mock_anthropic_response(llm_response_json)
        )
        state = add_message_to_state(state, MessageRole.user, user_msg)
        state = await reporter_node(state)
    return state


# =============================================================================
# Full English conversation flow
# =============================================================================


@pytest.mark.asyncio
async def test_full_english_conversation_cholera(patch_reporter_client):
    """
    Complete English conversation: listening → investigating → confirming → complete.

    Simulates a cholera report from Kassala.
    """
    state = create_initial_state("conv_full_en_001", "12345", Platform.telegram)

    turns = [
        # Turn 1: Greeting (stays in listening)
        (
            "Hello",
            make_reporter_response(
                response_text="Hello! How can I help you today?",
                language="en",
                health_signal=False,
                transition_to=None,
            ),
        ),
        # Turn 2: Health signal detected → investigating
        (
            "Many people in my village have severe diarrhea and vomiting",
            make_reporter_response(
                response_text="I'm sorry to hear that. Where is this happening?",
                language="en",
                health_signal=True,
                transition_to="investigating",
                extracted_data={
                    "symptoms": ["severe diarrhea", "vomiting"],
                },
                reasoning="Health signal: active illness in community",
            ),
        ),
        # Turn 3: Location provided
        (
            "In Kassala, near the market",
            make_reporter_response(
                response_text="When did the symptoms start?",
                language="en",
                health_signal=True,
                transition_to="investigating",
                extracted_data={
                    "location_text": "Kassala, near the market",
                },
            ),
        ),
        # Turn 4: Timing provided
        (
            "About three days ago",
            make_reporter_response(
                response_text="How many people are affected?",
                language="en",
                health_signal=True,
                transition_to="investigating",
                extracted_data={
                    "onset_text": "three days ago",
                },
            ),
        ),
        # Turn 5: Count and deaths → confirming
        (
            "About 8 people, and 2 children died",
            make_reporter_response(
                response_text="Let me confirm: severe diarrhea and vomiting in Kassala near the market, started 3 days ago, 8 affected, 2 deaths. Is this correct?",
                language="en",
                health_signal=True,
                transition_to="confirming",
                extracted_data={
                    "cases_count": 8,
                    "deaths_count": 2,
                    "suspected_disease": "cholera",
                    "reporter_relationship": "neighbor",
                },
            ),
        ),
        # Turn 6: Confirmation → complete
        (
            "Yes, that is correct",
            make_reporter_response(
                response_text="Thank you. Your report has been submitted to health officers.",
                language="en",
                health_signal=True,
                transition_to="complete",
                extracted_data={},
            ),
        ),
    ]

    result = await drive_conversation(patch_reporter_client, state, turns)

    # Verify final state
    assert result["current_mode"] == ConversationMode.complete.value
    assert result["handoff_to"] == HandoffTarget.surveillance.value
    assert result["language"] == Language.en.value

    # Verify all data was accumulated
    extracted = result["extracted_data"]
    assert "severe diarrhea" in extracted.get("symptoms", [])
    assert "vomiting" in extracted.get("symptoms", [])
    assert extracted.get("location_text") == "Kassala, near the market"
    assert extracted.get("onset_text") == "three days ago"
    assert extracted.get("cases_count") == 8
    assert extracted.get("deaths_count") == 2
    assert extracted.get("suspected_disease") == "cholera"

    # Verify message history has all turns (12 messages: 6 user + 6 assistant)
    assert len(result["messages"]) == 12
    assert result["turn_count"] == 6

    # Verify pending response is set for the user
    assert result.get("pending_response") is not None


# =============================================================================
# Full Arabic conversation flow
# =============================================================================


@pytest.mark.asyncio
async def test_full_arabic_conversation_dengue(patch_reporter_client):
    """
    Complete Arabic conversation: direct health signal → investigating → confirming → complete.
    """
    state = create_initial_state("conv_full_ar_001", "12345", Platform.telegram)

    turns = [
        # Turn 1: Arabic health signal → investigating immediately
        (
            "ابني عنده حمى شديدة وصداع وألم في المفاصل",
            make_reporter_response(
                response_text="آسف لسماع ذلك. أين أنتم؟",
                language="ar",
                health_signal=True,
                transition_to="investigating",
                extracted_data={
                    "symptoms": ["حمى شديدة", "صداع", "ألم في المفاصل"],
                    "reporter_relationship": "family",
                },
            ),
        ),
        # Turn 2: Location
        (
            "في بورتسودان",
            make_reporter_response(
                response_text="متى بدأت الأعراض؟",
                language="ar",
                health_signal=True,
                transition_to="investigating",
                extracted_data={
                    "location_text": "بورتسودان",
                },
            ),
        ),
        # Turn 3: Timing → confirming
        (
            "من يومين",
            make_reporter_response(
                response_text="خلاصة: حمى وصداع وألم مفاصل في بورتسودان من يومين. هل هذا صحيح؟",
                language="ar",
                health_signal=True,
                transition_to="confirming",
                extracted_data={
                    "onset_text": "يومين",
                    "cases_count": 1,
                    "suspected_disease": "dengue",
                },
            ),
        ),
        # Turn 4: Confirmation
        (
            "نعم صحيح",
            make_reporter_response(
                response_text="شكراً. تم إرسال تقريرك للمسؤولين الصحيين.",
                language="ar",
                health_signal=True,
                transition_to="complete",
                extracted_data={},
            ),
        ),
    ]

    result = await drive_conversation(patch_reporter_client, state, turns)

    assert result["current_mode"] == ConversationMode.complete.value
    assert result["language"] == Language.ar.value
    assert result["handoff_to"] == HandoffTarget.surveillance.value

    extracted = result["extracted_data"]
    assert "حمى شديدة" in extracted.get("symptoms", [])
    assert extracted.get("location_text") == "بورتسودان"
    assert extracted.get("suspected_disease") == "dengue"
    assert result["turn_count"] == 4


# =============================================================================
# Conversation with corrections
# =============================================================================


@pytest.mark.asyncio
async def test_conversation_user_corrects_information(patch_reporter_client):
    """
    Test that user can correct information during confirming mode.
    Agent should go back to investigating and update data.
    """
    state = create_initial_state("conv_correction_001", "12345", Platform.telegram)

    turns = [
        # Turn 1: Health signal
        (
            "There are sick people in my area with bloody diarrhea",
            make_reporter_response(
                response_text="That's concerning. Where is this?",
                language="en",
                health_signal=True,
                transition_to="investigating",
                extracted_data={"symptoms": ["bloody diarrhea"]},
            ),
        ),
        # Turn 2: Provide all info
        (
            "Omdurman, started yesterday, about 5 people",
            make_reporter_response(
                response_text="Let me confirm: bloody diarrhea in Omdurman, started yesterday, 5 people. Correct?",
                language="en",
                health_signal=True,
                transition_to="confirming",
                extracted_data={
                    "location_text": "Omdurman",
                    "onset_text": "yesterday",
                    "cases_count": 5,
                },
            ),
        ),
        # Turn 3: User corrects → back to investigating
        (
            "No, it's actually 10 people, not 5",
            make_reporter_response(
                response_text="Updated: 10 people affected. Anything else to correct?",
                language="en",
                health_signal=True,
                transition_to="confirming",
                extracted_data={
                    "cases_count": 10,
                },
            ),
        ),
        # Turn 4: Confirm corrected info
        (
            "Yes, that's correct now",
            make_reporter_response(
                response_text="Thank you. Report submitted.",
                language="en",
                health_signal=True,
                transition_to="complete",
                extracted_data={},
            ),
        ),
    ]

    result = await drive_conversation(patch_reporter_client, state, turns)

    assert result["current_mode"] == ConversationMode.complete.value
    # Cases count should be the corrected value
    assert result["extracted_data"]["cases_count"] == 10


# =============================================================================
# Conversation recovery after disconnect / error
# =============================================================================


@pytest.mark.asyncio
async def test_conversation_recovery_after_error(patch_reporter_client):
    """
    Test that conversation can continue after a transient error.

    Simulates: normal turn → API error → recovery on next message.
    """
    import anthropic

    state = create_initial_state("conv_recovery_001", "12345", Platform.telegram)

    # Turn 1: Normal message
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(
            make_reporter_response(
                response_text="How can I help?",
                language="en",
                health_signal=False,
            )
        )
    )
    state = add_message_to_state(state, MessageRole.user, "Hello")
    state = await reporter_node(state)
    assert state["current_mode"] == ConversationMode.listening.value

    # Turn 2: API error
    patch_reporter_client.messages.create.side_effect = (
        anthropic.APIConnectionError(request=None)
    )
    state_before_error = dict(state)
    state = add_message_to_state(state, MessageRole.user, "People are sick")
    state = await reporter_node(state)
    assert state["current_mode"] == ConversationMode.error.value

    # Turn 3: Recovery — reset state to listening mode (simulating new conversation)
    new_state = dict(state)
    new_state["current_mode"] = ConversationMode.listening.value
    new_state["error"] = None
    state = ConversationState(**new_state)

    patch_reporter_client.messages.create.side_effect = None
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(
            make_reporter_response(
                response_text="Sorry about that. People are sick? Tell me more.",
                language="en",
                health_signal=True,
                transition_to="investigating",
                extracted_data={"symptoms": ["unspecified illness"]},
            )
        )
    )
    state = add_message_to_state(state, MessageRole.user, "People are sick in my village")
    state = await reporter_node(state)

    # Should recover to investigating
    assert state["current_mode"] == ConversationMode.investigating.value


# =============================================================================
# Edge cases: conversation boundaries
# =============================================================================


@pytest.mark.asyncio
async def test_conversation_no_messages_returns_error(patch_reporter_client):
    """Reporter node with empty messages should set error state."""
    state = create_initial_state("conv_empty_001", "12345", Platform.telegram)
    # Don't add any messages

    result = await reporter_node(state)

    assert result["current_mode"] == ConversationMode.error.value
    assert "No messages" in result.get("error", "")


@pytest.mark.asyncio
async def test_conversation_preserves_state_across_turns(patch_reporter_client):
    """State data should accumulate correctly across multiple turns."""
    state = create_initial_state("conv_accum_001", "12345", Platform.telegram)

    # Turn 1: Symptoms
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(
            make_reporter_response(
                response_text="Where is this?",
                language="en",
                health_signal=True,
                transition_to="investigating",
                extracted_data={"symptoms": ["fever"]},
            )
        )
    )
    state = add_message_to_state(state, MessageRole.user, "People have fever")
    state = await reporter_node(state)
    assert state["extracted_data"]["symptoms"] == ["fever"]

    # Turn 2: More symptoms (should merge)
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(
            make_reporter_response(
                response_text="When did this start?",
                language="en",
                health_signal=True,
                transition_to="investigating",
                extracted_data={"symptoms": ["vomiting"], "location_text": "Bahri"},
            )
        )
    )
    state = add_message_to_state(state, MessageRole.user, "Also vomiting, in Bahri")
    state = await reporter_node(state)

    # Both symptoms should be present
    assert "fever" in state["extracted_data"]["symptoms"]
    assert "vomiting" in state["extracted_data"]["symptoms"]
    assert state["extracted_data"]["location_text"] == "Bahri"

    # Turn 3: Timing
    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(
            make_reporter_response(
                response_text="How many people?",
                language="en",
                health_signal=True,
                transition_to="investigating",
                extracted_data={"onset_text": "since Monday"},
            )
        )
    )
    state = add_message_to_state(state, MessageRole.user, "Since Monday")
    state = await reporter_node(state)

    # All accumulated data should be present
    assert "fever" in state["extracted_data"]["symptoms"]
    assert "vomiting" in state["extracted_data"]["symptoms"]
    assert state["extracted_data"]["location_text"] == "Bahri"
    assert state["extracted_data"]["onset_text"] == "since Monday"


@pytest.mark.asyncio
async def test_long_conversation_turn_count(patch_reporter_client):
    """Turn count should accurately reflect user messages only."""
    state = create_initial_state("conv_turns_001", "12345", Platform.telegram)

    for i in range(5):
        patch_reporter_client.messages.create.return_value = (
            create_mock_anthropic_response(
                make_reporter_response(
                    response_text=f"Response {i}",
                    language="en",
                    health_signal=False,
                )
            )
        )
        state = add_message_to_state(state, MessageRole.user, f"Message {i}")
        state = await reporter_node(state)

    assert state["turn_count"] == 5
    # 5 user + 5 assistant = 10 messages
    assert len(state["messages"]) == 10


# =============================================================================
# Test WhatsApp platform conversation
# =============================================================================


@pytest.mark.asyncio
async def test_whatsapp_conversation(patch_reporter_client):
    """Conversation should work identically on WhatsApp platform."""
    state = create_initial_state(
        "conv_wa_001", "249123456789", Platform.whatsapp
    )

    patch_reporter_client.messages.create.return_value = (
        create_mock_anthropic_response(
            make_reporter_response(
                response_text="I'm sorry. Where is this happening?",
                language="en",
                health_signal=True,
                transition_to="investigating",
                extracted_data={"symptoms": ["diarrhea"]},
            )
        )
    )

    state = add_message_to_state(
        state, MessageRole.user, "People have diarrhea in my area"
    )
    result = await reporter_node(state)

    assert result["platform"] == Platform.whatsapp.value
    assert result["current_mode"] == ConversationMode.investigating.value


# =============================================================================
# Graph routing tests
# =============================================================================


class TestGraphRouting:
    """Test graph routing functions for correctness."""

    def test_route_after_reporter_to_send_response(self):
        """Reporter with pending response should route to send_response."""
        from cbi.agents.graph import route_after_reporter

        state = ConversationState(
            conversation_id="test",
            reporter_phone="123",
            platform="telegram",
            messages=[],
            current_mode=ConversationMode.investigating.value,
            language="en",
            extracted_data={},
            classification={},
            pending_response="Some response",
            handoff_to=None,
            error=None,
            created_at="",
            updated_at="",
            turn_count=1,
        )
        assert route_after_reporter(state) == "send_response"

    def test_route_after_reporter_error_to_end(self):
        """Reporter with error should route to END."""
        from cbi.agents.graph import route_after_reporter

        state = ConversationState(
            conversation_id="test",
            reporter_phone="123",
            platform="telegram",
            messages=[],
            current_mode=ConversationMode.error.value,
            language="en",
            extracted_data={},
            classification={},
            pending_response=None,
            handoff_to=None,
            error="some error",
            created_at="",
            updated_at="",
            turn_count=1,
        )
        assert route_after_reporter(state) == "__end__"

    def test_route_after_send_response_to_surveillance(self):
        """After sending response for complete conversation, route to surveillance."""
        from cbi.agents.graph import route_after_send_response

        state = ConversationState(
            conversation_id="test",
            reporter_phone="123",
            platform="telegram",
            messages=[],
            current_mode=ConversationMode.complete.value,
            language="en",
            extracted_data={},
            classification={},
            pending_response=None,
            handoff_to=HandoffTarget.surveillance.value,
            error=None,
            created_at="",
            updated_at="",
            turn_count=1,
        )
        assert route_after_send_response(state) == "surveillance"

    def test_route_after_send_response_to_end(self):
        """After sending response for non-complete conversation, route to END."""
        from cbi.agents.graph import route_after_send_response

        state = ConversationState(
            conversation_id="test",
            reporter_phone="123",
            platform="telegram",
            messages=[],
            current_mode=ConversationMode.investigating.value,
            language="en",
            extracted_data={},
            classification={},
            pending_response=None,
            handoff_to=None,
            error=None,
            created_at="",
            updated_at="",
            turn_count=1,
        )
        assert route_after_send_response(state) == "__end__"

    def test_route_after_surveillance_critical_to_analyst(self):
        """Critical urgency after surveillance should route to analyst."""
        from cbi.agents.graph import route_after_surveillance

        state = ConversationState(
            conversation_id="test",
            reporter_phone="123",
            platform="telegram",
            messages=[],
            current_mode=ConversationMode.complete.value,
            language="en",
            extracted_data={},
            classification={"urgency": "critical"},
            pending_response=None,
            handoff_to=None,
            error=None,
            created_at="",
            updated_at="",
            turn_count=1,
        )
        assert route_after_surveillance(state) == "analyst"

    def test_route_after_surveillance_high_to_analyst(self):
        """High urgency should also route to analyst."""
        from cbi.agents.graph import route_after_surveillance

        state = ConversationState(
            conversation_id="test",
            reporter_phone="123",
            platform="telegram",
            messages=[],
            current_mode=ConversationMode.complete.value,
            language="en",
            extracted_data={},
            classification={"urgency": "high"},
            pending_response=None,
            handoff_to=None,
            error=None,
            created_at="",
            updated_at="",
            turn_count=1,
        )
        assert route_after_surveillance(state) == "analyst"

    def test_route_after_surveillance_medium_to_notification(self):
        """Medium urgency should route to notification."""
        from cbi.agents.graph import route_after_surveillance

        state = ConversationState(
            conversation_id="test",
            reporter_phone="123",
            platform="telegram",
            messages=[],
            current_mode=ConversationMode.complete.value,
            language="en",
            extracted_data={},
            classification={"urgency": "medium"},
            pending_response=None,
            handoff_to=None,
            error=None,
            created_at="",
            updated_at="",
            turn_count=1,
        )
        assert route_after_surveillance(state) == "send_notification"

    def test_route_after_surveillance_low_to_end(self):
        """Low urgency should route to END."""
        from cbi.agents.graph import route_after_surveillance

        state = ConversationState(
            conversation_id="test",
            reporter_phone="123",
            platform="telegram",
            messages=[],
            current_mode=ConversationMode.complete.value,
            language="en",
            extracted_data={},
            classification={"urgency": "low"},
            pending_response=None,
            handoff_to=None,
            error=None,
            created_at="",
            updated_at="",
            turn_count=1,
        )
        assert route_after_surveillance(state) == "__end__"
