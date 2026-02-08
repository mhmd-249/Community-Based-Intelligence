"""
LangGraph workflow for CBI conversation processing.

Defines the conversation flow through Reporter, Surveillance, and Analyst agents
with conditional routing based on health signal detection and urgency levels.
"""

from datetime import datetime
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from cbi.agents.analyst import analyst_node
from cbi.agents.reporter import reporter_node
from cbi.agents.state import (
    ConversationMode,
    ConversationState,
    HandoffTarget,
)
from cbi.agents.surveillance import surveillance_node
from cbi.config import get_logger
from cbi.services.messaging.base import OutgoingMessage
from cbi.services.messaging.factory import get_gateway

logger = get_logger(__name__)


# =============================================================================
# Response and Notification Nodes
# =============================================================================


async def send_response_node(state: ConversationState) -> ConversationState:
    """
    Send the pending response to the user via the appropriate messaging gateway.

    Args:
        state: Current conversation state with pending_response set

    Returns:
        Updated state with pending_response cleared
    """
    conversation_id = state.get("conversation_id", "unknown")
    platform = state.get("platform", "telegram")
    pending_response = state.get("pending_response")
    chat_id = state.get("reporter_phone", "")

    if not pending_response:
        logger.warning(
            "No pending response to send",
            conversation_id=conversation_id,
        )
        return state

    if not chat_id:
        logger.error(
            "No chat_id available for response",
            conversation_id=conversation_id,
        )
        return state

    try:
        gateway = get_gateway(platform)
        message = OutgoingMessage(
            chat_id=chat_id,
            text=pending_response,
        )
        message_id = await gateway.send_message(message)

        logger.info(
            "Sent response to user",
            conversation_id=conversation_id,
            platform=platform,
            message_id=message_id,
            response_length=len(pending_response),
        )

    except Exception as e:
        logger.error(
            "Failed to send response",
            conversation_id=conversation_id,
            platform=platform,
            error=str(e),
        )
        # Don't fail the workflow - just log the error
        # The response can be retried later if needed

    # Clear pending response
    new_state = dict(state)
    new_state["pending_response"] = None
    new_state["updated_at"] = datetime.utcnow().isoformat()

    return ConversationState(**new_state)


async def send_notification_node(state: ConversationState) -> ConversationState:
    """
    Create a notification for health officers about this report.

    Args:
        state: Current conversation state with classification

    Returns:
        Updated state (notification created in database)
    """
    conversation_id = state.get("conversation_id", "unknown")
    classification = state.get("classification", {})
    extracted_data = state.get("extracted_data", {})

    urgency = classification.get("urgency", "medium")
    alert_type = classification.get("alert_type", "single_case")
    suspected_disease = classification.get("suspected_disease", "unknown")

    logger.info(
        "Creating notification for health officers",
        conversation_id=conversation_id,
        urgency=urgency,
        alert_type=alert_type,
        suspected_disease=suspected_disease,
    )

    symptoms = extracted_data.get("symptoms", [])
    location = extracted_data.get("location_text", "Unknown location")
    cases = extracted_data.get("cases_count", 1)
    deaths = extracted_data.get("deaths_count", 0)

    notification_title = f"[{urgency.upper()}] {suspected_disease.title()} Report"
    notification_body = (
        f"Location: {location}\n"
        f"Symptoms: {', '.join(symptoms) if symptoms else 'Not specified'}\n"
        f"Cases: {cases}\n"
        f"Deaths: {deaths or 0}"
    )

    try:
        from cbi.db.models import UrgencyLevel
        from cbi.db.queries import create_notifications_for_all_officers
        from cbi.db.session import get_session

        try:
            urgency_enum = UrgencyLevel(urgency)
        except ValueError:
            urgency_enum = UrgencyLevel.medium

        async with get_session() as session:
            notification_ids = await create_notifications_for_all_officers(
                session,
                urgency=urgency_enum,
                title=notification_title,
                body=notification_body,
                metadata={
                    "conversation_id": conversation_id,
                    "alert_type": alert_type,
                    "suspected_disease": suspected_disease,
                },
            )

        logger.info(
            "Notifications created in database",
            conversation_id=conversation_id,
            title=notification_title,
            notification_count=len(notification_ids),
        )

    except Exception as e:
        logger.error(
            "Failed to create notifications in database",
            conversation_id=conversation_id,
            error=str(e),
        )

    new_state = dict(state)
    new_state["updated_at"] = datetime.utcnow().isoformat()

    return ConversationState(**new_state)


# =============================================================================
# Routing Functions
# =============================================================================


def route_after_reporter(
    state: ConversationState,
) -> Literal["send_response", "__end__"]:
    """
    Determine the next node after the reporter agent.

    Routing logic:
    - If error occurred -> END
    - If there's a pending response -> send_response (always send response first)
    - Otherwise -> END

    After send_response, route_after_send_response handles handoff to surveillance.

    Args:
        state: Current conversation state

    Returns:
        Name of the next node or END
    """
    current_mode = state.get("current_mode")
    error = state.get("error")
    pending_response = state.get("pending_response")

    # Error state - end the workflow
    if error or current_mode == ConversationMode.error.value:
        logger.debug(
            "Routing to END due to error",
            conversation_id=state.get("conversation_id"),
            error=error,
        )
        return "__end__"

    # Always send response to user first (then route to surveillance if needed)
    if pending_response:
        logger.debug(
            "Routing to send_response",
            conversation_id=state.get("conversation_id"),
        )
        return "send_response"

    # Default - end
    logger.debug(
        "Routing to END (default)",
        conversation_id=state.get("conversation_id"),
    )
    return "__end__"


def route_after_send_response(
    state: ConversationState,
) -> Literal["surveillance", "__end__"]:
    """
    Determine the next node after sending a response to the user.

    If the conversation is complete and needs surveillance handoff,
    route to surveillance. Otherwise, end.

    Args:
        state: Current conversation state

    Returns:
        Name of the next node or END
    """
    current_mode = state.get("current_mode")
    handoff_to = state.get("handoff_to")

    if (
        current_mode == ConversationMode.complete.value
        and handoff_to == HandoffTarget.surveillance.value
    ):
        logger.debug(
            "Routing to surveillance after sending response",
            conversation_id=state.get("conversation_id"),
        )
        return "surveillance"

    return "__end__"


def route_after_surveillance(
    state: ConversationState,
) -> Literal["analyst", "send_notification", "__end__"]:
    """
    Determine the next node after the surveillance agent.

    Routing logic:
    - If urgency is critical or high -> analyst (for deeper analysis)
    - If urgency is medium -> send_notification
    - Otherwise (low) -> END

    Args:
        state: Current conversation state

    Returns:
        Name of the next node or END
    """
    classification = state.get("classification", {})
    urgency = classification.get("urgency", "low")

    conversation_id = state.get("conversation_id")

    if urgency in ("critical", "high"):
        logger.debug(
            "Routing to analyst for critical/high urgency",
            conversation_id=conversation_id,
            urgency=urgency,
        )
        return "analyst"

    if urgency == "medium":
        logger.debug(
            "Routing to send_notification for medium urgency",
            conversation_id=conversation_id,
            urgency=urgency,
        )
        return "send_notification"

    # Low urgency - end without notification
    logger.debug(
        "Routing to END for low urgency",
        conversation_id=conversation_id,
        urgency=urgency,
    )
    return "__end__"


# =============================================================================
# Graph Creation
# =============================================================================


def create_cbi_graph(checkpointer: MemorySaver | None = None) -> StateGraph:
    """
    Create the CBI conversation processing graph.

    The graph flows as follows:
    1. reporter: Process user message, detect health signals, collect MVS
    2. If complete -> surveillance: Classify report
    3. If critical/high -> analyst: Deep analysis
    4. send_notification: Alert health officers
    5. send_response: Reply to user

    Args:
        checkpointer: Optional checkpointer for state persistence.
                     Defaults to MemorySaver for development.

    Returns:
        Compiled StateGraph ready for execution
    """
    # Create the graph with ConversationState
    workflow = StateGraph(ConversationState)

    # Add nodes
    workflow.add_node("reporter", reporter_node)
    workflow.add_node("surveillance", surveillance_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("send_response", send_response_node)
    workflow.add_node("send_notification", send_notification_node)

    # Set entry point
    workflow.set_entry_point("reporter")

    # Add conditional edges from reporter
    workflow.add_conditional_edges(
        "reporter",
        route_after_reporter,
        {
            "send_response": "send_response",
            "__end__": END,
        },
    )

    # Add conditional edges from send_response
    # Routes to surveillance if conversation is complete, otherwise END
    workflow.add_conditional_edges(
        "send_response",
        route_after_send_response,
        {
            "surveillance": "surveillance",
            "__end__": END,
        },
    )

    # Add conditional edges from surveillance
    workflow.add_conditional_edges(
        "surveillance",
        route_after_surveillance,
        {
            "analyst": "analyst",
            "send_notification": "send_notification",
            "__end__": END,
        },
    )

    # Add edges from analyst and notification
    workflow.add_edge("analyst", "send_notification")
    workflow.add_edge("send_notification", END)

    # Use provided checkpointer or create default
    if checkpointer is None:
        checkpointer = MemorySaver()

    # Compile the graph
    compiled = workflow.compile(checkpointer=checkpointer)

    logger.info("CBI conversation graph compiled successfully")

    return compiled


# =============================================================================
# Convenience Functions
# =============================================================================


async def process_conversation_turn(
    state: ConversationState,
    graph: StateGraph | None = None,
    thread_id: str | None = None,
) -> ConversationState:
    """
    Process a single conversation turn through the graph.

    This is a convenience function for running the graph with a given state.

    Args:
        state: Current conversation state with user message added
        graph: Optional pre-compiled graph (creates new if not provided)
        thread_id: Optional thread ID for checkpointing

    Returns:
        Updated conversation state after processing
    """
    if graph is None:
        graph = create_cbi_graph()

    config = {}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    # Run the graph
    result = await graph.ainvoke(state, config)

    return result


# Singleton graph instance for reuse
_graph_instance: StateGraph | None = None


def get_graph() -> StateGraph:
    """
    Get or create the singleton graph instance.

    Returns:
        Compiled StateGraph instance
    """
    global _graph_instance

    if _graph_instance is None:
        _graph_instance = create_cbi_graph()

    return _graph_instance


def reset_graph() -> None:
    """Reset the singleton graph instance (mainly for testing)."""
    global _graph_instance
    _graph_instance = None
