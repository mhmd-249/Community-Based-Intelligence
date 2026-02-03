"""
CBI Agent modules.

Contains the LangGraph-based conversation agents:
- Reporter Agent: Handles incoming conversations, collects MVS data
- Surveillance Agent: Classifies reports, detects patterns
- Analyst Agent: Natural language queries, visualizations
"""

from cbi.agents.analyst import (
    ALLOWED_COLUMNS,
    ALLOWED_TABLES,
    analyst_node,
    execute_query,
    format_results,
    generate_sql,
    get_disease_summary,
    get_geographic_hotspots,
    parse_query_intent,
    process_query,
    validate_sql_query,
)
from cbi.agents.graph import (
    create_cbi_graph,
    get_graph,
    process_conversation_turn,
    reset_graph,
    route_after_reporter,
    route_after_surveillance,
    send_notification_node,
    send_response_node,
)
from cbi.agents.surveillance import (
    THRESHOLDS,
    calculate_urgency,
    check_thresholds,
    surveillance_node,
)
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
from cbi.agents.reporter import (
    detect_language,
    process_message,
    reporter_node,
)
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
    # State helper functions
    "create_initial_state",
    "get_missing_mvs_fields",
    "calculate_data_completeness",
    "add_message_to_state",
    "update_extracted_data",
    "transition_mode",
    "set_handoff",
    "set_error",
    # System prompts
    "REPORTER_SYSTEM_PROMPT",
    "SURVEILLANCE_SYSTEM_PROMPT",
    "ANALYST_SYSTEM_PROMPT",
    "ARABIC_PHRASES",
    # Prompt formatters
    "format_reporter_prompt",
    "format_surveillance_prompt",
    "format_analyst_prompt",
    # Validators
    "validate_reporter_response",
    "validate_surveillance_response",
    "validate_analyst_query_response",
    "validate_analyst_summary_response",
    # Reporter agent
    "reporter_node",
    "process_message",
    "detect_language",
    # Graph
    "create_cbi_graph",
    "get_graph",
    "reset_graph",
    "process_conversation_turn",
    # Agent nodes
    "surveillance_node",
    "analyst_node",
    # Surveillance utilities
    "THRESHOLDS",
    "check_thresholds",
    "calculate_urgency",
    "send_response_node",
    "send_notification_node",
    # Routing functions
    "route_after_reporter",
    "route_after_surveillance",
    # Analyst agent
    "process_query",
    "parse_query_intent",
    "generate_sql",
    "execute_query",
    "format_results",
    "validate_sql_query",
    "get_disease_summary",
    "get_geographic_hotspots",
    "ALLOWED_TABLES",
    "ALLOWED_COLUMNS",
]
