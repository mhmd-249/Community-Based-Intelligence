"""
Pytest configuration and shared fixtures for unit tests.
"""

import pytest


# =============================================================================
# Common Test Data
# =============================================================================


@pytest.fixture
def sudanese_phone_numbers() -> list[str]:
    """List of Sudanese phone number formats."""
    return [
        "+249123456789",
        "+249912345678",
        "00249123456789",
        "0123456789",
        "249123456789",
    ]


@pytest.fixture
def arabic_health_texts() -> list[str]:
    """Arabic health-related texts for testing."""
    return [
        "أعاني من حمى منذ ثلاثة أيام",
        "هناك أطفال مرضى في قريتي",
        "الكثير من الناس يعانون من الإسهال",
        "مات ثلاثة أشخاص هذا الأسبوع",
        "نحتاج مساعدة طبية عاجلة",
    ]


@pytest.fixture
def english_health_texts() -> list[str]:
    """English health-related texts for testing."""
    return [
        "I have had fever for three days",
        "There are sick children in my village",
        "Many people are suffering from diarrhea",
        "Three people died this week",
        "We need urgent medical help",
    ]


@pytest.fixture
def mvs_symptoms() -> list[str]:
    """Common symptoms used in MVS data."""
    return [
        "fever",
        "diarrhea",
        "vomiting",
        "headache",
        "rash",
        "cough",
        "dehydration",
    ]


@pytest.fixture
def sudan_locations() -> list[str]:
    """Sudan location names."""
    return [
        "Khartoum",
        "Omdurman",
        "Bahri",
        "Port Sudan",
        "Kassala",
        "Gezira",
        "North Darfur",
        "South Darfur",
    ]
