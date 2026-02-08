"""
Integration tests for report creation from conversation state and notification generation.

Capstone tests that exercise the full report creation pipeline.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio(loop_scope="session")

from cbi.db.models import (
    DiseaseType,
    Notification,
    Officer,
    Report,
    Reporter,
    UrgencyLevel,
)
from cbi.db.queries import (
    create_notification,
    create_notifications_for_all_officers,
    create_report_from_state,
)
from cbi.services.auth import hash_password


# =============================================================================
# TestReportCreationFromState
# =============================================================================


class TestReportCreationFromState:
    """Tests for create_report_from_state()."""

    @pytest.mark.asyncio
    async def test_full_data(self, db_session: AsyncSession):
        """Complete state dict → report in DB with all MVS fields, reporter created."""
        state = {
            "conversation_id": "conv-full-data-001",
            "reporter_phone": "+249123456789",
            "platform": "telegram",
            "language": "ar",
            "extracted_data": {
                "symptoms": ["diarrhea", "vomiting", "dehydration"],
                "suspected_disease": "cholera",
                "location_text": "Khartoum, Bahri",
                "location_normalized": "Khartoum",
                "location_coords": [15.5007, 32.5599],
                "onset_text": "3 days ago",
                "onset_date": "2024-01-15",
                "cases_count": 5,
                "deaths_count": 1,
                "affected_description": "Children under 5",
                "reporter_relationship": "neighbor",
            },
            "classification": {
                "suspected_disease": "cholera",
                "urgency": "critical",
                "alert_type": "suspected_outbreak",
                "data_completeness": 0.9,
                "confidence": 0.85,
            },
            "messages": [
                {"role": "user", "content": "There is cholera in our area"},
                {"role": "assistant", "content": "I understand. Can you tell me more?"},
            ],
        }

        report_id = await create_report_from_state(db_session, state)
        await db_session.commit()

        # Verify report
        result = await db_session.execute(select(Report).where(Report.id == report_id))
        report = result.scalar_one()

        assert report.conversation_id == "conv-full-data-001"
        assert report.suspected_disease == DiseaseType.cholera
        assert report.urgency == UrgencyLevel.critical
        assert report.cases_count == 5
        assert report.deaths_count == 1
        assert report.data_completeness == 0.9
        assert report.confidence_score == 0.85
        assert "diarrhea" in report.symptoms
        assert report.location_normalized == "Khartoum"
        assert report.reporter_id is not None

        # Verify reporter was created
        result = await db_session.execute(
            select(Reporter).where(Reporter.id == report.reporter_id)
        )
        reporter = result.scalar_one()
        assert reporter.preferred_language == "ar"
        assert reporter.total_reports >= 1

    @pytest.mark.asyncio
    async def test_minimal_data(self, db_session: AsyncSession):
        """Partial state → report created with defaults, no reporter (empty phone)."""
        state = {
            "conversation_id": "conv-minimal-001",
            "reporter_phone": "",
            "platform": "telegram",
            "language": "en",
            "extracted_data": {
                "symptoms": ["fever"],
            },
            "classification": {},
            "messages": [],
        }

        report_id = await create_report_from_state(db_session, state)
        await db_session.commit()

        result = await db_session.execute(select(Report).where(Report.id == report_id))
        report = result.scalar_one()

        assert report.reporter_id is None
        assert report.suspected_disease == DiseaseType.unknown
        assert report.urgency == UrgencyLevel.medium
        assert "fever" in report.symptoms

    @pytest.mark.asyncio
    async def test_report_with_geospatial_point(self, db_session: AsyncSession):
        """WKT location_point stored correctly."""
        state = {
            "conversation_id": "conv-geo-001",
            "reporter_phone": "",
            "platform": "telegram",
            "language": "ar",
            "extracted_data": {
                "symptoms": ["cough"],
                "location_coords": [15.5007, 32.5599],
            },
            "classification": {},
            "messages": [],
        }

        report_id = await create_report_from_state(db_session, state)
        await db_session.commit()

        # Verify the point was stored using raw SQL
        result = await db_session.execute(
            text(
                "SELECT ST_X(location_point::geometry), ST_Y(location_point::geometry) "
                "FROM reports WHERE id = :id"
            ),
            {"id": report_id},
        )
        row = result.one()
        lon, lat = row
        assert abs(lat - 15.5007) < 0.001
        assert abs(lon - 32.5599) < 0.001


# =============================================================================
# TestNotificationGeneration
# =============================================================================


class TestNotificationGeneration:
    """Tests for notification creation."""

    @pytest_asyncio.fixture(loop_scope="session")
    async def officers(self, db_session: AsyncSession) -> list[Officer]:
        """Seed 3 officers: 2 active, 1 inactive."""
        active1 = Officer(
            id=uuid.uuid4(),
            email="officer1@cbi.example.com",
            password_hash=hash_password("password123"),
            name="Officer One",
            role="officer",
            is_active=True,
            region="Khartoum",
        )
        active2 = Officer(
            id=uuid.uuid4(),
            email="officer2@cbi.example.com",
            password_hash=hash_password("password123"),
            name="Officer Two",
            role="officer",
            is_active=True,
            region="Kassala",
        )
        inactive = Officer(
            id=uuid.uuid4(),
            email="inactive@cbi.example.com",
            password_hash=hash_password("password123"),
            name="Inactive Officer",
            role="officer",
            is_active=False,
            region="Khartoum",
        )
        db_session.add_all([active1, active2, inactive])
        await db_session.commit()
        return [active1, active2, inactive]

    @pytest.mark.asyncio
    async def test_create_notification_for_single_officer(
        self, db_session: AsyncSession, officers: list[Officer]
    ):
        """Notification linked to report + officer."""
        # Create a report first
        from cbi.db.queries import create_report

        report = await create_report(
            db_session,
            conversation_id="conv-notif-001",
            suspected_disease=DiseaseType.cholera,
            urgency=UrgencyLevel.critical,
        )
        await db_session.flush()

        notif_id = await create_notification(
            db_session,
            report_id=report.id,
            officer_id=officers[0].id,
            urgency=UrgencyLevel.critical,
            title="Suspected cholera outbreak",
            body="5 cases reported in Khartoum",
        )
        await db_session.commit()

        result = await db_session.execute(
            select(Notification).where(Notification.id == notif_id)
        )
        notif = result.scalar_one()
        assert notif.report_id == report.id
        assert notif.officer_id == officers[0].id
        assert notif.title == "Suspected cholera outbreak"

    @pytest.mark.asyncio
    async def test_broadcast_to_all_officers(
        self, db_session: AsyncSession, officers: list[Officer]
    ):
        """create_notifications_for_all_officers creates one per active officer."""
        notif_ids = await create_notifications_for_all_officers(
            db_session,
            urgency=UrgencyLevel.high,
            title="New outbreak alert",
            body="Multiple cases in Kassala",
        )
        await db_session.commit()

        # 2 active officers
        assert len(notif_ids) == 2

        # Verify each notification exists
        for nid in notif_ids:
            result = await db_session.execute(
                select(Notification).where(Notification.id == nid)
            )
            notif = result.scalar_one()
            assert notif.title == "New outbreak alert"

    @pytest.mark.asyncio
    async def test_inactive_officer_excluded(
        self, db_session: AsyncSession, officers: list[Officer]
    ):
        """Inactive officers don't receive notifications."""
        notif_ids = await create_notifications_for_all_officers(
            db_session,
            urgency=UrgencyLevel.medium,
            title="Routine alert",
            body="Test body",
        )
        await db_session.commit()

        # Check that the inactive officer (index 2) didn't get a notification
        result = await db_session.execute(
            select(Notification).where(Notification.officer_id == officers[2].id)
        )
        notifs = list(result.scalars().all())
        assert len(notifs) == 0
