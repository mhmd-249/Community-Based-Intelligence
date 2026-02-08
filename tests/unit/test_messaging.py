"""
Unit tests for messaging gateway functionality.

Tests webhook parsing for Telegram and WhatsApp, and OutgoingMessage formatting.
"""

from datetime import UTC, datetime

import pytest

from cbi.services.messaging.base import IncomingMessage, OutgoingMessage
from cbi.services.messaging.exceptions import MessagingParseError
from cbi.services.messaging.telegram import TelegramGateway
from cbi.services.messaging.whatsapp import WhatsAppGateway


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def telegram_gateway() -> TelegramGateway:
    """Create Telegram gateway for testing."""
    return TelegramGateway(bot_token="test_token_123")


@pytest.fixture
def whatsapp_gateway() -> WhatsAppGateway:
    """Create WhatsApp gateway for testing."""
    return WhatsAppGateway(
        phone_number_id="123456789",
        access_token="test_access_token",
    )


@pytest.fixture
def telegram_message_update() -> dict:
    """Sample Telegram message update."""
    return {
        "update_id": 123456789,
        "message": {
            "message_id": 42,
            "from": {
                "id": 987654321,
                "is_bot": False,
                "first_name": "John",
                "last_name": "Doe",
            },
            "chat": {
                "id": 987654321,
                "first_name": "John",
                "last_name": "Doe",
                "type": "private",
            },
            "date": 1699000000,
            "text": "Hello, I want to report an illness",
        },
    }


@pytest.fixture
def telegram_arabic_message() -> dict:
    """Sample Telegram message in Arabic."""
    return {
        "update_id": 123456790,
        "message": {
            "message_id": 43,
            "from": {"id": 111222333, "is_bot": False, "first_name": "Ahmed"},
            "chat": {"id": 111222333, "type": "private"},
            "date": 1699000100,
            "text": "السلام عليكم، أريد الإبلاغ عن مرض",
        },
    }


@pytest.fixture
def whatsapp_message_webhook() -> dict:
    """Sample WhatsApp message webhook."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "123456789",
                            },
                            "contacts": [
                                {
                                    "wa_id": "249123456789",
                                    "profile": {"name": "John Doe"},
                                }
                            ],
                            "messages": [
                                {
                                    "from": "249123456789",
                                    "id": "wamid.abc123def456",
                                    "timestamp": "1699000000",
                                    "type": "text",
                                    "text": {"body": "I need to report sick people"},
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
# Tests for Telegram Webhook Parsing
# =============================================================================


class TestTelegramWebhookParsing:
    """Tests for Telegram webhook parsing."""

    def test_parses_text_message(
        self, telegram_gateway: TelegramGateway, telegram_message_update: dict
    ) -> None:
        """Should parse text message from Telegram webhook."""
        messages = telegram_gateway.parse_webhook(telegram_message_update)

        assert len(messages) == 1
        msg = messages[0]
        assert isinstance(msg, IncomingMessage)
        assert msg.platform == "telegram"
        assert msg.text == "Hello, I want to report an illness"

    def test_extracts_message_id(
        self, telegram_gateway: TelegramGateway, telegram_message_update: dict
    ) -> None:
        """Should extract message ID."""
        messages = telegram_gateway.parse_webhook(telegram_message_update)
        assert messages[0].message_id == "42"

    def test_extracts_chat_id(
        self, telegram_gateway: TelegramGateway, telegram_message_update: dict
    ) -> None:
        """Should extract chat ID."""
        messages = telegram_gateway.parse_webhook(telegram_message_update)
        assert messages[0].chat_id == "987654321"

    def test_extracts_from_id(
        self, telegram_gateway: TelegramGateway, telegram_message_update: dict
    ) -> None:
        """Should extract sender ID."""
        messages = telegram_gateway.parse_webhook(telegram_message_update)
        assert messages[0].from_id == "987654321"

    def test_extracts_timestamp(
        self, telegram_gateway: TelegramGateway, telegram_message_update: dict
    ) -> None:
        """Should extract and convert timestamp."""
        messages = telegram_gateway.parse_webhook(telegram_message_update)
        assert isinstance(messages[0].timestamp, datetime)

    def test_parses_arabic_message(
        self, telegram_gateway: TelegramGateway, telegram_arabic_message: dict
    ) -> None:
        """Should parse Arabic text correctly."""
        messages = telegram_gateway.parse_webhook(telegram_arabic_message)

        assert len(messages) == 1
        assert messages[0].text == "السلام عليكم، أريد الإبلاغ عن مرض"

    def test_parses_edited_message(
        self, telegram_gateway: TelegramGateway
    ) -> None:
        """Should parse edited messages."""
        update = {
            "update_id": 123456789,
            "edited_message": {
                "message_id": 42,
                "from": {"id": 987654321},
                "chat": {"id": 987654321},
                "date": 1699000000,
                "text": "Edited message text",
            },
        }

        messages = telegram_gateway.parse_webhook(update)
        assert len(messages) == 1
        assert messages[0].text == "Edited message text"

    def test_parses_reply_message(
        self, telegram_gateway: TelegramGateway
    ) -> None:
        """Should parse reply-to-message ID."""
        update = {
            "update_id": 123456789,
            "message": {
                "message_id": 43,
                "from": {"id": 987654321},
                "chat": {"id": 987654321},
                "date": 1699000000,
                "text": "This is a reply",
                "reply_to_message": {"message_id": 42},
            },
        }

        messages = telegram_gateway.parse_webhook(update)
        assert messages[0].reply_to_id == "42"

    def test_returns_empty_for_photo_message(
        self, telegram_gateway: TelegramGateway
    ) -> None:
        """Should return empty list for photo messages."""
        update = {
            "update_id": 123456789,
            "message": {
                "message_id": 42,
                "from": {"id": 987654321},
                "chat": {"id": 987654321},
                "date": 1699000000,
                "photo": [{"file_id": "abc123"}],
            },
        }

        messages = telegram_gateway.parse_webhook(update)
        assert messages == []

    def test_returns_empty_for_document_message(
        self, telegram_gateway: TelegramGateway
    ) -> None:
        """Should return empty list for document messages."""
        update = {
            "update_id": 123456789,
            "message": {
                "message_id": 42,
                "from": {"id": 987654321},
                "chat": {"id": 987654321},
                "date": 1699000000,
                "document": {"file_id": "abc123"},
            },
        }

        messages = telegram_gateway.parse_webhook(update)
        assert messages == []

    def test_returns_empty_for_sticker(
        self, telegram_gateway: TelegramGateway
    ) -> None:
        """Should return empty list for sticker messages."""
        update = {
            "update_id": 123456789,
            "message": {
                "message_id": 42,
                "from": {"id": 987654321},
                "chat": {"id": 987654321},
                "date": 1699000000,
                "sticker": {"file_id": "abc123"},
            },
        }

        messages = telegram_gateway.parse_webhook(update)
        assert messages == []

    def test_returns_empty_for_callback_query(
        self, telegram_gateway: TelegramGateway
    ) -> None:
        """Should return empty list for callback query updates."""
        update = {
            "update_id": 123456789,
            "callback_query": {
                "id": "abc123",
                "from": {"id": 987654321},
                "data": "button_click",
            },
        }

        messages = telegram_gateway.parse_webhook(update)
        assert messages == []

    def test_raises_error_for_invalid_payload(
        self, telegram_gateway: TelegramGateway
    ) -> None:
        """Should raise error for invalid payload type."""
        with pytest.raises(MessagingParseError):
            telegram_gateway.parse_webhook("not a dict")  # type: ignore

    def test_raises_error_for_none_payload(
        self, telegram_gateway: TelegramGateway
    ) -> None:
        """Should raise error for None payload."""
        with pytest.raises(MessagingParseError):
            telegram_gateway.parse_webhook(None)  # type: ignore


# =============================================================================
# Tests for WhatsApp Webhook Parsing
# =============================================================================


class TestWhatsAppWebhookParsing:
    """Tests for WhatsApp webhook parsing."""

    def test_parses_text_message(
        self, whatsapp_gateway: WhatsAppGateway, whatsapp_message_webhook: dict
    ) -> None:
        """Should parse text message from WhatsApp webhook."""
        messages = whatsapp_gateway.parse_webhook(whatsapp_message_webhook)

        assert len(messages) == 1
        msg = messages[0]
        assert isinstance(msg, IncomingMessage)
        assert msg.platform == "whatsapp"
        assert msg.text == "I need to report sick people"

    def test_extracts_message_id(
        self, whatsapp_gateway: WhatsAppGateway, whatsapp_message_webhook: dict
    ) -> None:
        """Should extract WhatsApp message ID."""
        messages = whatsapp_gateway.parse_webhook(whatsapp_message_webhook)
        assert messages[0].message_id == "wamid.abc123def456"

    def test_extracts_phone_as_chat_id(
        self, whatsapp_gateway: WhatsAppGateway, whatsapp_message_webhook: dict
    ) -> None:
        """Should use phone number as chat ID for WhatsApp."""
        messages = whatsapp_gateway.parse_webhook(whatsapp_message_webhook)
        assert messages[0].chat_id == "249123456789"

    def test_extracts_from_id(
        self, whatsapp_gateway: WhatsAppGateway, whatsapp_message_webhook: dict
    ) -> None:
        """Should extract sender phone number."""
        messages = whatsapp_gateway.parse_webhook(whatsapp_message_webhook)
        assert messages[0].from_id == "249123456789"

    def test_extracts_timestamp(
        self, whatsapp_gateway: WhatsAppGateway, whatsapp_message_webhook: dict
    ) -> None:
        """Should extract and convert timestamp."""
        messages = whatsapp_gateway.parse_webhook(whatsapp_message_webhook)
        assert isinstance(messages[0].timestamp, datetime)

    def test_parses_button_response(
        self, whatsapp_gateway: WhatsAppGateway
    ) -> None:
        """Should parse button response messages."""
        webhook = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "249123456789",
                                        "id": "wamid.xyz789",
                                        "timestamp": "1699000000",
                                        "type": "button",
                                        "button": {"text": "Yes, confirm"},
                                    }
                                ],
                                "contacts": [],
                            }
                        }
                    ]
                }
            ],
        }

        messages = whatsapp_gateway.parse_webhook(webhook)
        assert len(messages) == 1
        assert messages[0].text == "Yes, confirm"

    def test_parses_interactive_button_reply(
        self, whatsapp_gateway: WhatsAppGateway
    ) -> None:
        """Should parse interactive button reply."""
        webhook = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "249123456789",
                                        "id": "wamid.xyz789",
                                        "timestamp": "1699000000",
                                        "type": "interactive",
                                        "interactive": {
                                            "type": "button_reply",
                                            "button_reply": {
                                                "id": "btn_1",
                                                "title": "Report Now",
                                            },
                                        },
                                    }
                                ],
                                "contacts": [],
                            }
                        }
                    ]
                }
            ],
        }

        messages = whatsapp_gateway.parse_webhook(webhook)
        assert len(messages) == 1
        assert messages[0].text == "Report Now"

    def test_parses_interactive_list_reply(
        self, whatsapp_gateway: WhatsAppGateway
    ) -> None:
        """Should parse interactive list reply."""
        webhook = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "249123456789",
                                        "id": "wamid.xyz789",
                                        "timestamp": "1699000000",
                                        "type": "interactive",
                                        "interactive": {
                                            "type": "list_reply",
                                            "list_reply": {
                                                "id": "item_1",
                                                "title": "Cholera symptoms",
                                            },
                                        },
                                    }
                                ],
                                "contacts": [],
                            }
                        }
                    ]
                }
            ],
        }

        messages = whatsapp_gateway.parse_webhook(webhook)
        assert len(messages) == 1
        assert messages[0].text == "Cholera symptoms"

    def test_parses_reply_context(
        self, whatsapp_gateway: WhatsAppGateway
    ) -> None:
        """Should parse reply context."""
        webhook = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "249123456789",
                                        "id": "wamid.xyz789",
                                        "timestamp": "1699000000",
                                        "type": "text",
                                        "text": {"body": "This is a reply"},
                                        "context": {"id": "wamid.original123"},
                                    }
                                ],
                                "contacts": [],
                            }
                        }
                    ]
                }
            ],
        }

        messages = whatsapp_gateway.parse_webhook(webhook)
        assert messages[0].reply_to_id == "wamid.original123"

    def test_returns_empty_for_non_whatsapp_object(
        self, whatsapp_gateway: WhatsAppGateway
    ) -> None:
        """Should return empty list for non-WhatsApp webhook."""
        webhook = {"object": "instagram", "entry": []}

        messages = whatsapp_gateway.parse_webhook(webhook)
        assert messages == []

    def test_returns_empty_for_image_message(
        self, whatsapp_gateway: WhatsAppGateway
    ) -> None:
        """Should return empty list for image messages."""
        webhook = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "249123456789",
                                        "id": "wamid.xyz789",
                                        "timestamp": "1699000000",
                                        "type": "image",
                                        "image": {"id": "img123"},
                                    }
                                ],
                                "contacts": [],
                            }
                        }
                    ]
                }
            ],
        }

        messages = whatsapp_gateway.parse_webhook(webhook)
        assert messages == []

    def test_parses_multiple_messages(
        self, whatsapp_gateway: WhatsAppGateway
    ) -> None:
        """Should parse multiple messages in single webhook."""
        webhook = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "249123456789",
                                        "id": "wamid.msg1",
                                        "timestamp": "1699000000",
                                        "type": "text",
                                        "text": {"body": "First message"},
                                    },
                                    {
                                        "from": "249987654321",
                                        "id": "wamid.msg2",
                                        "timestamp": "1699000001",
                                        "type": "text",
                                        "text": {"body": "Second message"},
                                    },
                                ],
                                "contacts": [],
                            }
                        }
                    ]
                }
            ],
        }

        messages = whatsapp_gateway.parse_webhook(webhook)
        assert len(messages) == 2
        assert messages[0].text == "First message"
        assert messages[1].text == "Second message"

    def test_raises_error_for_invalid_payload(
        self, whatsapp_gateway: WhatsAppGateway
    ) -> None:
        """Should raise error for invalid payload."""
        with pytest.raises(MessagingParseError):
            whatsapp_gateway.parse_webhook("not a dict")  # type: ignore


# =============================================================================
# Tests for OutgoingMessage Formatting
# =============================================================================


class TestOutgoingMessageFormatting:
    """Tests for OutgoingMessage dataclass formatting."""

    def test_creates_basic_message(self) -> None:
        """Should create basic outgoing message."""
        msg = OutgoingMessage(chat_id="123456", text="Hello")

        assert msg.chat_id == "123456"
        assert msg.text == "Hello"
        assert msg.reply_to_id is None

    def test_creates_reply_message(self) -> None:
        """Should create reply message with reply_to_id."""
        msg = OutgoingMessage(
            chat_id="123456",
            text="This is a reply",
            reply_to_id="999",
        )

        assert msg.reply_to_id == "999"

    def test_handles_arabic_text(self) -> None:
        """Should handle Arabic text correctly."""
        msg = OutgoingMessage(
            chat_id="123456",
            text="مرحبا، شكراً لإبلاغك",
        )

        assert msg.text == "مرحبا، شكراً لإبلاغك"

    def test_handles_long_text(self) -> None:
        """Should handle long text messages."""
        long_text = "Hello " * 1000
        msg = OutgoingMessage(chat_id="123456", text=long_text)

        assert len(msg.text) == len(long_text)

    def test_handles_special_characters(self) -> None:
        """Should handle special characters."""
        msg = OutgoingMessage(
            chat_id="123456",
            text="Special chars: <>&'\"",
        )

        assert msg.text == "Special chars: <>&'\""

    def test_handles_newlines(self) -> None:
        """Should handle newlines in text."""
        msg = OutgoingMessage(
            chat_id="123456",
            text="Line 1\nLine 2\nLine 3",
        )

        assert "\n" in msg.text

    def test_empty_text_allowed(self) -> None:
        """Should allow empty text (edge case)."""
        msg = OutgoingMessage(chat_id="123456", text="")

        assert msg.text == ""


# =============================================================================
# Tests for IncomingMessage Dataclass
# =============================================================================


class TestIncomingMessage:
    """Tests for IncomingMessage dataclass."""

    def test_creates_incoming_message(self) -> None:
        """Should create incoming message with all fields."""
        msg = IncomingMessage(
            platform="telegram",
            message_id="42",
            chat_id="123456",
            from_id="789",
            text="Hello",
            timestamp=datetime.now(UTC),
        )

        assert msg.platform == "telegram"
        assert msg.message_id == "42"
        assert msg.text == "Hello"

    def test_is_frozen(self) -> None:
        """IncomingMessage should be immutable (frozen)."""
        msg = IncomingMessage(
            platform="telegram",
            message_id="42",
            chat_id="123456",
            from_id="789",
            text="Hello",
            timestamp=datetime.now(UTC),
        )

        # Attempting to modify should raise
        with pytest.raises(AttributeError):
            msg.text = "Modified"  # type: ignore

    def test_allows_none_text(self) -> None:
        """Should allow None text for media messages."""
        msg = IncomingMessage(
            platform="telegram",
            message_id="42",
            chat_id="123456",
            from_id="789",
            text=None,
            timestamp=datetime.now(UTC),
        )

        assert msg.text is None

    def test_default_reply_to_id_is_none(self) -> None:
        """Default reply_to_id should be None."""
        msg = IncomingMessage(
            platform="telegram",
            message_id="42",
            chat_id="123456",
            from_id="789",
            text="Hello",
            timestamp=datetime.now(UTC),
        )

        assert msg.reply_to_id is None

    def test_equality(self) -> None:
        """Should support equality comparison."""
        ts = datetime.now(UTC)

        msg1 = IncomingMessage(
            platform="telegram",
            message_id="42",
            chat_id="123456",
            from_id="789",
            text="Hello",
            timestamp=ts,
        )

        msg2 = IncomingMessage(
            platform="telegram",
            message_id="42",
            chat_id="123456",
            from_id="789",
            text="Hello",
            timestamp=ts,
        )

        assert msg1 == msg2
