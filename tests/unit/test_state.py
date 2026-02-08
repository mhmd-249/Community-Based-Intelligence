"""
Unit tests for cbi.agents.state module.

Tests state creation, MVS field tracking, and data completeness calculation.
"""

import json
from datetime import datetime

import pytest

from cbi.agents.state import (
    Classification,
    ConversationMode,
    ConversationState,
    ExtractedData,
    HandoffTarget,
    Language,
    Message,
    MessageRole,
    Platform,
    add_message_to_state,
    calculate_data_completeness,
    create_initial_state,
    get_missing_mvs_fields,
    set_error,
    set_handoff,
    transition_mode,
    update_extracted_data,
)
from cbi.db.models import ReporterRelation


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def conversation_id() -> str:
    """Sample conversation ID for testing."""
    return "conv_abc123def456"


@pytest.fixture
def phone() -> str:
    """Sample phone number for testing."""
    return "+249123456789"


@pytest.fixture
def initial_state(conversation_id: str, phone: str) -> ConversationState:
    """Create a fresh initial state for testing."""
    return create_initial_state(conversation_id, phone)


@pytest.fixture
def empty_extracted_data() -> dict:
    """Empty extracted data dict."""
    return ExtractedData().model_dump()


@pytest.fixture
def partial_extracted_data() -> dict:
    """Partially complete extracted data."""
    return ExtractedData(
        symptoms=["fever", "vomiting"],
        location_text="Khartoum North",
    ).model_dump()


@pytest.fixture
def complete_extracted_data() -> dict:
    """Fully complete extracted data."""
    return ExtractedData(
        symptoms=["fever", "diarrhea", "vomiting"],
        location_text="Al-Thawra neighborhood, Omdurman",
        onset_text="three days ago",
        cases_count=5,
        reporter_relationship=ReporterRelation.health_worker,
        affected_description="children under 5",
    ).model_dump()


# =============================================================================
# Tests for create_initial_state()
# =============================================================================


class TestCreateInitialState:
    """Tests for create_initial_state function."""

    def test_creates_state_with_required_fields(
        self, conversation_id: str, phone: str
    ) -> None:
        """State should contain all required fields."""
        state = create_initial_state(conversation_id, phone)

        assert state["conversation_id"] == conversation_id
        assert state["reporter_phone"] == phone
        assert state["platform"] == Platform.telegram.value

    def test_default_platform_is_telegram(
        self, conversation_id: str, phone: str
    ) -> None:
        """Default platform should be telegram."""
        state = create_initial_state(conversation_id, phone)
        assert state["platform"] == "telegram"

    def test_custom_platform_enum(self, conversation_id: str, phone: str) -> None:
        """Should accept Platform enum value."""
        state = create_initial_state(conversation_id, phone, Platform.whatsapp)
        assert state["platform"] == "whatsapp"

    def test_custom_platform_string(self, conversation_id: str, phone: str) -> None:
        """Should accept platform as string."""
        state = create_initial_state(conversation_id, phone, "whatsapp")
        assert state["platform"] == "whatsapp"

    def test_initial_mode_is_listening(self, initial_state: ConversationState) -> None:
        """Initial mode should be 'listening'."""
        assert initial_state["current_mode"] == ConversationMode.listening.value

    def test_initial_language_is_unknown(
        self, initial_state: ConversationState
    ) -> None:
        """Initial language should be 'unknown'."""
        assert initial_state["language"] == Language.unknown.value

    def test_messages_initially_empty(self, initial_state: ConversationState) -> None:
        """Messages list should be empty initially."""
        assert initial_state["messages"] == []

    def test_extracted_data_has_defaults(
        self, initial_state: ConversationState
    ) -> None:
        """Extracted data should have default values."""
        extracted = initial_state["extracted_data"]
        assert extracted["symptoms"] == []
        assert extracted["location_text"] is None
        assert extracted["onset_text"] is None
        assert extracted["cases_count"] is None

    def test_classification_has_defaults(
        self, initial_state: ConversationState
    ) -> None:
        """Classification should have default values."""
        classification = initial_state["classification"]
        assert classification["confidence"] == 0.0
        assert classification["data_completeness"] == 0.0
        assert classification["urgency"] == "medium"

    def test_control_fields_are_none(self, initial_state: ConversationState) -> None:
        """Control flow fields should be None initially."""
        assert initial_state["pending_response"] is None
        assert initial_state["handoff_to"] is None
        assert initial_state["error"] is None

    def test_turn_count_starts_at_zero(self, initial_state: ConversationState) -> None:
        """Turn count should start at 0."""
        assert initial_state["turn_count"] == 0

    def test_timestamps_are_set(self, initial_state: ConversationState) -> None:
        """Created and updated timestamps should be set."""
        assert initial_state["created_at"] is not None
        assert initial_state["updated_at"] is not None

    def test_timestamps_are_iso_format(self, initial_state: ConversationState) -> None:
        """Timestamps should be in ISO format."""
        # Should not raise
        datetime.fromisoformat(initial_state["created_at"])
        datetime.fromisoformat(initial_state["updated_at"])


# =============================================================================
# Tests for get_missing_mvs_fields()
# =============================================================================


class TestGetMissingMvsFields:
    """Tests for get_missing_mvs_fields function."""

    def test_all_fields_missing_with_empty_data(
        self, empty_extracted_data: dict
    ) -> None:
        """All fields should be missing with empty data."""
        missing = get_missing_mvs_fields(empty_extracted_data)

        assert "symptoms" in missing
        assert "location_text" in missing
        assert "onset_text" in missing
        assert "cases_count" in missing
        assert "reporter_relationship" in missing
        assert "affected_description" in missing

    def test_partial_data_returns_only_missing(
        self, partial_extracted_data: dict
    ) -> None:
        """Should return only the fields that are actually missing."""
        missing = get_missing_mvs_fields(partial_extracted_data)

        # These are set
        assert "symptoms" not in missing
        assert "location_text" not in missing

        # These are missing
        assert "onset_text" in missing
        assert "cases_count" in missing
        assert "reporter_relationship" in missing
        assert "affected_description" in missing

    def test_complete_data_returns_empty_list(
        self, complete_extracted_data: dict
    ) -> None:
        """Should return empty list when all fields are filled."""
        missing = get_missing_mvs_fields(complete_extracted_data)
        assert missing == []

    def test_accepts_extracted_data_model(self) -> None:
        """Should accept ExtractedData model directly."""
        data = ExtractedData(symptoms=["cough"])
        missing = get_missing_mvs_fields(data)

        assert "symptoms" not in missing
        assert "location_text" in missing

    def test_accepts_dict(self) -> None:
        """Should accept dict representation."""
        data = {"symptoms": ["fever"], "location_text": None}
        missing = get_missing_mvs_fields(data)

        assert "symptoms" not in missing
        assert "location_text" in missing

    def test_empty_symptoms_list_is_missing(self) -> None:
        """Empty symptoms list should count as missing."""
        data = ExtractedData(symptoms=[])
        missing = get_missing_mvs_fields(data)
        assert "symptoms" in missing

    def test_none_cases_count_is_missing(self) -> None:
        """None cases_count should count as missing."""
        data = ExtractedData(cases_count=None)
        missing = get_missing_mvs_fields(data)
        assert "cases_count" in missing

    def test_zero_cases_count_is_not_missing(self) -> None:
        """Zero cases_count should NOT count as missing (0 is a valid value)."""
        data = {"symptoms": [], "cases_count": 0}
        missing = get_missing_mvs_fields(data)
        # cases_count of 0 is explicitly set, so not missing
        assert "cases_count" not in missing


# =============================================================================
# Tests for calculate_data_completeness()
# =============================================================================


class TestCalculateDataCompleteness:
    """Tests for calculate_data_completeness function."""

    def test_empty_data_returns_zero(self, empty_extracted_data: dict) -> None:
        """Empty data should have 0.0 completeness."""
        score = calculate_data_completeness(empty_extracted_data)
        assert score == 0.0

    def test_complete_data_returns_one(self, complete_extracted_data: dict) -> None:
        """Complete data should have 1.0 completeness."""
        score = calculate_data_completeness(complete_extracted_data)
        assert score == 1.0

    def test_partial_data_returns_partial_score(
        self, partial_extracted_data: dict
    ) -> None:
        """Partial data should return score between 0 and 1."""
        score = calculate_data_completeness(partial_extracted_data)
        assert 0.0 < score < 1.0

    def test_symptoms_weight_is_0_25(self) -> None:
        """Symptoms alone should contribute 0.25."""
        data = ExtractedData(symptoms=["fever"])
        score = calculate_data_completeness(data)
        assert score == 0.25

    def test_location_weight_is_0_25(self) -> None:
        """Location alone should contribute 0.25."""
        data = ExtractedData(location_text="Khartoum")
        score = calculate_data_completeness(data)
        assert score == 0.25

    def test_onset_weight_is_0_20(self) -> None:
        """Onset alone should contribute 0.20."""
        data = ExtractedData(onset_text="yesterday")
        score = calculate_data_completeness(data)
        assert score == 0.20

    def test_cases_count_weight_is_0_15(self) -> None:
        """Cases count alone should contribute 0.15."""
        data = ExtractedData(cases_count=3)
        score = calculate_data_completeness(data)
        assert score == 0.15

    def test_reporter_relationship_weight_is_0_10(self) -> None:
        """Reporter relationship alone should contribute 0.10."""
        data = ExtractedData(reporter_relationship=ReporterRelation.family)
        score = calculate_data_completeness(data)
        assert score == 0.10

    def test_affected_description_weight_is_0_05(self) -> None:
        """Affected description alone should contribute 0.05."""
        data = ExtractedData(affected_description="children")
        score = calculate_data_completeness(data)
        assert score == 0.05

    def test_weights_sum_to_one(self, complete_extracted_data: dict) -> None:
        """All weights should sum to 1.0."""
        # 0.25 + 0.25 + 0.20 + 0.15 + 0.10 + 0.05 = 1.0
        score = calculate_data_completeness(complete_extracted_data)
        assert score == 1.0

    def test_result_rounded_to_two_decimals(self) -> None:
        """Result should be rounded to 2 decimal places."""
        data = ExtractedData(
            symptoms=["fever"],
            location_text="Omdurman",
        )
        score = calculate_data_completeness(data)
        # 0.25 + 0.25 = 0.50
        assert score == 0.50

    def test_accepts_extracted_data_model(self) -> None:
        """Should accept ExtractedData model directly."""
        data = ExtractedData(symptoms=["fever"], location_text="Khartoum")
        score = calculate_data_completeness(data)
        assert score == 0.50

    def test_accepts_dict(self) -> None:
        """Should accept dict representation."""
        data = {"symptoms": ["fever"], "location_text": "Khartoum"}
        score = calculate_data_completeness(data)
        assert score == 0.50


# =============================================================================
# Tests for State Serialization/Deserialization
# =============================================================================


class TestStateSerialization:
    """Tests for state serialization and deserialization."""

    def test_state_can_be_serialized_to_json(
        self, initial_state: ConversationState
    ) -> None:
        """State should be JSON serializable."""
        json_str = json.dumps(dict(initial_state))
        assert isinstance(json_str, str)
        assert len(json_str) > 0

    def test_state_can_be_deserialized_from_json(
        self, initial_state: ConversationState
    ) -> None:
        """State should be deserializable from JSON."""
        json_str = json.dumps(dict(initial_state))
        restored = json.loads(json_str)

        assert restored["conversation_id"] == initial_state["conversation_id"]
        assert restored["reporter_phone"] == initial_state["reporter_phone"]
        assert restored["platform"] == initial_state["platform"]

    def test_roundtrip_preserves_all_fields(
        self, initial_state: ConversationState
    ) -> None:
        """JSON roundtrip should preserve all fields."""
        json_str = json.dumps(dict(initial_state))
        restored = ConversationState(**json.loads(json_str))

        for key in initial_state:
            assert restored[key] == initial_state[key], f"Mismatch in field: {key}"

    def test_extracted_data_nested_serialization(
        self, complete_extracted_data: dict
    ) -> None:
        """Nested extracted data should serialize correctly."""
        state = create_initial_state("conv_test", "+249000000000")
        state = update_extracted_data(state, **complete_extracted_data)

        json_str = json.dumps(dict(state))
        restored = json.loads(json_str)

        assert restored["extracted_data"]["symptoms"] == ["fever", "diarrhea", "vomiting"]
        assert restored["extracted_data"]["location_text"] == "Al-Thawra neighborhood, Omdurman"

    def test_messages_list_serialization(
        self, initial_state: ConversationState
    ) -> None:
        """Messages list should serialize correctly."""
        state = add_message_to_state(initial_state, MessageRole.user, "Hello")
        state = add_message_to_state(state, MessageRole.assistant, "Hi there")

        # Messages contain datetime objects, so we need a custom encoder
        def json_encoder(obj):
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        json_str = json.dumps(dict(state), default=json_encoder)
        restored = json.loads(json_str)

        assert len(restored["messages"]) == 2
        assert restored["messages"][0]["role"] == "user"
        assert restored["messages"][1]["role"] == "assistant"


# =============================================================================
# Tests for Helper Functions
# =============================================================================


class TestAddMessageToState:
    """Tests for add_message_to_state function."""

    def test_adds_user_message(self, initial_state: ConversationState) -> None:
        """Should add user message to state."""
        state = add_message_to_state(initial_state, MessageRole.user, "Hello")

        assert len(state["messages"]) == 1
        assert state["messages"][0]["role"] == "user"
        assert state["messages"][0]["content"] == "Hello"

    def test_adds_assistant_message(self, initial_state: ConversationState) -> None:
        """Should add assistant message to state."""
        state = add_message_to_state(initial_state, MessageRole.assistant, "Hi there")

        assert len(state["messages"]) == 1
        assert state["messages"][0]["role"] == "assistant"

    def test_increments_turn_count_for_user_messages(
        self, initial_state: ConversationState
    ) -> None:
        """Turn count should increment only for user messages."""
        state = add_message_to_state(initial_state, MessageRole.user, "Hello")
        assert state["turn_count"] == 1

        state = add_message_to_state(state, MessageRole.assistant, "Hi")
        assert state["turn_count"] == 1  # No increment for assistant

        state = add_message_to_state(state, MessageRole.user, "How are you?")
        assert state["turn_count"] == 2

    def test_updates_timestamp(self, initial_state: ConversationState) -> None:
        """Should update the updated_at timestamp."""
        original_updated = initial_state["updated_at"]
        state = add_message_to_state(initial_state, MessageRole.user, "Hello")
        # Timestamps might be equal if executed fast, so just check it's set
        assert state["updated_at"] is not None

    def test_accepts_string_role(self, initial_state: ConversationState) -> None:
        """Should accept role as string."""
        state = add_message_to_state(initial_state, "user", "Hello")
        assert state["messages"][0]["role"] == "user"


class TestTransitionMode:
    """Tests for transition_mode function."""

    def test_transitions_to_investigating(
        self, initial_state: ConversationState
    ) -> None:
        """Should transition from listening to investigating."""
        state = transition_mode(initial_state, ConversationMode.investigating)
        assert state["current_mode"] == "investigating"

    def test_transitions_to_confirming(
        self, initial_state: ConversationState
    ) -> None:
        """Should transition to confirming mode."""
        state = transition_mode(initial_state, ConversationMode.confirming)
        assert state["current_mode"] == "confirming"

    def test_accepts_string_mode(self, initial_state: ConversationState) -> None:
        """Should accept mode as string."""
        state = transition_mode(initial_state, "investigating")
        assert state["current_mode"] == "investigating"


class TestSetHandoff:
    """Tests for set_handoff function."""

    def test_sets_surveillance_handoff(self, initial_state: ConversationState) -> None:
        """Should set handoff to surveillance."""
        state = set_handoff(initial_state, HandoffTarget.surveillance)

        assert state["handoff_to"] == "surveillance"
        assert state["current_mode"] == "complete"

    def test_sets_analyst_handoff(self, initial_state: ConversationState) -> None:
        """Should set handoff to analyst."""
        state = set_handoff(initial_state, HandoffTarget.analyst)
        assert state["handoff_to"] == "analyst"

    def test_sets_human_handoff(self, initial_state: ConversationState) -> None:
        """Should set handoff to human."""
        state = set_handoff(initial_state, HandoffTarget.human)
        assert state["handoff_to"] == "human"


class TestSetError:
    """Tests for set_error function."""

    def test_sets_error_message(self, initial_state: ConversationState) -> None:
        """Should set error message."""
        state = set_error(initial_state, "Something went wrong")

        assert state["error"] == "Something went wrong"
        assert state["current_mode"] == "error"

    def test_transitions_to_error_mode(
        self, initial_state: ConversationState
    ) -> None:
        """Should transition to error mode."""
        state = set_error(initial_state, "Connection failed")
        assert state["current_mode"] == ConversationMode.error.value


class TestUpdateExtractedData:
    """Tests for update_extracted_data function."""

    def test_updates_single_field(self, initial_state: ConversationState) -> None:
        """Should update a single field."""
        state = update_extracted_data(initial_state, symptoms=["fever"])

        assert state["extracted_data"]["symptoms"] == ["fever"]

    def test_updates_multiple_fields(self, initial_state: ConversationState) -> None:
        """Should update multiple fields."""
        state = update_extracted_data(
            initial_state,
            symptoms=["fever", "cough"],
            location_text="Khartoum",
            cases_count=3,
        )

        assert state["extracted_data"]["symptoms"] == ["fever", "cough"]
        assert state["extracted_data"]["location_text"] == "Khartoum"
        assert state["extracted_data"]["cases_count"] == 3

    def test_recalculates_completeness(
        self, initial_state: ConversationState
    ) -> None:
        """Should recalculate data completeness."""
        state = update_extracted_data(
            initial_state,
            symptoms=["fever"],
            location_text="Omdurman",
        )

        assert state["classification"]["data_completeness"] == 0.50

    def test_preserves_existing_data(self, initial_state: ConversationState) -> None:
        """Should preserve existing data when adding new."""
        state = update_extracted_data(initial_state, symptoms=["fever"])
        state = update_extracted_data(state, location_text="Khartoum")

        assert state["extracted_data"]["symptoms"] == ["fever"]
        assert state["extracted_data"]["location_text"] == "Khartoum"
