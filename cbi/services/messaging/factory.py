"""
Factory for creating and caching messaging gateway instances.

Provides a singleton pattern per platform to ensure efficient resource usage.
"""

from typing import Any

from cbi.config import get_logger, get_settings

from .base import MessagingGateway
from .exceptions import GatewayNotFoundError
from .telegram import TelegramGateway
from .whatsapp import WhatsAppGateway

logger = get_logger(__name__)

# Cache for gateway instances (singleton per platform)
_gateway_cache: dict[str, MessagingGateway] = {}

# Supported platforms
SUPPORTED_PLATFORMS = frozenset({"telegram", "whatsapp"})


def get_gateway(platform: str) -> MessagingGateway:
    """
    Get or create a messaging gateway for the specified platform.

    Uses singleton pattern to cache gateway instances per platform,
    ensuring efficient resource usage (shared HTTP clients, etc.).

    Args:
        platform: Platform identifier ('telegram' or 'whatsapp')

    Returns:
        MessagingGateway instance for the platform

    Raises:
        GatewayNotFoundError: If platform is not supported
        ValueError: If required configuration is missing

    Example:
        >>> gateway = get_gateway("telegram")
        >>> message_id = await gateway.send_message(outgoing_msg)
    """
    platform = platform.lower()

    if platform not in SUPPORTED_PLATFORMS:
        raise GatewayNotFoundError(platform)

    # Return cached instance if available
    if platform in _gateway_cache:
        return _gateway_cache[platform]

    # Create new gateway instance
    gateway = _create_gateway(platform)
    _gateway_cache[platform] = gateway

    logger.info("Created messaging gateway", platform=platform)

    return gateway


def _create_gateway(platform: str) -> MessagingGateway:
    """
    Create a new gateway instance for the specified platform.

    Args:
        platform: Platform identifier

    Returns:
        New MessagingGateway instance

    Raises:
        ValueError: If required configuration is missing
    """
    settings = get_settings()

    if platform == "telegram":
        bot_token = settings.telegram_bot_token.get_secret_value()
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required for Telegram gateway")
        return TelegramGateway(bot_token=bot_token)

    if platform == "whatsapp":
        phone_number_id = getattr(settings, "whatsapp_phone_number_id", None)
        access_token = getattr(settings, "whatsapp_access_token", None)

        if not phone_number_id:
            raise ValueError(
                "WHATSAPP_PHONE_NUMBER_ID is required for WhatsApp gateway"
            )
        if not access_token:
            raise ValueError("WHATSAPP_ACCESS_TOKEN is required for WhatsApp gateway")

        # Handle SecretStr if present
        if hasattr(access_token, "get_secret_value"):
            access_token = access_token.get_secret_value()

        return WhatsAppGateway(
            phone_number_id=phone_number_id,
            access_token=access_token,
        )

    # This should never happen due to the check in get_gateway
    raise GatewayNotFoundError(platform)


def get_gateway_for_message(
    data: dict[str, Any],
) -> tuple[MessagingGateway, str] | None:
    """
    Determine the appropriate gateway based on webhook data.

    Inspects the webhook payload to identify the platform
    and returns the corresponding gateway.

    Args:
        data: Raw webhook payload

    Returns:
        Tuple of (gateway, platform_name) or None if platform unknown

    Example:
        >>> result = get_gateway_for_message(webhook_data)
        >>> if result:
        ...     gateway, platform = result
        ...     messages = gateway.parse_webhook(webhook_data)
    """
    # Detect Telegram webhook
    if "update_id" in data or "message" in data or "edited_message" in data:
        return get_gateway("telegram"), "telegram"

    # Detect WhatsApp webhook
    if data.get("object") == "whatsapp_business_account":
        return get_gateway("whatsapp"), "whatsapp"

    logger.warning(
        "Unknown webhook format",
        keys=list(data.keys())[:10],  # Log first 10 keys for debugging
    )
    return None


async def close_all_gateways() -> None:
    """
    Close all cached gateway instances.

    Should be called during application shutdown to clean up resources.
    """
    for platform, gateway in _gateway_cache.items():
        try:
            await gateway.close()
            logger.info("Closed messaging gateway", platform=platform)
        except Exception as e:
            logger.error(
                "Error closing gateway",
                platform=platform,
                error=str(e),
            )

    _gateway_cache.clear()


def clear_gateway_cache() -> None:
    """
    Clear the gateway cache without closing connections.

    Primarily used for testing purposes.
    """
    _gateway_cache.clear()
