"""
Telegram Bot API implementation of the MessagingGateway.

Uses httpx for async HTTP requests to the Telegram Bot API.
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from cbi.config import get_logger

from .base import IncomingMessage, MessagingGateway, OutgoingMessage
from .exceptions import (
    MessagingAuthenticationError,
    MessagingParseError,
    MessagingRateLimitError,
    MessagingSendError,
    MessagingTemplateError,
)

logger = get_logger(__name__)

# Telegram Bot API base URL
TELEGRAM_API_BASE = "https://api.telegram.org/bot"

# Default templates for common messages
DEFAULT_TEMPLATES: dict[str, str] = {
    "welcome": "Welcome! I'm here to help you report health incidents in your community.",
    "welcome_ar": "مرحبا! أنا هنا لمساعدتك في الإبلاغ عن الحوادث الصحية في مجتمعك.",
    "confirm_received": "Thank you. Your report has been received and will be reviewed by a health officer.",
    "confirm_received_ar": "شكرا لك. تم استلام تقريرك وسيتم مراجعته من قبل مسؤول صحي.",
    "error": "Sorry, something went wrong. Please try again later.",
    "error_ar": "عذرا، حدث خطأ ما. يرجى المحاولة مرة أخرى لاحقا.",
}


class TelegramGateway(MessagingGateway):
    """
    Telegram Bot API gateway implementation.

    Handles sending and receiving messages via the Telegram Bot API.
    Uses HTML parse mode for message formatting.
    """

    def __init__(
        self,
        bot_token: str,
        http_client: httpx.AsyncClient | None = None,
        templates: dict[str, str] | None = None,
    ) -> None:
        """
        Initialize the Telegram gateway.

        Args:
            bot_token: Telegram Bot API token
            http_client: Optional pre-configured httpx client
            templates: Custom templates to override defaults
        """
        self._bot_token = bot_token
        self._base_url = f"{TELEGRAM_API_BASE}{bot_token}"
        self._client = http_client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = http_client is None
        self._templates = {**DEFAULT_TEMPLATES, **(templates or {})}

    @property
    def platform_name(self) -> str:
        """Return the platform identifier."""
        return "telegram"

    async def send_message(self, message: OutgoingMessage) -> str:
        """
        Send a text message via Telegram.

        Uses HTML parse mode for formatting support.

        Args:
            message: The outgoing message to send

        Returns:
            Telegram message ID as string

        Raises:
            MessagingSendError: If the message fails to send
            MessagingRateLimitError: If rate limited by Telegram
            MessagingAuthenticationError: If the bot token is invalid
        """
        payload: dict[str, Any] = {
            "chat_id": message.chat_id,
            "text": message.text,
            "parse_mode": "HTML",
        }

        if message.reply_to_id:
            payload["reply_to_message_id"] = int(message.reply_to_id)

        try:
            response = await self._client.post(
                f"{self._base_url}/sendMessage",
                json=payload,
            )

            return self._handle_response(response, message.chat_id)

        except httpx.TimeoutException as e:
            logger.error(
                "Telegram API timeout",
                chat_id=message.chat_id,
                error=str(e),
            )
            raise MessagingSendError(
                "Request to Telegram API timed out",
                platform=self.platform_name,
                chat_id=message.chat_id,
            ) from e
        except httpx.RequestError as e:
            logger.error(
                "Telegram API request error",
                chat_id=message.chat_id,
                error=str(e),
            )
            raise MessagingSendError(
                f"Failed to connect to Telegram API: {e}",
                platform=self.platform_name,
                chat_id=message.chat_id,
            ) from e

    async def send_template(
        self,
        chat_id: str,
        template_name: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Send a template message via Telegram.

        Since Telegram doesn't have native templates, this formats
        the template string locally and sends it as a regular message.

        Args:
            chat_id: Target chat identifier
            template_name: Name of the template to use
            params: Parameters to substitute into the template

        Returns:
            Telegram message ID as string

        Raises:
            MessagingTemplateError: If template not found
            MessagingSendError: If the message fails to send
        """
        template = self._templates.get(template_name)
        if not template:
            raise MessagingTemplateError(
                f"Template not found: {template_name}",
                platform=self.platform_name,
                template_name=template_name,
            )

        try:
            text = template.format(**(params or {}))
        except KeyError as e:
            raise MessagingTemplateError(
                f"Missing template parameter: {e}",
                platform=self.platform_name,
                template_name=template_name,
                details={"missing_param": str(e)},
            ) from e

        message = OutgoingMessage(chat_id=chat_id, text=text)
        return await self.send_message(message)

    def parse_webhook(self, data: dict[str, Any]) -> list[IncomingMessage]:
        """
        Parse a Telegram webhook update into incoming messages.

        Extracts text messages from Telegram update format.
        Logs and skips non-text messages (photos, documents, etc.) for MVP.

        Args:
            data: Raw Telegram webhook payload

        Returns:
            List containing zero or one IncomingMessage

        Raises:
            MessagingParseError: If the update is malformed
        """
        if not isinstance(data, dict):
            raise MessagingParseError(
                "Invalid webhook payload: expected dict",
                platform=self.platform_name,
                raw_data=data if isinstance(data, dict) else {"type": str(type(data))},
            )

        # Handle different update types
        message_data = data.get("message") or data.get("edited_message")

        if not message_data:
            # Could be callback_query, inline_query, etc.
            logger.debug(
                "Non-message update received",
                update_id=data.get("update_id"),
                keys=list(data.keys()),
            )
            return []

        # Check for text content
        text = message_data.get("text")
        if text is None:
            # Handle non-text messages (photo, document, sticker, etc.)
            content_types = [
                k
                for k in message_data
                if k
                in (
                    "photo",
                    "document",
                    "video",
                    "audio",
                    "voice",
                    "sticker",
                    "location",
                )
            ]
            if content_types:
                logger.info(
                    "Non-text message received, skipping for MVP",
                    content_types=content_types,
                    chat_id=message_data.get("chat", {}).get("id"),
                )
            return []

        try:
            chat = message_data.get("chat", {})
            from_user = message_data.get("from", {})
            reply_to = message_data.get("reply_to_message")

            # Convert Unix timestamp to datetime
            timestamp_unix = message_data.get("date", 0)
            timestamp = datetime.fromtimestamp(timestamp_unix, tz=UTC)

            incoming = IncomingMessage(
                platform=self.platform_name,
                message_id=str(message_data.get("message_id", "")),
                chat_id=str(chat.get("id", "")),
                from_id=str(from_user.get("id", "")),
                text=text,
                timestamp=timestamp,
                reply_to_id=str(reply_to["message_id"]) if reply_to else None,
            )

            return [incoming]

        except (KeyError, TypeError) as e:
            raise MessagingParseError(
                f"Failed to parse Telegram message: {e}",
                platform=self.platform_name,
                raw_data=data,
            ) from e

    def _handle_response(self, response: httpx.Response, chat_id: str) -> str:
        """
        Handle Telegram API response and extract message ID.

        Args:
            response: The HTTP response from Telegram
            chat_id: The target chat ID (for error context)

        Returns:
            Message ID as string

        Raises:
            MessagingAuthenticationError: For 401 errors
            MessagingRateLimitError: For 429 errors
            MessagingSendError: For other errors
        """
        status_code = response.status_code

        try:
            result = response.json()
        except ValueError as e:
            raise MessagingSendError(
                "Invalid JSON response from Telegram",
                platform=self.platform_name,
                chat_id=chat_id,
                status_code=status_code,
            ) from e

        if result.get("ok"):
            return str(result.get("result", {}).get("message_id", ""))

        error_description = result.get("description", "Unknown error")
        error_code = result.get("error_code", status_code)

        if error_code == 401:
            raise MessagingAuthenticationError(
                "Invalid Telegram bot token",
                platform=self.platform_name,
            )

        if error_code == 429:
            retry_after = result.get("parameters", {}).get("retry_after")
            raise MessagingRateLimitError(
                "Telegram rate limit exceeded",
                platform=self.platform_name,
                retry_after=retry_after,
            )

        logger.error(
            "Telegram API error",
            error_code=error_code,
            description=error_description,
            chat_id=chat_id,
        )

        raise MessagingSendError(
            f"Telegram API error: {error_description}",
            platform=self.platform_name,
            chat_id=chat_id,
            status_code=error_code,
            details={"telegram_error": result},
        )

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()
