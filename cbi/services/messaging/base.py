"""
Base classes and dataclasses for the messaging gateway abstraction layer.

Provides platform-agnostic interfaces for Telegram, WhatsApp, and future platforms.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class IncomingMessage:
    """
    Platform-agnostic representation of an incoming message.

    Attributes:
        platform: Source platform (e.g., 'telegram', 'whatsapp')
        message_id: Platform-specific message identifier
        chat_id: Conversation/chat identifier
        from_id: Sender identifier
        text: Message text content (may be None for media-only messages)
        timestamp: When the message was sent
        reply_to_id: ID of message being replied to, if any
    """

    platform: str
    message_id: str
    chat_id: str
    from_id: str
    text: str | None
    timestamp: datetime
    reply_to_id: str | None = None


@dataclass
class OutgoingMessage:
    """
    Platform-agnostic representation of an outgoing message.

    Attributes:
        chat_id: Target conversation/chat identifier
        text: Message text content
        reply_to_id: ID of message to reply to, if any
    """

    chat_id: str
    text: str
    reply_to_id: str | None = None


@dataclass
class TemplateParameter:
    """
    A parameter for a message template.

    Attributes:
        type: Parameter type ('text', 'currency', 'date_time', etc.)
        value: The parameter value
    """

    type: str = "text"
    value: str = ""


class MessagingGateway(ABC):
    """
    Abstract base class for messaging platform gateways.

    Implementations must handle platform-specific API calls and
    data format conversions while exposing a common interface.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (e.g., 'telegram', 'whatsapp')."""
        ...

    @abstractmethod
    async def send_message(self, message: OutgoingMessage) -> str:
        """
        Send a text message to a chat.

        Args:
            message: The outgoing message to send

        Returns:
            Platform-specific message ID of the sent message

        Raises:
            MessagingSendError: If the message could not be sent
            MessagingRateLimitError: If rate limited by the platform
        """
        ...

    @abstractmethod
    async def send_template(
        self,
        chat_id: str,
        template_name: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Send a template message to a chat.

        For platforms without native templates (e.g., Telegram),
        implementations should format the template string locally.

        Args:
            chat_id: Target conversation identifier
            template_name: Name of the template to use
            params: Parameters to substitute into the template

        Returns:
            Platform-specific message ID of the sent message

        Raises:
            MessagingTemplateError: If the template is not found or invalid
            MessagingSendError: If the message could not be sent
        """
        ...

    @abstractmethod
    def parse_webhook(self, data: dict[str, Any]) -> list[IncomingMessage]:
        """
        Parse a webhook payload into incoming messages.

        This method is synchronous since webhook parsing doesn't require I/O.

        Args:
            data: Raw webhook payload from the platform

        Returns:
            List of parsed incoming messages (may be empty if no text messages)

        Raises:
            MessagingParseError: If the webhook data is malformed
        """
        ...

    async def close(self) -> None:  # noqa: B027
        """
        Clean up any resources (e.g., HTTP clients).

        Subclasses should override if they need cleanup.
        This is intentionally not abstract - default is no cleanup needed.
        """
        pass
