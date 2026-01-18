"""
Structured JSON logging configuration.

Features:
- JSON format for production (machine-parseable)
- Console format for development (human-readable)
- PII filtering to prevent phone numbers and sensitive data from being logged
- Context binding for conversation_id and agent_name
"""

import logging
import re
import sys
from collections.abc import Mapping
from typing import Any

import structlog
from structlog.types import EventDict, Processor


# Patterns for PII detection
PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Phone numbers (international formats)
    (re.compile(r"\+?[0-9]{10,15}"), "[PHONE_REDACTED]"),
    # Phone with country code
    (re.compile(r"\+\d{1,3}[-.\s]?\d{3,4}[-.\s]?\d{3,4}[-.\s]?\d{3,4}"), "[PHONE_REDACTED]"),
    # Email addresses
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[EMAIL_REDACTED]"),
    # National ID patterns (Sudan format)
    (re.compile(r"\b\d{11}\b"), "[ID_REDACTED]"),
]


def _redact_pii_from_value(value: Any) -> Any:
    """Recursively redact PII from a value."""
    if isinstance(value, str):
        result = value
        for pattern, replacement in PII_PATTERNS:
            result = pattern.sub(replacement, result)
        return result
    elif isinstance(value, dict):
        return {k: _redact_pii_from_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_redact_pii_from_value(item) for item in value]
    return value


def filter_pii(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Structlog processor that redacts PII from log events.

    Scans all string values in the event dictionary and replaces
    phone numbers, emails, and other PII with redacted placeholders.
    """
    return {key: _redact_pii_from_value(value) for key, value in event_dict.items()}


def add_service_context(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add service-level context to all log events."""
    event_dict.setdefault("service", "cbi")
    return event_dict


def configure_logging(
    *,
    json_format: bool = True,
    log_level: str = "INFO",
) -> None:
    """
    Configure structured logging for the application.

    Args:
        json_format: If True, output JSON logs (production).
                    If False, output colored console logs (development).
        log_level: Minimum log level to output.
    """
    # Shared processors for all configurations
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_service_context,
        filter_pii,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_format:
        # Production: JSON format
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Colored console output
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )


def get_logger(
    name: str | None = None,
    *,
    conversation_id: str | None = None,
    agent_name: str | None = None,
) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger with optional context binding.

    Args:
        name: Logger name (typically module name).
        conversation_id: Conversation ID for request tracing.
        agent_name: Name of the agent (reporter, surveillance, analyst).

    Returns:
        Bound logger with context.

    Example:
        logger = get_logger(__name__, conversation_id="abc123", agent_name="reporter")
        logger.info("Processing message", message_type="text")
    """
    logger = structlog.get_logger(name)

    bindings: dict[str, Any] = {}
    if conversation_id:
        bindings["conversation_id"] = conversation_id
    if agent_name:
        bindings["agent_name"] = agent_name

    if bindings:
        logger = logger.bind(**bindings)

    return logger


def bind_context(**kwargs: Any) -> None:
    """
    Bind context variables that will be included in all subsequent logs.

    Useful for adding request-scoped context like conversation_id.

    Args:
        **kwargs: Context variables to bind.

    Example:
        bind_context(conversation_id="abc123", agent_name="reporter")
        logger.info("This log will include conversation_id and agent_name")
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()
