"""
Reporter Agent for CBI.

Handles incoming conversations from community members, detects health signals,
and collects MVS (Minimum Viable Signal) data through natural conversation.

Uses Claude Haiku for fast, cost-effective responses with excellent Arabic support.
"""

import json
import re
import unicodedata
from typing import Any

import anthropic

from cbi.agents.prompts import (
    format_reporter_prompt,
    validate_reporter_response,
)
from cbi.agents.state import (
    ConversationMode,
    ConversationState,
    HandoffTarget,
    Language,
    MessageRole,
    add_message_to_state,
    get_missing_mvs_fields,
    set_error,
    set_handoff,
    transition_mode,
    update_extracted_data,
)
from cbi.config import get_logger, get_settings
from cbi.config.llm_config import get_llm_config

logger = get_logger(__name__)

# Error messages for graceful degradation
ERROR_MESSAGES = {
    "en": "I'm sorry, I'm having trouble processing your message. Please try again in a moment.",
    "ar": "عذراً، أواجه مشكلة في معالجة رسالتك. يرجى المحاولة مرة أخرى بعد قليل.",
}

# Minimum Arabic character ratio to consider text as Arabic
ARABIC_CHAR_THRESHOLD = 0.3


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    """
    Create and return an async Anthropic client.

    Returns:
        Configured AsyncAnthropic client
    """
    settings = get_settings()
    return anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
    )


def detect_language(text: str) -> str:
    """
    Detect whether text is primarily Arabic or English.

    Uses Unicode character analysis to determine language.
    Arabic Unicode ranges: \\u0600-\\u06FF, \\u0750-\\u077F, \\u08A0-\\u08FF

    Args:
        text: Input text to analyze

    Returns:
        Language code: 'ar' for Arabic, 'en' for English
    """
    if not text or not text.strip():
        return Language.unknown.value

    # Count Arabic characters
    arabic_count = 0
    total_letters = 0

    for char in text:
        if unicodedata.category(char).startswith("L"):  # Letter characters
            total_letters += 1
            # Check if character is in Arabic Unicode blocks
            if (
                "\u0600" <= char <= "\u06ff"
                or "\u0750" <= char <= "\u077f"
                or "\u08a0" <= char <= "\u08ff"
            ):
                arabic_count += 1

    if total_letters == 0:
        return Language.unknown.value

    arabic_ratio = arabic_count / total_letters

    if arabic_ratio >= ARABIC_CHAR_THRESHOLD:
        return Language.ar.value
    return Language.en.value


def build_message_history(state: ConversationState) -> list[dict[str, str]]:
    """
    Build conversation history in Claude's expected format.

    Args:
        state: Current conversation state

    Returns:
        List of message dicts with 'role' and 'content' keys
    """
    messages = []
    for msg in state.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Map our roles to Claude's expected roles
        if role == MessageRole.system.value:
            # System messages are passed separately to Claude
            continue
        elif role == MessageRole.assistant.value:
            messages.append({"role": "assistant", "content": content})
        else:
            messages.append({"role": "user", "content": content})

    return messages


def parse_json_response(response_text: str) -> dict[str, Any] | None:
    """
    Parse JSON from Claude's response, handling markdown code blocks.

    Args:
        response_text: Raw response text from Claude

    Returns:
        Parsed JSON dict or None if parsing fails
    """
    # Try to extract JSON from markdown code block
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to parse the entire response as JSON
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # Try to find any JSON object in the response
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def extract_data_from_response(
    parsed: dict[str, Any],
    current_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Extract and merge new data from parsed response.

    Args:
        parsed: Parsed JSON response from Claude
        current_data: Current extracted_data dict

    Returns:
        Updated extracted_data dict with new values merged in
    """
    extracted = parsed.get("extracted_data", {})
    if not extracted:
        return current_data

    # Valid disease types from the DiseaseType enum
    valid_diseases = {"cholera", "dengue", "malaria", "measles", "meningitis", "unknown"}

    # Only update fields that have non-null, non-empty values
    updates = {}
    for key, value in extracted.items():
        if value is not None:
            # Validate suspected_disease against enum values
            if key == "suspected_disease":
                if isinstance(value, str) and value.lower() in valid_diseases:
                    updates[key] = value.lower()
                else:
                    # Invalid disease type - default to "unknown"
                    updates[key] = "unknown"
            elif isinstance(value, list) and len(value) > 0:
                # Merge lists (e.g., symptoms)
                existing = current_data.get(key, [])
                if isinstance(existing, list):
                    # Combine and deduplicate
                    combined = list(dict.fromkeys(existing + value))
                    updates[key] = combined
                else:
                    updates[key] = value
            elif (
                isinstance(value, str)
                and value.strip()
                or isinstance(value, (int, float))
            ):
                updates[key] = value

    return {**current_data, **updates}


def get_user_response_from_parsed(parsed: dict[str, Any], language: str) -> str:
    """
    Get the user-facing response from parsed JSON.

    Args:
        parsed: Parsed JSON response
        language: Current language ('ar' or 'en')

    Returns:
        Response text to send to user
    """
    response = parsed.get("response", "")
    if response:
        return response

    # Fallback if no response field
    return ERROR_MESSAGES.get(language, ERROR_MESSAGES["en"])


async def reporter_node(state: ConversationState) -> ConversationState:
    """
    LangGraph node for the Reporter Agent.

    Processes user messages, detects health signals, and collects MVS data.
    This is the main entry point for conversation processing.

    Args:
        state: Current conversation state

    Returns:
        Updated conversation state with:
        - New assistant message appended
        - Updated mode if transition detected
        - Merged extracted data
        - pending_response set
        - Handoff set if complete
    """
    conversation_id = state.get("conversation_id", "unknown")
    current_mode = state.get("current_mode", ConversationMode.listening.value)
    turn_count = state.get("turn_count", 0)

    logger.info(
        "Reporter agent processing message",
        conversation_id=conversation_id,
        mode=current_mode,
        turn_count=turn_count,
    )

    try:
        # Get the latest user message
        messages = state.get("messages", [])
        if not messages:
            logger.warning(
                "No messages in state",
                conversation_id=conversation_id,
            )
            return set_error(state, "No messages to process")

        latest_message = messages[-1]
        user_text = latest_message.get("content", "")

        # Detect language if unknown
        current_language = state.get("language", Language.unknown.value)
        if current_language == Language.unknown.value:
            detected = detect_language(user_text)
            # Update state with detected language
            new_state = dict(state)
            new_state["language"] = detected
            state = ConversationState(**new_state)
            current_language = detected
            logger.debug(
                "Detected language",
                conversation_id=conversation_id,
                language=detected,
            )

        # Get current extracted data and missing fields
        extracted_data = state.get("extracted_data", {})
        missing_fields = get_missing_mvs_fields(extracted_data)

        # Build message history for Claude
        message_history = build_message_history(state)

        # Format system prompt with current state
        system_prompt = format_reporter_prompt(
            mode=current_mode,
            language=current_language,
            extracted_data=extracted_data,
            missing_fields=missing_fields,
        )

        # Get LLM config and client
        config = get_llm_config("reporter")
        client = get_anthropic_client()

        logger.debug(
            "Calling Claude API",
            conversation_id=conversation_id,
            model=config.model,
            message_count=len(message_history),
        )

        # Call Claude
        response = await client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            system=system_prompt,
            messages=message_history,
        )

        # Extract response text
        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

        logger.debug(
            "Received Claude response",
            conversation_id=conversation_id,
            response_length=len(response_text),
            stop_reason=response.stop_reason,
        )

        # Parse the JSON response
        parsed = parse_json_response(response_text)

        if parsed is None:
            # Couldn't parse JSON - use response as plain text
            logger.warning(
                "Failed to parse JSON response, using raw text",
                conversation_id=conversation_id,
                response_preview=response_text[:200],
            )
            user_response = response_text
            new_mode = current_mode
            new_extracted = extracted_data
        else:
            # Validate the response structure
            is_valid, errors = validate_reporter_response(parsed)
            if not is_valid:
                logger.warning(
                    "Response validation failed",
                    conversation_id=conversation_id,
                    errors=errors,
                )

            # Extract user response
            user_response = get_user_response_from_parsed(parsed, current_language)

            # Update language if detected
            if parsed.get("detected_language") in ["ar", "en"]:
                new_state = dict(state)
                new_state["language"] = parsed["detected_language"]
                state = ConversationState(**new_state)

            # Determine mode transition
            transition_to = parsed.get("transition_to")
            if transition_to and transition_to != current_mode:
                new_mode = transition_to
                logger.info(
                    "Mode transition",
                    conversation_id=conversation_id,
                    from_mode=current_mode,
                    to_mode=new_mode,
                    reasoning=parsed.get("reasoning", ""),
                )
            else:
                new_mode = current_mode

            # Extract new data
            new_extracted = extract_data_from_response(parsed, extracted_data)

        # Update state with assistant response
        state = add_message_to_state(
            state,
            MessageRole.assistant,
            user_response,
        )

        # Update mode if changed
        if new_mode != current_mode:
            state = transition_mode(state, new_mode)

        # Update extracted data if changed
        if new_extracted != extracted_data:
            state = update_extracted_data(state, **new_extracted)

        # Set pending response for the messaging gateway
        new_state = dict(state)
        new_state["pending_response"] = user_response
        state = ConversationState(**new_state)

        # Check if conversation is complete and ready for handoff
        if new_mode == ConversationMode.complete.value:
            state = set_handoff(state, HandoffTarget.surveillance)
            logger.info(
                "Conversation complete, handing off to surveillance",
                conversation_id=conversation_id,
                turn_count=state.get("turn_count", 0),
            )

        logger.info(
            "Reporter agent completed processing",
            conversation_id=conversation_id,
            new_mode=state.get("current_mode"),
            data_completeness=state.get("classification", {}).get(
                "data_completeness", 0
            ),
        )

        return state

    except anthropic.APIConnectionError as e:
        logger.error(
            "API connection error",
            conversation_id=conversation_id,
            error=str(e),
        )
        return _handle_error(state, "connection_error")

    except anthropic.RateLimitError as e:
        logger.error(
            "Rate limit exceeded",
            conversation_id=conversation_id,
            error=str(e),
        )
        return _handle_error(state, "rate_limit")

    except anthropic.APIStatusError as e:
        logger.error(
            "API status error",
            conversation_id=conversation_id,
            status_code=e.status_code,
            error=str(e),
        )
        return _handle_error(state, "api_error")

    except Exception as e:
        logger.exception(
            "Unexpected error in reporter agent",
            conversation_id=conversation_id,
            error=str(e),
        )
        return _handle_error(state, "unexpected_error")


def _handle_error(state: ConversationState, error_type: str) -> ConversationState:
    """
    Handle errors gracefully by setting error state and generating apologetic response.

    Args:
        state: Current conversation state
        error_type: Type of error that occurred

    Returns:
        Updated state with error set and apologetic response
    """
    language = state.get("language", "en")
    error_message = ERROR_MESSAGES.get(language, ERROR_MESSAGES["en"])

    # Set the error and pending response
    state = set_error(state, f"Reporter agent error: {error_type}")

    new_state = dict(state)
    new_state["pending_response"] = error_message
    return ConversationState(**new_state)


async def process_message(
    phone: str,
    platform: str,
    message_text: str,
    state_service: Any,
) -> tuple[str, ConversationState]:
    """
    High-level function to process an incoming message.

    This is a convenience function that combines state management
    with the reporter node for simpler integration.

    Args:
        phone: Reporter's phone number
        platform: Messaging platform (telegram/whatsapp)
        message_text: The incoming message text
        state_service: StateService instance for state persistence

    Returns:
        Tuple of (response_text, updated_state)
    """
    # Get or create conversation state
    state, is_new = await state_service.get_or_create_conversation(platform, phone)

    if is_new:
        logger.info(
            "New conversation started",
            conversation_id=state["conversation_id"],
            platform=platform,
        )

    # Add the user message to state
    state = add_message_to_state(state, MessageRole.user, message_text)

    # Process through reporter node
    state = await reporter_node(state)

    # Save updated state
    await state_service.save_state(state)

    # Return the pending response
    response = state.get("pending_response", "")

    return response, state
