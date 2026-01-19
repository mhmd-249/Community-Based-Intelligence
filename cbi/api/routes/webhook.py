"""
Webhook endpoints for messaging platforms.

Handles incoming messages from Telegram and WhatsApp.
"""

from typing import Any

from fastapi import APIRouter, Request, Response

from cbi.config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/telegram")
async def telegram_webhook(request: Request) -> dict[str, str]:
    """
    Handle incoming Telegram webhook events.

    Receives updates from Telegram Bot API and queues them for processing.

    TODO: Implement in Phase 2
    - Validate webhook signature
    - Parse Telegram update
    - Queue message for agent processing
    """
    body = await request.json()
    logger.info("Received Telegram webhook", update_id=body.get("update_id"))

    return {"status": "received"}


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request) -> dict[str, str]:
    """
    Handle incoming WhatsApp webhook events.

    Receives messages from WhatsApp Business API.

    TODO: Implement in Phase 2
    - Validate webhook signature
    - Parse WhatsApp message
    - Queue message for agent processing
    """
    body = await request.json()
    logger.info("Received WhatsApp webhook")

    return {"status": "received"}


@router.get("/whatsapp")
async def whatsapp_verification(
    hub_mode: str | None = None,
    hub_challenge: str | None = None,
    hub_verify_token: str | None = None,
) -> Response:
    """
    WhatsApp webhook verification endpoint.

    Meta requires this endpoint to verify webhook URL ownership.

    TODO: Implement in Phase 2
    - Validate verify_token against settings
    - Return hub.challenge on success
    """
    # Placeholder - return challenge for any request
    if hub_mode == "subscribe" and hub_challenge:
        return Response(content=hub_challenge, media_type="text/plain")

    return Response(content="Verification failed", status_code=403)
