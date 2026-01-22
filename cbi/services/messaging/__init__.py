"""
Messaging gateway abstraction layer.

Provides a unified interface for sending and receiving messages
across different platforms (Telegram, WhatsApp).

Example usage:
    from cbi.services.messaging import get_gateway, IncomingMessage, OutgoingMessage

    # Get a gateway instance
    gateway = get_gateway("telegram")

    # Send a message
    message = OutgoingMessage(chat_id="123456", text="Hello!")
    message_id = await gateway.send_message(message)

    # Parse incoming webhook
    messages = gateway.parse_webhook(webhook_data)
    for msg in messages:
        print(f"Received: {msg.text}")
"""

from .base import IncomingMessage, MessagingGateway, OutgoingMessage, TemplateParameter
from .exceptions import (
    GatewayNotFoundError,
    MessagingAuthenticationError,
    MessagingError,
    MessagingParseError,
    MessagingPlatformError,
    MessagingRateLimitError,
    MessagingSendError,
    MessagingTemplateError,
)
from .factory import (
    SUPPORTED_PLATFORMS,
    clear_gateway_cache,
    close_all_gateways,
    get_gateway,
    get_gateway_for_message,
)
from .telegram import TelegramGateway
from .whatsapp import WhatsAppGateway

__all__ = [
    # Base classes
    "MessagingGateway",
    "IncomingMessage",
    "OutgoingMessage",
    "TemplateParameter",
    # Gateway implementations
    "TelegramGateway",
    "WhatsAppGateway",
    # Factory functions
    "get_gateway",
    "get_gateway_for_message",
    "close_all_gateways",
    "clear_gateway_cache",
    "SUPPORTED_PLATFORMS",
    # Exceptions
    "MessagingError",
    "MessagingSendError",
    "MessagingRateLimitError",
    "MessagingTemplateError",
    "MessagingParseError",
    "MessagingAuthenticationError",
    "MessagingPlatformError",
    "GatewayNotFoundError",
]
