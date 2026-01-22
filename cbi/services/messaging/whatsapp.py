"""
WhatsApp Cloud API implementation of the MessagingGateway.

Uses httpx for async HTTP requests to the Meta Graph API.
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

# WhatsApp Cloud API base URL
WHATSAPP_API_BASE = "https://graph.facebook.com/v18.0"


class WhatsAppGateway(MessagingGateway):
    """
    WhatsApp Cloud API gateway implementation.

    Handles sending and receiving messages via Meta's WhatsApp Business API.
    Supports both text messages and template messages.
    """

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Initialize the WhatsApp gateway.

        Args:
            phone_number_id: WhatsApp Business phone number ID
            access_token: Meta Graph API access token
            http_client: Optional pre-configured httpx client
        """
        self._phone_number_id = phone_number_id
        self._access_token = access_token
        self._base_url = f"{WHATSAPP_API_BASE}/{phone_number_id}/messages"
        self._client = http_client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = http_client is None

    @property
    def platform_name(self) -> str:
        """Return the platform identifier."""
        return "whatsapp"

    def _get_headers(self) -> dict[str, str]:
        """Get authorization headers for API requests."""
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def send_message(self, message: OutgoingMessage) -> str:
        """
        Send a text message via WhatsApp.

        Args:
            message: The outgoing message to send

        Returns:
            WhatsApp message ID

        Raises:
            MessagingSendError: If the message fails to send
            MessagingRateLimitError: If rate limited by Meta
            MessagingAuthenticationError: If the access token is invalid
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": message.chat_id,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message.text,
            },
        }

        if message.reply_to_id:
            payload["context"] = {"message_id": message.reply_to_id}

        try:
            response = await self._client.post(
                self._base_url,
                json=payload,
                headers=self._get_headers(),
            )

            return self._handle_response(response, message.chat_id)

        except httpx.TimeoutException as e:
            logger.error(
                "WhatsApp API timeout",
                chat_id=message.chat_id,
                error=str(e),
            )
            raise MessagingSendError(
                "Request to WhatsApp API timed out",
                platform=self.platform_name,
                chat_id=message.chat_id,
            ) from e
        except httpx.RequestError as e:
            logger.error(
                "WhatsApp API request error",
                chat_id=message.chat_id,
                error=str(e),
            )
            raise MessagingSendError(
                f"Failed to connect to WhatsApp API: {e}",
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
        Send a template message via WhatsApp.

        Uses WhatsApp's template message format which requires
        pre-approved templates registered with Meta.

        Args:
            chat_id: Target phone number (recipient)
            template_name: Name of the approved template
            params: Template parameters with structure:
                {
                    "language": "en",  # Template language code
                    "components": [    # Optional template components
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": "value1"},
                                {"type": "text", "text": "value2"},
                            ]
                        }
                    ]
                }

        Returns:
            WhatsApp message ID

        Raises:
            MessagingTemplateError: If template parameters are invalid
            MessagingSendError: If the message fails to send
        """
        params = params or {}
        language_code = params.get("language", "en")
        components = params.get("components", [])

        template_payload: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }

        if components:
            template_payload["components"] = components

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": chat_id,
            "type": "template",
            "template": template_payload,
        }

        try:
            response = await self._client.post(
                self._base_url,
                json=payload,
                headers=self._get_headers(),
            )

            return self._handle_template_response(response, chat_id, template_name)

        except httpx.TimeoutException as e:
            logger.error(
                "WhatsApp API timeout (template)",
                chat_id=chat_id,
                template=template_name,
                error=str(e),
            )
            raise MessagingSendError(
                "Request to WhatsApp API timed out",
                platform=self.platform_name,
                chat_id=chat_id,
            ) from e
        except httpx.RequestError as e:
            logger.error(
                "WhatsApp API request error (template)",
                chat_id=chat_id,
                template=template_name,
                error=str(e),
            )
            raise MessagingSendError(
                f"Failed to connect to WhatsApp API: {e}",
                platform=self.platform_name,
                chat_id=chat_id,
            ) from e

    def parse_webhook(self, data: dict[str, Any]) -> list[IncomingMessage]:
        """
        Parse a WhatsApp webhook payload into incoming messages.

        Handles the nested WhatsApp webhook structure:
        {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{...}],
                        "contacts": [{...}]
                    }
                }]
            }]
        }

        Args:
            data: Raw WhatsApp webhook payload

        Returns:
            List of parsed incoming messages (may be empty)

        Raises:
            MessagingParseError: If the webhook data is malformed
        """
        if not isinstance(data, dict):
            raise MessagingParseError(
                "Invalid webhook payload: expected dict",
                platform=self.platform_name,
                raw_data=data if isinstance(data, dict) else {"type": str(type(data))},
            )

        # Check if this is a WhatsApp webhook
        if data.get("object") != "whatsapp_business_account":
            logger.debug(
                "Non-WhatsApp webhook received",
                object_type=data.get("object"),
            )
            return []

        messages: list[IncomingMessage] = []

        try:
            entries = data.get("entry", [])
            for entry in entries:
                changes = entry.get("changes", [])
                for change in changes:
                    value = change.get("value", {})
                    raw_messages = value.get("messages", [])
                    contacts = {
                        c["wa_id"]: c.get("profile", {}).get("name", "")
                        for c in value.get("contacts", [])
                    }

                    for msg in raw_messages:
                        parsed = self._parse_message(msg, contacts)
                        if parsed:
                            messages.append(parsed)

        except (KeyError, TypeError) as e:
            raise MessagingParseError(
                f"Failed to parse WhatsApp webhook: {e}",
                platform=self.platform_name,
                raw_data=data,
            ) from e

        return messages

    def _parse_message(
        self,
        msg: dict[str, Any],
        contacts: dict[str, str],  # noqa: ARG002 - Reserved for future use
    ) -> IncomingMessage | None:
        """
        Parse a single WhatsApp message.

        Args:
            msg: Raw message data from webhook
            contacts: Map of wa_id to contact names

        Returns:
            IncomingMessage if text message, None for other types
        """
        msg_type = msg.get("type")
        msg_id = msg.get("id", "")
        from_id = msg.get("from", "")
        timestamp_str = msg.get("timestamp", "0")

        # Convert Unix timestamp string to datetime
        try:
            timestamp_unix = int(timestamp_str)
            timestamp = datetime.fromtimestamp(timestamp_unix, tz=UTC)
        except (ValueError, TypeError):
            timestamp = datetime.now(UTC)

        # Handle context (reply-to)
        context = msg.get("context", {})
        reply_to_id = context.get("id") if context else None

        # Extract text based on message type
        if msg_type == "text":
            text = msg.get("text", {}).get("body")
        elif msg_type == "button":
            # Quick reply button response
            text = msg.get("button", {}).get("text")
        elif msg_type == "interactive":
            # Interactive message response (list reply or button reply)
            interactive = msg.get("interactive", {})
            interactive_type = interactive.get("type")
            if interactive_type == "button_reply":
                text = interactive.get("button_reply", {}).get("title")
            elif interactive_type == "list_reply":
                text = interactive.get("list_reply", {}).get("title")
            else:
                text = None
        else:
            # Handle non-text messages (image, document, audio, etc.)
            logger.info(
                "Non-text WhatsApp message received, skipping for MVP",
                message_type=msg_type,
                from_id=from_id,
            )
            return None

        if not text:
            return None

        return IncomingMessage(
            platform=self.platform_name,
            message_id=msg_id,
            chat_id=from_id,  # In WhatsApp, chat_id is the sender's phone number
            from_id=from_id,
            text=text,
            timestamp=timestamp,
            reply_to_id=reply_to_id,
        )

    def _handle_response(self, response: httpx.Response, chat_id: str) -> str:
        """
        Handle WhatsApp API response for text messages.

        Args:
            response: The HTTP response from WhatsApp
            chat_id: The target phone number (for error context)

        Returns:
            Message ID

        Raises:
            MessagingAuthenticationError: For 401 errors
            MessagingRateLimitError: For 429 errors
            MessagingSendError: For other errors
        """
        return self._process_api_response(response, chat_id)

    def _handle_template_response(
        self,
        response: httpx.Response,
        chat_id: str,
        template_name: str,
    ) -> str:
        """
        Handle WhatsApp API response for template messages.

        Args:
            response: The HTTP response from WhatsApp
            chat_id: The target phone number
            template_name: The template name (for error context)

        Returns:
            Message ID

        Raises:
            MessagingTemplateError: For template-specific errors
            MessagingAuthenticationError: For 401 errors
            MessagingRateLimitError: For 429 errors
            MessagingSendError: For other errors
        """
        status_code = response.status_code

        try:
            result = response.json()
        except ValueError as e:
            raise MessagingSendError(
                "Invalid JSON response from WhatsApp",
                platform=self.platform_name,
                chat_id=chat_id,
                status_code=status_code,
            ) from e

        # Check for template-specific errors
        error = result.get("error", {})
        error_code = error.get("code")

        if error_code in (131047, 131026):
            # Template not found or not approved
            raise MessagingTemplateError(
                error.get("message", "Template error"),
                platform=self.platform_name,
                template_name=template_name,
                details={"whatsapp_error": error},
            )

        return self._process_api_response(response, chat_id, result)

    def _process_api_response(
        self,
        response: httpx.Response,
        chat_id: str,
        parsed_result: dict[str, Any] | None = None,
    ) -> str:
        """
        Process WhatsApp API response and extract message ID.

        Args:
            response: The HTTP response
            chat_id: Target chat ID for error context
            parsed_result: Pre-parsed JSON result, if available

        Returns:
            Message ID

        Raises:
            Various MessagingErrors based on error type
        """
        status_code = response.status_code

        if parsed_result is None:
            try:
                parsed_result = response.json()
            except ValueError as e:
                raise MessagingSendError(
                    "Invalid JSON response from WhatsApp",
                    platform=self.platform_name,
                    chat_id=chat_id,
                    status_code=status_code,
                ) from e

        # Successful response
        if status_code == 200:
            messages = parsed_result.get("messages", [])
            if messages:
                return messages[0].get("id", "")
            return ""

        # Error handling
        error = parsed_result.get("error", {})
        error_message = error.get("message", "Unknown error")
        error_code = error.get("code", status_code)

        if status_code == 401 or error_code == 190:
            raise MessagingAuthenticationError(
                "Invalid WhatsApp access token",
                platform=self.platform_name,
            )

        if status_code == 429 or error_code == 130429:
            raise MessagingRateLimitError(
                "WhatsApp rate limit exceeded",
                platform=self.platform_name,
            )

        logger.error(
            "WhatsApp API error",
            status_code=status_code,
            error_code=error_code,
            error_message=error_message,
            chat_id=chat_id,
        )

        raise MessagingSendError(
            f"WhatsApp API error: {error_message}",
            platform=self.platform_name,
            chat_id=chat_id,
            status_code=error_code,
            details={"whatsapp_error": error},
        )

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()
