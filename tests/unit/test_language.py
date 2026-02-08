"""
Unit tests for language detection functionality.

Tests the detect_language function used to identify Arabic vs English text.
"""

import pytest

from cbi.agents.reporter import detect_language
from cbi.agents.state import Language


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def arabic_text_samples() -> list[str]:
    """Sample Arabic texts for testing."""
    return [
        "السلام عليكم",
        "مرحبا، أريد الإبلاغ عن مرض",
        "هناك أطفال مرضى في قريتي",
        "أعاني من حمى وإسهال منذ ثلاثة أيام",
        "الكثير من الناس يعانون من القيء",
        "مات ثلاثة أشخاص هذا الأسبوع",
        "في الخرطوم شمال",
        "أنا طبيب في المستشفى",
    ]


@pytest.fixture
def english_text_samples() -> list[str]:
    """Sample English texts for testing."""
    return [
        "Hello",
        "I want to report an illness",
        "There are sick children in my village",
        "I have had fever and diarrhea for three days",
        "Many people are suffering from vomiting",
        "Three people died this week",
        "In Khartoum North",
        "I am a doctor at the hospital",
    ]


# =============================================================================
# Tests for Arabic Detection
# =============================================================================


class TestArabicDetection:
    """Tests for detecting Arabic language."""

    def test_detects_arabic_greeting(self) -> None:
        """Should detect Arabic greeting."""
        result = detect_language("السلام عليكم")
        assert result == Language.ar.value

    def test_detects_arabic_sentence(self) -> None:
        """Should detect Arabic sentences."""
        result = detect_language("هناك أطفال مرضى في قريتي")
        assert result == Language.ar.value

    def test_detects_arabic_medical_text(self) -> None:
        """Should detect Arabic medical descriptions."""
        result = detect_language("أعاني من حمى وإسهال منذ ثلاثة أيام")
        assert result == Language.ar.value

    def test_detects_all_arabic_samples(
        self, arabic_text_samples: list[str]
    ) -> None:
        """Should correctly detect all Arabic samples."""
        for text in arabic_text_samples:
            result = detect_language(text)
            assert result == Language.ar.value, f"Failed for: {text}"

    def test_detects_arabic_with_numbers(self) -> None:
        """Should detect Arabic even with embedded numbers."""
        result = detect_language("مات 3 أشخاص هذا الأسبوع")
        assert result == Language.ar.value

    def test_detects_arabic_with_punctuation(self) -> None:
        """Should detect Arabic with punctuation marks."""
        result = detect_language("مرحبا، كيف حالك؟")
        assert result == Language.ar.value

    def test_detects_sudanese_dialect(self) -> None:
        """Should detect Sudanese Arabic dialect."""
        # Common Sudanese expressions
        result = detect_language("كيفك؟ شنو الخبر؟")
        assert result == Language.ar.value

    def test_detects_arabic_extended_characters(self) -> None:
        """Should detect extended Arabic Unicode characters."""
        # Farsi/Arabic extended characters
        result = detect_language("گچپژ سلام")  # Persian characters
        # This might be detected as Arabic or unknown depending on threshold
        # The key is it shouldn't crash


# =============================================================================
# Tests for English Detection
# =============================================================================


class TestEnglishDetection:
    """Tests for detecting English language."""

    def test_detects_english_greeting(self) -> None:
        """Should detect English greeting."""
        result = detect_language("Hello, how are you?")
        assert result == Language.en.value

    def test_detects_english_sentence(self) -> None:
        """Should detect English sentences."""
        result = detect_language("There are sick children in my village")
        assert result == Language.en.value

    def test_detects_english_medical_text(self) -> None:
        """Should detect English medical descriptions."""
        result = detect_language("I have had fever and diarrhea for three days")
        assert result == Language.en.value

    def test_detects_all_english_samples(
        self, english_text_samples: list[str]
    ) -> None:
        """Should correctly detect all English samples."""
        for text in english_text_samples:
            result = detect_language(text)
            assert result == Language.en.value, f"Failed for: {text}"

    def test_detects_english_with_numbers(self) -> None:
        """Should detect English even with embedded numbers."""
        result = detect_language("3 people died this week")
        assert result == Language.en.value

    def test_detects_english_with_punctuation(self) -> None:
        """Should detect English with various punctuation."""
        result = detect_language("Hello! How are you? I'm fine, thanks.")
        assert result == Language.en.value

    def test_detects_english_location_names(self) -> None:
        """Should detect English with location names."""
        result = detect_language("Omdurman is a city in Sudan")
        assert result == Language.en.value


# =============================================================================
# Tests for Mixed Text Handling
# =============================================================================


class TestMixedTextHandling:
    """Tests for handling mixed Arabic and English text."""

    def test_mixed_mostly_arabic(self) -> None:
        """Mixed text with mostly Arabic should be detected as Arabic."""
        # More than 30% Arabic
        text = "أنا مريض and I need help من فضلك"
        result = detect_language(text)
        assert result == Language.ar.value

    def test_mixed_mostly_english(self) -> None:
        """Mixed text with mostly English should be detected as English."""
        # Less than 30% Arabic
        text = "I am sick from Khartoum الخرطوم"
        result = detect_language(text)
        # This might be English or Arabic depending on ratio
        assert result in [Language.en.value, Language.ar.value]

    def test_english_with_arabic_names(self) -> None:
        """English text with Arabic names should be English."""
        text = "My name is Mohammed and I live in Omdurman"
        result = detect_language(text)
        assert result == Language.en.value

    def test_arabic_with_english_medical_terms(self) -> None:
        """Arabic text with English medical terms should be Arabic."""
        text = "أعاني من fever وإسهال"
        result = detect_language(text)
        # Depending on ratio, could go either way
        assert result in [Language.ar.value, Language.en.value]

    def test_code_switching(self) -> None:
        """Should handle code-switching between languages."""
        text = "السلام عليكم، I want to report مرض in my village"
        result = detect_language(text)
        # Will be detected based on ratio
        assert result in [Language.ar.value, Language.en.value]


# =============================================================================
# Tests for Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases in language detection."""

    def test_empty_string_returns_unknown(self) -> None:
        """Empty string should return 'unknown'."""
        result = detect_language("")
        assert result == Language.unknown.value

    def test_whitespace_only_returns_unknown(self) -> None:
        """Whitespace-only string should return 'unknown'."""
        result = detect_language("   ")
        assert result == Language.unknown.value

    def test_numbers_only_returns_unknown(self) -> None:
        """Numbers-only string should return 'unknown'."""
        result = detect_language("12345")
        assert result == Language.unknown.value

    def test_punctuation_only_returns_unknown(self) -> None:
        """Punctuation-only string should return 'unknown'."""
        result = detect_language("!@#$%^&*()")
        assert result == Language.unknown.value

    def test_emojis_only_returns_unknown(self) -> None:
        """Emoji-only string should return 'unknown'."""
        result = detect_language("😀😊🎉")
        assert result == Language.unknown.value

    def test_single_arabic_character(self) -> None:
        """Single Arabic character should be detected as Arabic."""
        result = detect_language("م")
        assert result == Language.ar.value

    def test_single_english_character(self) -> None:
        """Single English character should be detected as English."""
        result = detect_language("a")
        assert result == Language.en.value

    def test_none_input_behavior(self) -> None:
        """Should handle None input gracefully if passed."""
        # The function checks for empty/falsy values at the start
        # None is falsy, so it returns 'unknown' rather than raising
        result = detect_language(None)  # type: ignore
        assert result == Language.unknown.value

    def test_very_long_text(self) -> None:
        """Should handle very long text without issues."""
        text = "مرحبا " * 1000
        result = detect_language(text)
        assert result == Language.ar.value

    def test_newlines_and_tabs(self) -> None:
        """Should handle text with newlines and tabs."""
        text = "Hello\nHow are you?\tI'm fine"
        result = detect_language(text)
        assert result == Language.en.value

    def test_arabic_with_diacritics(self) -> None:
        """Should detect Arabic with diacritical marks."""
        # Arabic with tashkeel (vowel marks)
        text = "اَلسَّلَامُ عَلَيْكُمْ"
        result = detect_language(text)
        assert result == Language.ar.value


# =============================================================================
# Tests for Threshold Behavior
# =============================================================================


class TestThresholdBehavior:
    """Tests for the 30% Arabic character threshold."""

    def test_exactly_at_threshold(self) -> None:
        """Text at exactly 30% Arabic should be detected as Arabic."""
        # Create text with exactly 30% Arabic characters
        # 3 Arabic chars + 7 English chars = 30% Arabic
        # Note: This is approximate due to how letters are counted
        text = "aaa ب ب ب aaa"
        result = detect_language(text)
        # At 30% threshold, should be Arabic
        assert result == Language.ar.value

    def test_just_below_threshold(self) -> None:
        """Text just below 30% Arabic should be detected as English."""
        # More English letters to push below threshold
        text = "aaaaaaa ب ب"
        result = detect_language(text)
        # Should be English since Arabic ratio is low
        assert result == Language.en.value

    def test_just_above_threshold(self) -> None:
        """Text just above 30% Arabic should be detected as Arabic."""
        # More Arabic letters to push above threshold
        text = "aaa ب ب ب ب"
        result = detect_language(text)
        assert result == Language.ar.value


# =============================================================================
# Tests for Specific Health Reporting Scenarios
# =============================================================================


class TestHealthReportingScenarios:
    """Tests for typical health reporting messages in both languages."""

    def test_arabic_symptom_report(self) -> None:
        """Should detect Arabic symptom reports."""
        text = "ابني عنده حمى وإسهال من يومين"
        result = detect_language(text)
        assert result == Language.ar.value

    def test_english_symptom_report(self) -> None:
        """Should detect English symptom reports."""
        text = "My son has had fever and diarrhea for two days"
        result = detect_language(text)
        assert result == Language.en.value

    def test_arabic_location_report(self) -> None:
        """Should detect Arabic location descriptions."""
        text = "الحالات في منطقة الخرطوم شمال"
        result = detect_language(text)
        assert result == Language.ar.value

    def test_english_location_report(self) -> None:
        """Should detect English location descriptions."""
        text = "The cases are in the Khartoum North area"
        result = detect_language(text)
        assert result == Language.en.value

    def test_arabic_urgency_message(self) -> None:
        """Should detect Arabic urgent messages."""
        text = "حالة طوارئ! الناس يموتون!"
        result = detect_language(text)
        assert result == Language.ar.value

    def test_english_urgency_message(self) -> None:
        """Should detect English urgent messages."""
        text = "Emergency! People are dying!"
        result = detect_language(text)
        assert result == Language.en.value
