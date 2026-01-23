"""
LangGraph state schema for CBI conversation agents.

Defines the ConversationState TypedDict used by LangGraph to manage
conversation flow through the Reporter, Surveillance, and Analyst agents.
"""

from datetime import date, datetime
from enum import Enum
from typing import TypedDict

from pydantic import BaseModel, Field

from cbi.db.models import (
    AlertType,
    DiseaseType,
    ReporterRelation,
    UrgencyLevel,
)

# =============================================================================
# Enums specific to conversation state
# =============================================================================


class MessageRole(str, Enum):
    """Role of a message in the conversation."""

    user = "user"
    assistant = "assistant"
    system = "system"


class ConversationMode(str, Enum):
    """Operating mode of the Reporter Agent."""

    listening = "listening"
    investigating = "investigating"
    confirming = "confirming"
    complete = "complete"
    error = "error"


class Language(str, Enum):
    """Detected language of the conversation."""

    ar = "ar"
    en = "en"
    unknown = "unknown"


class Platform(str, Enum):
    """Messaging platform source."""

    telegram = "telegram"
    whatsapp = "whatsapp"


class HandoffTarget(str, Enum):
    """Target agent for handoff."""

    surveillance = "surveillance"
    analyst = "analyst"
    human = "human"


# =============================================================================
# Pydantic Models for Nested Data
# =============================================================================


class Message(BaseModel):
    """A single message in the conversation history."""

    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_id: str | None = None

    class Config:
        use_enum_values = True


class ExtractedData(BaseModel):
    """
    Data extracted from the conversation (MVS - Minimum Viable Signal).

    What: symptoms, suspected_disease
    Where: location_text, location_normalized, location_coords
    When: onset_text, onset_date
    Who: cases_count, deaths_count, affected_description, reporter_relationship
    """

    # What - Health signal
    symptoms: list[str] = Field(default_factory=list)
    suspected_disease: DiseaseType = DiseaseType.unknown

    # Where - Location
    location_text: str | None = None
    location_normalized: str | None = None
    location_coords: tuple[float, float] | None = None  # (lat, lon)

    # When - Timing
    onset_text: str | None = None
    onset_date: date | None = None

    # Who - Affected population
    cases_count: int | None = None
    deaths_count: int | None = None
    affected_description: str | None = None
    reporter_relationship: ReporterRelation | None = None

    class Config:
        use_enum_values = True


class Classification(BaseModel):
    """
    Classification results from the Surveillance Agent.

    Used to determine urgency, alert type, and required actions.
    """

    suspected_disease: DiseaseType = DiseaseType.unknown
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    data_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    urgency: UrgencyLevel = UrgencyLevel.medium
    alert_type: AlertType = AlertType.single_case
    reasoning: str | None = None
    recommended_actions: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)

    class Config:
        use_enum_values = True


# =============================================================================
# TypedDict for LangGraph State
# =============================================================================


class ConversationState(TypedDict, total=False):
    """
    LangGraph state for managing conversation flow.

    This TypedDict defines all fields that can be tracked across
    agent nodes in the conversation graph.

    Using total=False allows partial state updates in LangGraph.
    """

    # Identifiers
    conversation_id: str
    reporter_phone: str
    platform: str  # Platform enum value

    # Conversation history and mode
    messages: list[dict]  # List of Message model dicts
    current_mode: str  # ConversationMode enum value
    language: str  # Language enum value

    # Extracted data (MVS)
    extracted_data: dict  # ExtractedData model dict

    # Classification (from Surveillance Agent)
    classification: dict  # Classification model dict

    # Control flow
    pending_response: str | None
    handoff_to: str | None  # HandoffTarget enum value
    error: str | None

    # Metadata
    created_at: str  # ISO format datetime
    updated_at: str  # ISO format datetime
    turn_count: int


# =============================================================================
# Helper Functions
# =============================================================================


def create_initial_state(
    conversation_id: str,
    phone: str,
    platform: Platform | str = Platform.telegram,
) -> ConversationState:
    """
    Create a new ConversationState with sensible defaults.

    Args:
        conversation_id: Unique identifier for the conversation
        phone: Reporter's phone number (will be hashed for storage)
        platform: Messaging platform (telegram or whatsapp)

    Returns:
        Initial ConversationState ready for use in LangGraph
    """
    now = datetime.utcnow().isoformat()
    platform_value = platform.value if isinstance(platform, Platform) else platform

    return ConversationState(
        # Identifiers
        conversation_id=conversation_id,
        reporter_phone=phone,
        platform=platform_value,
        # Conversation
        messages=[],
        current_mode=ConversationMode.listening.value,
        language=Language.unknown.value,
        # Extracted data
        extracted_data=ExtractedData().model_dump(),
        # Classification (empty until Surveillance Agent processes)
        classification=Classification().model_dump(),
        # Control flow
        pending_response=None,
        handoff_to=None,
        error=None,
        # Metadata
        created_at=now,
        updated_at=now,
        turn_count=0,
    )


# MVS field definitions with weights for completeness calculation
MVS_FIELDS: dict[str, float] = {
    "symptoms": 0.25,  # What - most important
    "location_text": 0.25,  # Where - critical for response
    "onset_text": 0.20,  # When - important for timeline
    "cases_count": 0.15,  # Who - scale assessment
    "reporter_relationship": 0.10,  # Who - source credibility
    "affected_description": 0.05,  # Who - context
}


def get_missing_mvs_fields(extracted: ExtractedData | dict) -> list[str]:
    """
    Identify which MVS fields are still missing from extracted data.

    Args:
        extracted: ExtractedData model or dict representation

    Returns:
        List of field names that are missing or empty
    """
    if isinstance(extracted, dict):
        extracted = ExtractedData(**extracted)

    missing = []

    # Check each MVS field
    if not extracted.symptoms:
        missing.append("symptoms")

    if not extracted.location_text:
        missing.append("location_text")

    if not extracted.onset_text:
        missing.append("onset_text")

    if extracted.cases_count is None:
        missing.append("cases_count")

    if extracted.reporter_relationship is None:
        missing.append("reporter_relationship")

    if not extracted.affected_description:
        missing.append("affected_description")

    return missing


def calculate_data_completeness(extracted: ExtractedData | dict) -> float:
    """
    Calculate the completeness score (0.0 to 1.0) for extracted data.

    Uses weighted scoring based on MVS field importance:
    - symptoms: 25% (what happened)
    - location_text: 25% (where)
    - onset_text: 20% (when)
    - cases_count: 15% (scale)
    - reporter_relationship: 10% (source context)
    - affected_description: 5% (additional context)

    Args:
        extracted: ExtractedData model or dict representation

    Returns:
        Completeness score from 0.0 to 1.0
    """
    if isinstance(extracted, dict):
        extracted = ExtractedData(**extracted)

    score = 0.0

    # Check symptoms (list)
    if extracted.symptoms:
        score += MVS_FIELDS["symptoms"]

    # Check location_text
    if extracted.location_text:
        score += MVS_FIELDS["location_text"]

    # Check onset_text
    if extracted.onset_text:
        score += MVS_FIELDS["onset_text"]

    # Check cases_count
    if extracted.cases_count is not None:
        score += MVS_FIELDS["cases_count"]

    # Check reporter_relationship
    if extracted.reporter_relationship is not None:
        score += MVS_FIELDS["reporter_relationship"]

    # Check affected_description
    if extracted.affected_description:
        score += MVS_FIELDS["affected_description"]

    return round(score, 2)


def add_message_to_state(
    state: ConversationState,
    role: MessageRole | str,
    content: str,
    message_id: str | None = None,
) -> ConversationState:
    """
    Add a new message to the conversation state.

    Args:
        state: Current conversation state
        role: Message role (user, assistant, system)
        message_id: Optional platform-specific message ID

    Returns:
        Updated state with new message appended
    """
    role_value = role.value if isinstance(role, MessageRole) else role

    message = Message(
        role=MessageRole(role_value),
        content=content,
        message_id=message_id,
    )

    messages = list(state.get("messages", []))
    messages.append(message.model_dump())

    # Create new state with updated fields
    new_state = dict(state)
    new_state["messages"] = messages
    new_state["updated_at"] = datetime.utcnow().isoformat()
    new_state["turn_count"] = state.get("turn_count", 0) + (
        1 if role_value == "user" else 0
    )

    return ConversationState(**new_state)


def update_extracted_data(
    state: ConversationState,
    **updates: dict,
) -> ConversationState:
    """
    Update extracted data fields in the state.

    Args:
        state: Current conversation state
        **updates: Field updates for ExtractedData

    Returns:
        Updated state with merged extracted data
    """
    current = dict(state.get("extracted_data", {}))
    merged = {**current, **updates}

    # Recalculate completeness
    completeness = calculate_data_completeness(merged)

    # Update classification with new completeness
    classification = dict(state.get("classification", {}))
    classification["data_completeness"] = completeness

    # Create new state with updated fields
    new_state = dict(state)
    new_state["extracted_data"] = merged
    new_state["classification"] = classification
    new_state["updated_at"] = datetime.utcnow().isoformat()

    return ConversationState(**new_state)


def transition_mode(
    state: ConversationState,
    new_mode: ConversationMode | str,
) -> ConversationState:
    """
    Transition the conversation to a new mode.

    Args:
        state: Current conversation state
        new_mode: Target mode to transition to

    Returns:
        Updated state with new mode
    """
    mode_value = new_mode.value if isinstance(new_mode, ConversationMode) else new_mode

    new_state = dict(state)
    new_state["current_mode"] = mode_value
    new_state["updated_at"] = datetime.utcnow().isoformat()

    return ConversationState(**new_state)


def set_handoff(
    state: ConversationState,
    target: HandoffTarget | str,
) -> ConversationState:
    """
    Set the handoff target for the conversation.

    Args:
        state: Current conversation state
        target: Agent or human to hand off to

    Returns:
        Updated state with handoff target set
    """
    target_value = target.value if isinstance(target, HandoffTarget) else target

    new_state = dict(state)
    new_state["handoff_to"] = target_value
    new_state["current_mode"] = ConversationMode.complete.value
    new_state["updated_at"] = datetime.utcnow().isoformat()

    return ConversationState(**new_state)


def set_error(
    state: ConversationState,
    error_message: str,
) -> ConversationState:
    """
    Set an error state for the conversation.

    Args:
        state: Current conversation state
        error_message: Description of the error

    Returns:
        Updated state with error set and mode changed to error
    """
    new_state = dict(state)
    new_state["error"] = error_message
    new_state["current_mode"] = ConversationMode.error.value
    new_state["updated_at"] = datetime.utcnow().isoformat()

    return ConversationState(**new_state)
