"""
Integration tests for database queries, especially PostGIS spatial queries.

Tests run against real PostgreSQL+PostGIS (cbi_test database).
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio(loop_scope="session")

from cbi.db.models import (
    AlertType,
    DiseaseType,
    LinkType,
    Officer,
    Report,
    ReportStatus,
    UrgencyLevel,
)
from cbi.db.queries import (
    count_reports_by_disease,
    create_report,
    find_related_cases,
    get_case_count_for_area,
    get_linked_reports,
    get_or_create_reporter,
    get_report_stats,
    get_reports_near_location,
    link_reports,
    list_reports_paginated,
)


# =============================================================================
# Helpers
# =============================================================================


async def _create_geo_report(
    session: AsyncSession,
    *,
    lat: float,
    lon: float,
    disease: DiseaseType = DiseaseType.cholera,
    symptoms: list[str] | None = None,
    conv_id: str | None = None,
) -> Report:
    """Create a report with a geographic point."""
    return await create_report(
        session,
        conversation_id=conv_id or f"conv-geo-{uuid.uuid4().hex[:8]}",
        symptoms=symptoms or ["diarrhea", "vomiting"],
        suspected_disease=disease,
        location_text=f"Near ({lat}, {lon})",
        location_normalized="TestArea",
        location_point_wkt=f"SRID=4326;POINT({lon} {lat})",
        cases_count=1,
        urgency=UrgencyLevel.high,
        source="telegram",
    )


# =============================================================================
# TestGeospatialQueries
# =============================================================================


class TestGeospatialQueries:
    """Tests for PostGIS spatial queries."""

    @pytest_asyncio.fixture(loop_scope="session")
    async def geo_reports(self, db_session: AsyncSession) -> list[Report]:
        """
        Seed 5 reports at known locations:
        - 3 in Khartoum cluster (within ~5km)
        - 1 in Port Sudan (~600km away)
        - 1 in Kassala (~400km away)
        """
        reports = []

        # Khartoum cluster
        reports.append(await _create_geo_report(
            db_session, lat=15.5007, lon=32.5599,
            disease=DiseaseType.cholera,
            symptoms=["diarrhea", "vomiting"],
        ))
        reports.append(await _create_geo_report(
            db_session, lat=15.5050, lon=32.5630,
            disease=DiseaseType.cholera,
            symptoms=["diarrhea", "dehydration"],
        ))
        reports.append(await _create_geo_report(
            db_session, lat=15.5100, lon=32.5550,
            disease=DiseaseType.cholera,
            symptoms=["vomiting", "fever"],
        ))

        # Port Sudan (far away)
        reports.append(await _create_geo_report(
            db_session, lat=19.6158, lon=37.2164,
            disease=DiseaseType.dengue,
            symptoms=["fever", "rash"],
        ))

        # Kassala (medium distance)
        reports.append(await _create_geo_report(
            db_session, lat=15.4538, lon=36.3937,
            disease=DiseaseType.malaria,
            symptoms=["fever", "chills"],
        ))

        await db_session.commit()
        return reports

    @pytest.mark.asyncio
    async def test_find_related_by_geography(
        self, db_session: AsyncSession, geo_reports: list[Report]
    ):
        """10km radius from Khartoum center finds nearby, excludes Port Sudan/Kassala."""
        results = await find_related_cases(
            db_session,
            location_coords=(15.5007, 32.5599),
            radius_km=10.0,
            exclude_report_id=geo_reports[0].id,
        )
        result_ids = {r["id"] for r in results}

        # Should find the other 2 Khartoum reports
        assert geo_reports[1].id in result_ids
        assert geo_reports[2].id in result_ids
        # Should NOT find Port Sudan or Kassala
        assert geo_reports[3].id not in result_ids
        assert geo_reports[4].id not in result_ids

    @pytest.mark.asyncio
    async def test_find_related_by_disease(
        self, db_session: AsyncSession, geo_reports: list[Report]
    ):
        """Filter by dengue returns only Port Sudan report."""
        results = await find_related_cases(
            db_session,
            suspected_disease=DiseaseType.dengue,
        )
        assert len(results) == 1
        assert results[0]["suspected_disease"] == "dengue"

    @pytest.mark.asyncio
    async def test_symptom_overlap_score(
        self, db_session: AsyncSession, geo_reports: list[Report]
    ):
        """Jaccard overlap: {diarrhea, vomiting} & {diarrhea, dehydration} = 1/3 ≈ 0.33."""
        results = await find_related_cases(
            db_session,
            symptoms=["diarrhea", "vomiting"],
            location_coords=(15.5007, 32.5599),
            radius_km=10.0,
            exclude_report_id=geo_reports[0].id,
        )

        # Find the report with diarrhea+dehydration (geo_reports[1])
        for r in results:
            if r["id"] == geo_reports[1].id:
                # Union: {diarrhea, vomiting, dehydration} = 3
                # Intersection: {diarrhea} = 1
                # Score: 1/3 ≈ 0.33
                assert r["symptom_overlap_score"] == pytest.approx(0.33, abs=0.01)
                break
        else:
            pytest.fail("Expected report not found in results")

    @pytest.mark.asyncio
    async def test_case_count_with_coords(
        self, db_session: AsyncSession, geo_reports: list[Report]
    ):
        """get_case_count_for_area with lat/lon returns correct count near Khartoum."""
        count = await get_case_count_for_area(
            db_session,
            disease=DiseaseType.cholera,
            location_lat=15.5007,
            location_lon=32.5599,
            radius_km=10.0,
        )
        assert count == 3  # 3 cholera reports in Khartoum

    @pytest.mark.asyncio
    async def test_case_count_text_fallback(
        self, db_session: AsyncSession, geo_reports: list[Report]
    ):
        """get_case_count_for_area with text location falls back to ILIKE."""
        count = await get_case_count_for_area(
            db_session,
            disease=DiseaseType.cholera,
            location_text="TestArea",
        )
        assert count == 3

    @pytest.mark.asyncio
    async def test_reports_near_location(
        self, db_session: AsyncSession, geo_reports: list[Report]
    ):
        """get_reports_near_location returns spatially nearby reports."""
        results = await get_reports_near_location(
            db_session,
            latitude=15.5007,
            longitude=32.5599,
            radius_km=10.0,
        )
        assert len(results) == 3


# =============================================================================
# TestReportLinking
# =============================================================================


class TestReportLinking:
    """Tests for report linking/clustering."""

    @pytest_asyncio.fixture(loop_scope="session")
    async def two_reports(self, db_session: AsyncSession) -> tuple[Report, Report]:
        """Create two reports for linking tests."""
        r1 = await create_report(
            db_session,
            conversation_id=f"conv-link-{uuid.uuid4().hex[:8]}",
            symptoms=["fever"],
            suspected_disease=DiseaseType.cholera,
            urgency=UrgencyLevel.high,
        )
        r2 = await create_report(
            db_session,
            conversation_id=f"conv-link-{uuid.uuid4().hex[:8]}",
            symptoms=["fever", "vomiting"],
            suspected_disease=DiseaseType.cholera,
            urgency=UrgencyLevel.medium,
        )
        await db_session.commit()
        return r1, r2

    @pytest.mark.asyncio
    async def test_link_two_reports(
        self, db_session: AsyncSession, two_reports: tuple[Report, Report]
    ):
        """Create link and retrieve via get_linked_reports."""
        r1, r2 = two_reports
        link = await link_reports(
            db_session,
            r1.id,
            r2.id,
            LinkType.geographic,
            confidence=0.9,
        )
        await db_session.commit()

        assert link is not None
        assert link.confidence == 0.9

        linked = await get_linked_reports(db_session, r1.id)
        assert len(linked) == 1
        assert linked[0]["id"] == r2.id
        assert linked[0]["link_type"] == "geographic"

    @pytest.mark.asyncio
    async def test_link_same_report_returns_none(
        self, db_session: AsyncSession, two_reports: tuple[Report, Report]
    ):
        """Self-link returns None."""
        r1, _ = two_reports
        result = await link_reports(
            db_session, r1.id, r1.id, LinkType.temporal, confidence=0.5
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_duplicate_link_returns_none(
        self, db_session: AsyncSession, two_reports: tuple[Report, Report]
    ):
        """Same pair + type returns None on duplicate."""
        r1, r2 = two_reports
        link1 = await link_reports(
            db_session, r1.id, r2.id, LinkType.geographic, confidence=0.9
        )
        await db_session.commit()
        assert link1 is not None

        link2 = await link_reports(
            db_session, r1.id, r2.id, LinkType.geographic, confidence=0.8
        )
        assert link2 is None


# =============================================================================
# TestStatisticsQueries
# =============================================================================


class TestStatisticsQueries:
    """Tests for statistics and aggregate queries."""

    @pytest.mark.asyncio
    async def test_count_by_disease(self, db_session: AsyncSession):
        """4 cholera reports → count=4."""
        for i in range(4):
            await create_report(
                db_session,
                conversation_id=f"conv-count-{i}",
                suspected_disease=DiseaseType.cholera,
            )
        await db_session.commit()

        count = await count_reports_by_disease(db_session, DiseaseType.cholera)
        assert count == 4

    @pytest.mark.asyncio
    async def test_report_stats(self, db_session: AsyncSession):
        """Mixed reports produce correct stats."""
        # 2 open + critical
        for i in range(2):
            await create_report(
                db_session,
                conversation_id=f"conv-stat-crit-{i}",
                urgency=UrgencyLevel.critical,
            )
        # 1 open + medium
        await create_report(
            db_session,
            conversation_id="conv-stat-med",
            urgency=UrgencyLevel.medium,
        )
        await db_session.commit()

        stats = await get_report_stats(db_session)
        assert stats["total"] == 3
        assert stats["open"] == 3
        assert stats["critical"] == 2

    @pytest.mark.asyncio
    async def test_get_or_create_reporter(self, db_session: AsyncSession):
        """First call creates, second returns existing."""
        phone_hash = "abc123hash"
        phone_enc = b"encrypted_phone"

        reporter1, created1 = await get_or_create_reporter(
            db_session, phone_hash, phone_enc, "ar"
        )
        await db_session.commit()
        assert created1 is True

        reporter2, created2 = await get_or_create_reporter(
            db_session, phone_hash, phone_enc, "ar"
        )
        assert created2 is False
        assert reporter2.id == reporter1.id

    @pytest.mark.asyncio
    async def test_list_reports_paginated(self, db_session: AsyncSession):
        """Pagination with filters works correctly."""
        for i in range(5):
            disease = DiseaseType.cholera if i < 3 else DiseaseType.dengue
            await create_report(
                db_session,
                conversation_id=f"conv-page-{i}",
                suspected_disease=disease,
            )
        await db_session.commit()

        reports, total = await list_reports_paginated(
            db_session,
            disease=DiseaseType.cholera,
            page=1,
            page_size=2,
        )
        assert total == 3
        assert len(reports) == 2

        reports2, total2 = await list_reports_paginated(
            db_session,
            disease=DiseaseType.cholera,
            page=2,
            page_size=2,
        )
        assert total2 == 3
        assert len(reports2) == 1

    @pytest.mark.asyncio
    async def test_list_reports_paginated_no_filter(self, db_session: AsyncSession):
        """List all reports without filter."""
        for i in range(3):
            await create_report(
                db_session,
                conversation_id=f"conv-all-{i}",
            )
        await db_session.commit()

        reports, total = await list_reports_paginated(db_session, page=1, page_size=10)
        assert total == 3
        assert len(reports) == 3
