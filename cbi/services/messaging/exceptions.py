"""
Custom exceptions for the messaging gateway layer.

These exceptions provide clear error handling for messaging operations
without exposing platform-specific details to consumers.
"""

from typing import Any


class MessagingError(Exception):
    """Base exception for all messaging-related errors."""

    def __init__(
        self,
        message: str,
        platform: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.platform = platform
        self.details = details or {}
        super().__init__(message)


class MessagingSendError(MessagingError):
    """
    Raised when a message fails to send.

    Attributes:
        chat_id: The target chat where send failed
        status_code: HTTP status code from the platform API, if available
    """

    def __init__(
        self,
        message: str,
        platform: str | None = None,
        chat_id: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, platform, details)
        self.chat_id = chat_id
        self.status_code = status_code


class MessagingRateLimitError(MessagingError):
    """
    Raised when rate limited by the messaging platform.

    Attributes:
        retry_after: Seconds to wait before retrying, if provided
    """

    def __init__(
        self,
        message: str,
        platform: str | None = None,
        retry_after: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, platform, details)
        self.retry_after = retry_after


class MessagingTemplateError(MessagingError):
    """
    Raised when a template operation fails.

    Attributes:
        template_name: Name of the template that failed
    """

    def __init__(
        self,
        message: str,
        platform: str | None = None,
        template_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, platform, details)
        self.template_name = template_name


class MessagingParseError(MessagingError):
    """
    Raised when webhook data cannot be parsed.

    Attributes:
        raw_data: The raw data that failed to parse (truncated for safety)
    """

    def __init__(
        self,
        message: str,
        platform: str | None = None,
        raw_data: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, platform, details)
        # Store truncated representation to avoid logging sensitive data
        self.raw_data = self._truncate_data(raw_data) if raw_data else None

    @staticmethod
    def _truncate_data(data: dict[str, Any], max_len: int = 500) -> str:
        """Truncate data representation to prevent logging sensitive info."""
        str_repr = str(data)
        if len(str_repr) > max_len:
            return str_repr[:max_len] + "..."
        return str_repr


class MessagingAuthenticationError(MessagingError):
    """Raised when API authentication fails."""

    pass


class MessagingPlatformError(MessagingError):
    """Raised for platform-specific errors that don't fit other categories."""

    pass


class GatewayNotFoundError(MessagingError):
    """Raised when requesting a gateway for an unsupported platform."""

    def __init__(self, platform: str) -> None:
        super().__init__(
            f"No messaging gateway available for platform: {platform}",
            platform=platform,
        )
