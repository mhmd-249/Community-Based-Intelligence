"""
Webhook security utilities for signature verification.

Implements signature verification for incoming webhooks from
Telegram and WhatsApp to ensure authenticity.
"""

import hashlib
import hmac

from cbi.config import get_logger, get_settings

logger = get_logger(__name__)


def verify_whatsapp_signature(
    payload: bytes,
    signature_header: str | None,
    app_secret: str | None = None,
) -> bool:
    """
    Verify the X-Hub-Signature-256 header from WhatsApp webhooks.

    WhatsApp/Meta signs webhook payloads using HMAC-SHA256 with the
    app secret as the key. The signature is sent in the header as:
    X-Hub-Signature-256: sha256=<hex_digest>

    Args:
        payload: Raw request body bytes
        signature_header: Value of X-Hub-Signature-256 header
        app_secret: Meta app secret (uses settings if not provided)

    Returns:
        True if signature is valid, False otherwise

    Example:
        >>> body = await request.body()
        >>> sig = request.headers.get("X-Hub-Signature-256")
        >>> if not verify_whatsapp_signature(body, sig):
        ...     raise HTTPException(403, "Invalid signature")
    """
    if not signature_header:
        logger.warning("Missing X-Hub-Signature-256 header")
        return False

    # Get app secret from settings if not provided
    if app_secret is None:
        settings = get_settings()
        if settings.whatsapp_app_secret:
            app_secret = settings.whatsapp_app_secret.get_secret_value()

    if not app_secret:
        logger.error("WhatsApp app secret not configured")
        return False

    # Parse the signature header (format: "sha256=<hex_digest>")
    if not signature_header.startswith("sha256="):
        logger.warning("Invalid signature format", header=signature_header[:20])
        return False

    expected_signature = signature_header[7:]  # Remove "sha256=" prefix

    # Calculate the signature
    computed_signature = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Compare signatures using constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(computed_signature, expected_signature)

    if not is_valid:
        logger.warning("WhatsApp webhook signature verification failed")

    return is_valid


def verify_telegram_secret_token(
    secret_token_header: str | None,
    expected_token: str | None = None,
) -> bool:
    """
    Verify the X-Telegram-Bot-Api-Secret-Token header.

    When setting up a Telegram webhook with a secret_token parameter,
    Telegram includes it in every request for verification.

    Args:
        secret_token_header: Value of X-Telegram-Bot-Api-Secret-Token header
        expected_token: Expected secret token (uses settings if not provided)

    Returns:
        True if token matches or no token is configured, False if mismatch

    Example:
        >>> token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        >>> if not verify_telegram_secret_token(token):
        ...     raise HTTPException(403, "Invalid token")
    """
    # Get expected token from settings if not provided
    if expected_token is None:
        settings = get_settings()
        if settings.telegram_webhook_secret:
            expected_token = settings.telegram_webhook_secret.get_secret_value()

    # If no secret is configured, skip verification
    if not expected_token:
        return True

    # If secret is configured, header must be present and match
    if not secret_token_header:
        logger.warning("Missing X-Telegram-Bot-Api-Secret-Token header")
        return False

    # Compare using constant-time comparison
    is_valid = hmac.compare_digest(secret_token_header, expected_token)

    if not is_valid:
        logger.warning("Telegram webhook secret token verification failed")

    return is_valid


def compute_whatsapp_signature(payload: bytes, app_secret: str) -> str:
    """
    Compute the HMAC-SHA256 signature for a WhatsApp payload.

    Useful for testing and debugging.

    Args:
        payload: The payload bytes to sign
        app_secret: The Meta app secret

    Returns:
        The signature in "sha256=<hex_digest>" format
    """
    signature = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return f"sha256={signature}"
