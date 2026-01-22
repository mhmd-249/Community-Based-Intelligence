"""
Webhook endpoints for messaging platforms.

Handles incoming messages from Telegram and WhatsApp with proper
verification, parsing, signature validation, and message queuing.
"""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from cbi.config import get_logger, get_settings
from cbi.services.message_queue import queue_incoming_message
from cbi.services.messaging import (
    IncomingMessage,
    MessagingError,
    MessagingParseError,
    get_gateway,
    get_gateway_for_message,
)
from cbi.services.webhook_security import (
    verify_telegram_secret_token,
    verify_whatsapp_signature,
)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = get_logger(__name__)
settings = get_settings()


async def _queue_message_background(message: IncomingMessage) -> None:
    """
    Background task to queue a message to Redis Stream.

    Args:
        message: The incoming message to queue
    """
    try:
        entry_id = await queue_incoming_message(message)
        logger.debug(
            "Message queued successfully",
            entry_id=entry_id,
            platform=message.platform,
            chat_id=message.chat_id,
        )
    except Exception as e:
        logger.error(
            "Failed to queue message",
            platform=message.platform,
            chat_id=message.chat_id,
            error=str(e),
        )


@router.get("/whatsapp")
async def whatsapp_verification(
    mode: str | None = Query(None, alias="hub.mode"),
    verify_token: str | None = Query(None, alias="hub.verify_token"),
    challenge: str | None = Query(None, alias="hub.challenge"),
) -> PlainTextResponse:
    """
    WhatsApp webhook verification endpoint.

    Meta requires this endpoint to verify webhook URL ownership during setup.
    The verification process:
    1. Meta sends GET request with hub.mode, hub.verify_token, hub.challenge
    2. We validate the verify_token matches our configured token
    3. On success, return hub.challenge as plain text
    4. On failure, return 403 Forbidden

    Args:
        mode: Should be "subscribe" for verification requests
        verify_token: Token to validate against our configuration
        challenge: Challenge string to return on success

    Returns:
        PlainTextResponse with the challenge on success

    Raises:
        HTTPException: 403 if verification fails
    """
    logger.info(
        "WhatsApp verification request",
        mode=mode,
        has_token=verify_token is not None,
        has_challenge=challenge is not None,
    )

    # Validate the verification request
    if mode != "subscribe":
        logger.warning("Invalid hub.mode for WhatsApp verification", mode=mode)
        raise HTTPException(status_code=403, detail="Invalid verification mode")

    if not challenge:
        logger.warning("Missing hub.challenge in WhatsApp verification")
        raise HTTPException(status_code=403, detail="Missing challenge")

    # Validate the verify token
    configured_token = settings.whatsapp_verify_token
    if not configured_token:
        logger.error("WHATSAPP_VERIFY_TOKEN not configured")
        raise HTTPException(status_code=403, detail="Webhook not configured")

    if verify_token != configured_token:
        logger.warning("Invalid verify_token for WhatsApp verification")
        raise HTTPException(status_code=403, detail="Invalid verify token")

    logger.info("WhatsApp webhook verification successful")
    return PlainTextResponse(content=challenge)


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    Handle incoming WhatsApp webhook events.

    Receives messages from WhatsApp Business API, verifies the signature,
    parses the messages, and queues them for async processing.

    The webhook payload structure:
    {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {...},
                    "contacts": [...],
                    "messages": [...]
                },
                "field": "messages"
            }]
        }]
    }

    Args:
        request: The incoming HTTP request
        background_tasks: FastAPI background tasks for async processing

    Returns:
        Acknowledgment response {"status": "ok"}
    """
    # Get raw body for signature verification
    raw_body = await request.body()

    # Verify signature if app secret is configured
    if settings.whatsapp_app_secret:
        signature = request.headers.get("X-Hub-Signature-256")
        if not verify_whatsapp_signature(raw_body, signature):
            logger.warning("WhatsApp webhook signature verification failed")
            raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse JSON body
    try:
        body: dict[str, Any] = await request.json()
    except Exception as e:
        logger.error("Failed to parse WhatsApp webhook JSON", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON") from e

    # Log the incoming webhook (no PII)
    logger.info(
        "Received WhatsApp webhook",
        object_type=body.get("object"),
        entry_count=len(body.get("entry", [])),
    )

    # Parse and queue messages
    try:
        gateway = get_gateway("whatsapp")
        messages = gateway.parse_webhook(body)

        for msg in messages:
            logger.info(
                "Parsed WhatsApp message",
                message_id=msg.message_id,
                has_text=msg.text is not None,
            )
            # Queue message for async processing
            background_tasks.add_task(_queue_message_background, msg)

    except MessagingParseError as e:
        logger.warning(
            "Failed to parse WhatsApp webhook",
            error=str(e),
            platform=e.platform,
        )
    except MessagingError as e:
        logger.error(
            "Messaging error processing WhatsApp webhook",
            error=str(e),
            platform=e.platform,
        )
    except Exception as e:
        # Log but don't fail - WhatsApp expects 200 OK
        logger.exception("Unexpected error processing WhatsApp webhook", error=str(e))

    # Always return 200 OK to acknowledge receipt
    # WhatsApp will retry if we don't acknowledge quickly
    return {"status": "ok"}


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, bool]:
    """
    Handle incoming Telegram webhook events.

    Receives updates from Telegram Bot API, validates (if secret token configured),
    parses messages, and queues them for async processing.

    Args:
        request: The incoming HTTP request
        background_tasks: FastAPI background tasks for async processing

    Returns:
        Acknowledgment response {"ok": true} (Telegram format)
    """
    # Verify secret token if configured
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not verify_telegram_secret_token(secret_token):
        logger.warning("Telegram webhook secret token verification failed")
        raise HTTPException(status_code=403, detail="Invalid secret token")

    # Parse JSON body
    try:
        body: dict[str, Any] = await request.json()
    except Exception as e:
        logger.error("Failed to parse Telegram webhook JSON", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON") from e

    update_id = body.get("update_id")

    # Check if this is a message update (not edit, callback, etc.)
    has_message = "message" in body
    has_edited = "edited_message" in body

    logger.info(
        "Received Telegram webhook",
        update_id=update_id,
        has_message=has_message,
        has_edited=has_edited,
    )

    # Only process message updates (skip edited messages, callbacks, etc.)
    if not has_message:
        logger.debug(
            "Skipping non-message Telegram update",
            update_id=update_id,
            keys=list(body.keys()),
        )
        return {"ok": True}

    # Parse and queue messages
    try:
        gateway = get_gateway("telegram")
        messages = gateway.parse_webhook(body)

        for msg in messages:
            logger.info(
                "Parsed Telegram message",
                message_id=msg.message_id,
                has_text=msg.text is not None,
            )
            # Queue message for async processing
            background_tasks.add_task(_queue_message_background, msg)

    except MessagingParseError as e:
        logger.warning(
            "Failed to parse Telegram webhook",
            error=str(e),
            platform=e.platform,
        )
    except MessagingError as e:
        logger.error(
            "Messaging error processing Telegram webhook",
            error=str(e),
            platform=e.platform,
        )
    except Exception as e:
        # Log but don't fail
        logger.exception("Unexpected error processing Telegram webhook", error=str(e))

    # Telegram expects {"ok": true} response
    return {"ok": True}


@router.post("/auto")
async def auto_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    Auto-detect platform and handle webhook.

    Inspects the payload to determine the platform (Telegram or WhatsApp)
    and routes to the appropriate handler. Note: signature verification
    is skipped in auto mode - use platform-specific endpoints for production.

    Args:
        request: The incoming HTTP request
        background_tasks: FastAPI background tasks for async processing

    Returns:
        Acknowledgment response
    """
    try:
        body: dict[str, Any] = await request.json()
    except Exception as e:
        logger.error("Failed to parse webhook JSON", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON") from e

    # Auto-detect platform
    result = get_gateway_for_message(body)

    if result is None:
        logger.warning(
            "Could not detect platform from webhook",
            keys=list(body.keys())[:5],
        )
        return {"status": "unknown_platform"}

    gateway, platform = result
    logger.info("Auto-detected webhook platform", platform=platform)

    try:
        messages = gateway.parse_webhook(body)

        for msg in messages:
            logger.info(
                "Parsed message",
                platform=platform,
                message_id=msg.message_id,
                has_text=msg.text is not None,
            )
            # Queue message for async processing
            background_tasks.add_task(_queue_message_background, msg)

    except MessagingError as e:
        logger.warning(
            "Failed to parse webhook",
            platform=platform,
            error=str(e),
        )
    except Exception as e:
        logger.exception("Unexpected error processing webhook", error=str(e))

    return {"status": "ok"}
