"""
Integration tests for webhook endpoints.

Tests HTTP behavior, signature validation, message parsing for
Telegram, WhatsApp, and auto-detect webhooks.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

from cbi.services.webhook_security import compute_whatsapp_signature


# =============================================================================
# Telegram Webhook Payloads
# =============================================================================

VALID_TELEGRAM_UPDATE = {
    "update_id": 123456789,
    "message": {
        "message_id": 1,
        "from": {
            "id": 987654321,
            "is_bot": False,
            "first_name": "Test",
            "language_code": "ar",
        },
        "chat": {"id": 987654321, "type": "private", "first_name": "Test"},
        "date": 1700000000,
        "text": "I have a health concern",
    },
}

CALLBACK_QUERY_UPDATE = {
    "update_id": 123456790,
    "callback_query": {
        "id": "1234",
        "from": {"id": 987654321, "is_bot": False, "first_name": "Test"},
        "data": "some_callback_data",
    },
}

EDITED_MESSAGE_UPDATE = {
    "update_id": 123456791,
    "edited_message": {
        "message_id": 1,
        "from": {"id": 987654321, "is_bot": False, "first_name": "Test"},
        "chat": {"id": 987654321, "type": "private"},
        "date": 1700000000,
        "edit_date": 1700000001,
        "text": "Edited message",
    },
}


# =============================================================================
# WhatsApp Webhook Payloads
# =============================================================================

VALID_WHATSAPP_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15551234567",
                            "phone_number_id": "0000000000",
                        },
                        "contacts": [
                            {"profile": {"name": "Test User"}, "wa_id": "249123456789"}
                        ],
                        "messages": [
                            {
                                "from": "249123456789",
                                "id": "wamid.abc123",
                                "timestamp": "1700000000",
                                "text": {"body": "I feel sick"},
                                "type": "text",
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}


# =============================================================================
# TestTelegramWebhook
# =============================================================================


class TestTelegramWebhook:
    """Tests for POST /webhooks/telegram."""

    @pytest.mark.asyncio
    async def test_valid_message_returns_ok(self, app_client):
        """POST valid Telegram update → 200 + {"ok": true}."""
        with patch(
            "cbi.api.routes.webhooks._queue_message_background",
            new_callable=AsyncMock,
        ):
            resp = await app_client.post(
                "/webhooks/telegram",
                json=VALID_TELEGRAM_UPDATE,
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_invalid_secret_token_returns_403(self, app_client):
        """Wrong secret token header → 403."""
        with patch(
            "cbi.api.routes.webhooks.settings"
        ) as mock_settings:
            mock_settings.telegram_webhook_secret.get_secret_value.return_value = "correct-token"
            with patch(
                "cbi.services.webhook_security.get_settings"
            ) as mock_sec_settings:
                mock_sec_settings.return_value.telegram_webhook_secret.get_secret_value.return_value = "correct-token"

                resp = await app_client.post(
                    "/webhooks/telegram",
                    json=VALID_TELEGRAM_UPDATE,
                    headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-token"},
                )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_secret_configured_passes(self, app_client):
        """Without secret configured, any request passes."""
        # Default test settings have no telegram_webhook_secret
        with patch(
            "cbi.api.routes.webhooks._queue_message_background",
            new_callable=AsyncMock,
        ):
            resp = await app_client.post(
                "/webhooks/telegram",
                json=VALID_TELEGRAM_UPDATE,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_malformed_json_returns_400(self, app_client):
        """Non-JSON body → 400."""
        resp = await app_client.post(
            "/webhooks/telegram",
            content=b"this is not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_non_message_update_skipped(self, app_client):
        """callback_query update → ok, no queue."""
        with patch(
            "cbi.api.routes.webhooks._queue_message_background",
            new_callable=AsyncMock,
        ) as mock_queue:
            resp = await app_client.post(
                "/webhooks/telegram",
                json=CALLBACK_QUERY_UPDATE,
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_queue.assert_not_called()

    @pytest.mark.asyncio
    async def test_edited_message_skipped(self, app_client):
        """edited_message → ok, no queue."""
        with patch(
            "cbi.api.routes.webhooks._queue_message_background",
            new_callable=AsyncMock,
        ) as mock_queue:
            resp = await app_client.post(
                "/webhooks/telegram",
                json=EDITED_MESSAGE_UPDATE,
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_queue.assert_not_called()

    @pytest.mark.asyncio
    async def test_message_queued_to_redis(self, app_client):
        """Valid message triggers _queue_message_background with correct IncomingMessage."""
        with patch(
            "cbi.api.routes.webhooks._queue_message_background",
            new_callable=AsyncMock,
        ) as mock_queue:
            resp = await app_client.post(
                "/webhooks/telegram",
                json=VALID_TELEGRAM_UPDATE,
            )
        assert resp.status_code == 200
        mock_queue.assert_called_once()
        msg = mock_queue.call_args[0][0]
        assert msg.platform == "telegram"
        assert msg.text == "I have a health concern"


# =============================================================================
# TestWhatsAppWebhook
# =============================================================================


class TestWhatsAppWebhook:
    """Tests for /webhooks/whatsapp."""

    @pytest.mark.asyncio
    async def test_valid_signature_returns_ok(self, app_client):
        """Use compute_whatsapp_signature helper, valid signature → 200."""
        payload_bytes = json.dumps(VALID_WHATSAPP_PAYLOAD).encode()
        app_secret = "test-whatsapp-app-secret"
        signature = compute_whatsapp_signature(payload_bytes, app_secret)

        with patch(
            "cbi.api.routes.webhooks.settings"
        ) as mock_settings, patch(
            "cbi.api.routes.webhooks._queue_message_background",
            new_callable=AsyncMock,
        ):
            mock_settings.whatsapp_app_secret.get_secret_value.return_value = app_secret
            with patch(
                "cbi.services.webhook_security.get_settings"
            ) as mock_sec:
                mock_sec.return_value.whatsapp_app_secret.get_secret_value.return_value = app_secret
                resp = await app_client.post(
                    "/webhooks/whatsapp",
                    content=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-Hub-Signature-256": signature,
                    },
                )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_403(self, app_client):
        """Wrong HMAC → 403."""
        payload_bytes = json.dumps(VALID_WHATSAPP_PAYLOAD).encode()
        app_secret = "test-whatsapp-app-secret"

        with patch(
            "cbi.api.routes.webhooks.settings"
        ) as mock_settings:
            mock_settings.whatsapp_app_secret.get_secret_value.return_value = app_secret
            with patch(
                "cbi.services.webhook_security.get_settings"
            ) as mock_sec:
                mock_sec.return_value.whatsapp_app_secret.get_secret_value.return_value = app_secret
                resp = await app_client.post(
                    "/webhooks/whatsapp",
                    content=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
                    },
                )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_secret_configured_skips_check(self, app_client):
        """Without WHATSAPP_APP_SECRET, no signature verification."""
        with patch(
            "cbi.api.routes.webhooks.settings"
        ) as mock_settings, patch(
            "cbi.api.routes.webhooks._queue_message_background",
            new_callable=AsyncMock,
        ):
            mock_settings.whatsapp_app_secret = None
            resp = await app_client.post(
                "/webhooks/whatsapp",
                json=VALID_WHATSAPP_PAYLOAD,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_verification_challenge_success(self, app_client):
        """GET with correct verify_token returns challenge."""
        with patch(
            "cbi.api.routes.webhooks.settings"
        ) as mock_settings:
            mock_settings.whatsapp_verify_token = "my-verify-token"
            resp = await app_client.get(
                "/webhooks/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "my-verify-token",
                    "hub.challenge": "challenge_string_123",
                },
            )
        assert resp.status_code == 200
        assert resp.text == "challenge_string_123"

    @pytest.mark.asyncio
    async def test_verification_wrong_token_returns_403(self, app_client):
        """GET with wrong verify_token → 403."""
        with patch(
            "cbi.api.routes.webhooks.settings"
        ) as mock_settings:
            mock_settings.whatsapp_verify_token = "correct-token"
            resp = await app_client.get(
                "/webhooks/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "wrong-token",
                    "hub.challenge": "challenge_string_123",
                },
            )
        assert resp.status_code == 403


# =============================================================================
# TestAutoWebhook
# =============================================================================


class TestAutoWebhook:
    """Tests for POST /webhooks/auto (platform auto-detection)."""

    @pytest.mark.asyncio
    async def test_auto_detect_telegram(self, app_client):
        """Telegram payload detected and processed."""
        with patch(
            "cbi.api.routes.webhooks._queue_message_background",
            new_callable=AsyncMock,
        ):
            resp = await app_client.post(
                "/webhooks/auto",
                json=VALID_TELEGRAM_UPDATE,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_unknown_platform(self, app_client):
        """Unrecognized payload → {"status": "unknown_platform"}."""
        resp = await app_client.post(
            "/webhooks/auto",
            json={"some_random_key": "value"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "unknown_platform"
