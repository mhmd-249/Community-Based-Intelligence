"""
Unit tests for phone hashing and encryption functionality.

Tests the crypto operations used for phone number privacy in CBI.
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from cbi.services.state import StateService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_settings():
    """Create mock settings with test values."""
    settings = MagicMock()
    settings.phone_hash_salt.get_secret_value.return_value = "test_salt_12345"
    settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"
    return settings


@pytest.fixture
def state_service(mock_settings):
    """Create StateService instance with mocked settings."""
    with patch("cbi.services.state.get_settings", return_value=mock_settings):
        service = StateService()
        return service


# =============================================================================
# Tests for Phone Hashing
# =============================================================================


class TestPhoneHashing:
    """Tests for phone number hashing functionality."""

    def test_hash_produces_consistent_output(self, state_service: StateService) -> None:
        """Same phone should always produce the same hash."""
        phone = "+249123456789"

        hash1 = state_service._phone_hash(phone)
        hash2 = state_service._phone_hash(phone)

        assert hash1 == hash2

    def test_hash_is_16_characters(self, state_service: StateService) -> None:
        """Hash should be truncated to 16 hex characters."""
        phone = "+249123456789"
        hash_result = state_service._phone_hash(phone)

        assert len(hash_result) == 16

    def test_hash_is_hex_string(self, state_service: StateService) -> None:
        """Hash should be valid hexadecimal."""
        phone = "+249123456789"
        hash_result = state_service._phone_hash(phone)

        # Should not raise ValueError if valid hex
        int(hash_result, 16)

    def test_different_phones_produce_different_hashes(
        self, state_service: StateService
    ) -> None:
        """Different phones should produce different hashes."""
        phone1 = "+249123456789"
        phone2 = "+249987654321"

        hash1 = state_service._phone_hash(phone1)
        hash2 = state_service._phone_hash(phone2)

        assert hash1 != hash2

    def test_hash_includes_salt(self, mock_settings) -> None:
        """Hash should incorporate the salt from settings."""
        phone = "+249123456789"
        salt = mock_settings.phone_hash_salt.get_secret_value()

        # Calculate expected hash
        expected_full = hashlib.sha256(f"{salt}{phone}".encode()).hexdigest()
        expected = expected_full[:16]

        with patch("cbi.services.state.get_settings", return_value=mock_settings):
            service = StateService()
            actual = service._phone_hash(phone)

        assert actual == expected

    def test_different_salts_produce_different_hashes(self) -> None:
        """Different salts should produce different hashes for same phone."""
        phone = "+249123456789"

        # Create two services with different salts
        settings1 = MagicMock()
        settings1.phone_hash_salt.get_secret_value.return_value = "salt_one"
        settings1.redis_url.get_secret_value.return_value = "redis://localhost"

        settings2 = MagicMock()
        settings2.phone_hash_salt.get_secret_value.return_value = "salt_two"
        settings2.redis_url.get_secret_value.return_value = "redis://localhost"

        with patch("cbi.services.state.get_settings", return_value=settings1):
            service1 = StateService()
            hash1 = service1._phone_hash(phone)

        with patch("cbi.services.state.get_settings", return_value=settings2):
            service2 = StateService()
            hash2 = service2._phone_hash(phone)

        assert hash1 != hash2


# =============================================================================
# Tests for Different Phone Formats
# =============================================================================


class TestPhoneFormats:
    """Tests for handling various phone number formats."""

    def test_sudanese_format_with_country_code(
        self, state_service: StateService
    ) -> None:
        """Should handle Sudanese numbers with +249 prefix."""
        phone = "+249123456789"
        hash_result = state_service._phone_hash(phone)
        assert len(hash_result) == 16

    def test_sudanese_format_with_00_prefix(
        self, state_service: StateService
    ) -> None:
        """Should handle numbers with 00 prefix."""
        phone = "00249123456789"
        hash_result = state_service._phone_hash(phone)
        assert len(hash_result) == 16

    def test_local_format_without_country_code(
        self, state_service: StateService
    ) -> None:
        """Should handle local format without country code."""
        phone = "0123456789"
        hash_result = state_service._phone_hash(phone)
        assert len(hash_result) == 16

    def test_format_with_spaces(self, state_service: StateService) -> None:
        """Should handle numbers with spaces."""
        phone = "+249 123 456 789"
        hash_result = state_service._phone_hash(phone)
        assert len(hash_result) == 16

    def test_format_with_dashes(self, state_service: StateService) -> None:
        """Should handle numbers with dashes."""
        phone = "+249-123-456-789"
        hash_result = state_service._phone_hash(phone)
        assert len(hash_result) == 16

    def test_different_formats_produce_different_hashes(
        self, state_service: StateService
    ) -> None:
        """Different formats of same logical number produce different hashes.

        Note: This is expected behavior - the system does not normalize phone numbers.
        Phone numbers should be normalized before hashing if needed.
        """
        phone1 = "+249123456789"
        phone2 = "00249123456789"

        hash1 = state_service._phone_hash(phone1)
        hash2 = state_service._phone_hash(phone2)

        # These are different strings, so they produce different hashes
        assert hash1 != hash2

    def test_whatsapp_phone_format(self, state_service: StateService) -> None:
        """Should handle WhatsApp phone format (no + prefix)."""
        # WhatsApp often sends numbers without + prefix
        phone = "249123456789"
        hash_result = state_service._phone_hash(phone)
        assert len(hash_result) == 16

    def test_empty_phone_hashes_to_something(
        self, state_service: StateService
    ) -> None:
        """Empty phone should still produce a hash (edge case)."""
        phone = ""
        hash_result = state_service._phone_hash(phone)
        assert len(hash_result) == 16

    def test_phone_with_parentheses(self, state_service: StateService) -> None:
        """Should handle numbers with parentheses."""
        phone = "+249(91)2345678"
        hash_result = state_service._phone_hash(phone)
        assert len(hash_result) == 16

    def test_very_long_phone_number(self, state_service: StateService) -> None:
        """Should handle unusually long phone numbers."""
        phone = "+12345678901234567890"
        hash_result = state_service._phone_hash(phone)
        assert len(hash_result) == 16

    def test_short_phone_number(self, state_service: StateService) -> None:
        """Should handle short phone numbers."""
        phone = "123"
        hash_result = state_service._phone_hash(phone)
        assert len(hash_result) == 16


# =============================================================================
# Tests for Hash Security Properties
# =============================================================================


class TestHashSecurity:
    """Tests for security properties of phone hashing."""

    def test_hash_is_not_reversible(self, state_service: StateService) -> None:
        """Hash output should not contain the original phone number."""
        phone = "+249123456789"
        hash_result = state_service._phone_hash(phone)

        # Hash should not contain any part of the phone number
        assert "249" not in hash_result
        assert "123" not in hash_result

    def test_hash_deterministic_across_instances(self, mock_settings) -> None:
        """Same settings should produce same hash across instances."""
        phone = "+249123456789"

        with patch("cbi.services.state.get_settings", return_value=mock_settings):
            service1 = StateService()
            service2 = StateService()

            hash1 = service1._phone_hash(phone)
            hash2 = service2._phone_hash(phone)

        assert hash1 == hash2

    def test_hash_uses_sha256(self, mock_settings) -> None:
        """Hash should use SHA-256 algorithm."""
        phone = "+249123456789"
        salt = mock_settings.phone_hash_salt.get_secret_value()

        # Calculate using SHA-256 directly
        expected = hashlib.sha256(f"{salt}{phone}".encode()).hexdigest()[:16]

        with patch("cbi.services.state.get_settings", return_value=mock_settings):
            service = StateService()
            actual = service._phone_hash(phone)

        assert actual == expected

    def test_hash_truncation_preserves_uniqueness(
        self, state_service: StateService
    ) -> None:
        """16 character truncation should still maintain uniqueness."""
        phones = [
            "+249111111111",
            "+249222222222",
            "+249333333333",
            "+249444444444",
            "+249555555555",
            "+249666666666",
            "+249777777777",
            "+249888888888",
            "+249999999999",
            "+249000000000",
        ]

        hashes = [state_service._phone_hash(p) for p in phones]

        # All hashes should be unique
        assert len(set(hashes)) == len(phones)


# =============================================================================
# Tests for Redis Key Generation
# =============================================================================


class TestRedisKeyGeneration:
    """Tests for Redis key generation using phone hashes."""

    def test_conversation_key_format(self, state_service: StateService) -> None:
        """Conversation key should have correct format."""
        conv_id = "conv_abc123"
        key = state_service._conversation_key(conv_id)

        assert key == "cbi:conversation:conv_abc123"

    def test_session_key_format(self, state_service: StateService) -> None:
        """Session key should include platform and phone hash."""
        platform = "telegram"
        phone_hash = "abcdef1234567890"
        key = state_service._session_key(platform, phone_hash)

        assert key == "cbi:session:telegram:abcdef1234567890"

    def test_session_key_with_whatsapp(self, state_service: StateService) -> None:
        """Session key should work with WhatsApp platform."""
        platform = "whatsapp"
        phone_hash = "fedcba0987654321"
        key = state_service._session_key(platform, phone_hash)

        assert key == "cbi:session:whatsapp:fedcba0987654321"

    def test_session_keys_different_for_same_phone_different_platform(
        self, state_service: StateService
    ) -> None:
        """Same phone on different platforms should have different session keys."""
        phone_hash = "abcdef1234567890"

        telegram_key = state_service._session_key("telegram", phone_hash)
        whatsapp_key = state_service._session_key("whatsapp", phone_hash)

        assert telegram_key != whatsapp_key
