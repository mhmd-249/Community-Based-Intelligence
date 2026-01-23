"""
CBI Agent modules.

Contains the LangGraph-based conversation agents:
- Reporter Agent: Handles incoming conversations, collects MVS data
- Surveillance Agent: Classifies reports, detects patterns
- Analyst Agent: Natural language queries, visualizations
"""

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

__all__ = [
    # Enums
    "MessageRole",
    "ConversationMode",
    "Language",
    "Platform",
    "HandoffTarget",
    # Pydantic models
    "Message",
    "ExtractedData",
    "Classification",
    # TypedDict
    "ConversationState",
    # Helper functions
    "create_initial_state",
    "get_missing_mvs_fields",
    "calculate_data_completeness",
    "add_message_to_state",
    "update_extracted_data",
    "transition_mode",
    "set_handoff",
    "set_error",
]
