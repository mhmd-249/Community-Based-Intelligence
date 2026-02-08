"""
Integration test fixtures for CBI.

Requires Docker Compose services running (db on port 5432, redis on port 6379).
Creates a separate cbi_test database to avoid corrupting dev data.

All async fixtures and tests use loop_scope="session" to share a single event
loop across the session. This avoids "attached to a different loop" errors.
"""

import os

# ── Set env vars BEFORE any cbi.* import (handles @lru_cache on get_settings) ─
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cbi:cbi_password@localhost:5432/cbi_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
os.environ.setdefault("JWT_SECRET", "integration-test-jwt-secret-must-be-32chars!!")
os.environ.setdefault("ENCRYPTION_KEY", "01234567890123456789012345678901")
os.environ.setdefault("PHONE_HASH_SALT", "test-salt-for-integration-tests")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "0000000000")
os.environ.setdefault("WHATSAPP_ACCESS_TOKEN", "fake-whatsapp-token")
os.environ.setdefault("ENVIRONMENT", "development")

# Clear lru_cache so settings picks up test env vars
from cbi.config.settings import get_settings
get_settings.cache_clear()

import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cbi.db.models import (
    AlertType,
    DiseaseType,
    Officer,
    Report,
    ReportStatus,
    UrgencyLevel,
)
from cbi.services.auth import create_access_token, hash_password

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATION_SQL = PROJECT_ROOT / "migrations" / "001_initial_schema.sql"

# ── URLs ──────────────────────────────────────────────────────────────────────
ADMIN_DB_URL = "postgresql+asyncpg://cbi:cbi_password@localhost:5432/postgres"
TEST_DB_URL = "postgresql+asyncpg://cbi:cbi_password@localhost:5432/cbi_test"
TEST_REDIS_URL = "redis://localhost:6379/1"

TABLES_TO_TRUNCATE = [
    "audit_logs",
    "conversation_states",
    "notifications",
    "report_links",
    "reports",
    "officers",
    "reporters",
]


# ── Session-scoped DB lifecycle ──────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine() -> AsyncEngine:
    """Create cbi_test DB, run migrations, yield engine, drop DB after."""
    # Create the test database
    admin_engine = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text("DROP DATABASE IF EXISTS cbi_test"))
        await conn.execute(text("CREATE DATABASE cbi_test"))
    await admin_engine.dispose()

    # Run migration SQL
    migration_engine = create_async_engine(TEST_DB_URL)
    migration_sql = MIGRATION_SQL.read_text()
    async with migration_engine.begin() as conn:
        for stmt in _split_sql_statements(migration_sql):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt))
        # Columns added after initial migration
        for extra in [
            "ALTER TABLE reports ADD COLUMN IF NOT EXISTS investigation_notes JSONB DEFAULT '[]'::jsonb",
            "ALTER TABLE reports ADD COLUMN IF NOT EXISTS outcome TEXT",
        ]:
            await conn.execute(text(extra))
    await migration_engine.dispose()

    # Create the real test engine
    engine = create_async_engine(
        TEST_DB_URL, pool_size=5, max_overflow=5, pool_pre_ping=True
    )

    yield engine

    # Cleanup
    await engine.dispose()
    admin_engine = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = 'cbi_test' AND pid <> pg_backend_pid()"
        ))
        await conn.execute(text("DROP DATABASE IF EXISTS cbi_test"))
    await admin_engine.dispose()


# ── Per-test fixtures ────────────────────────────────────────────────────────

@pytest_asyncio.fixture(loop_scope="session")
async def db_session(test_engine: AsyncEngine) -> AsyncSession:
    """Function-scoped session. Truncates all tables BEFORE each test."""
    # Truncate before yielding for a clean slate
    async with test_engine.begin() as conn:
        for table in TABLES_TO_TRUNCATE:
            await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))

    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    session = factory()
    yield session
    await session.close()


@pytest_asyncio.fixture(loop_scope="session")
async def test_redis():
    """Redis client on DB 1; FLUSHDB after each test."""
    client = aioredis.from_url(
        TEST_REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    yield client
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture(loop_scope="session")
async def app_client(test_engine: AsyncEngine, test_redis, db_session):
    """httpx AsyncClient with ASGITransport, patched to use test DB and Redis."""
    import cbi.db.session as db_session_mod
    from cbi.services.messaging.factory import _gateway_cache

    test_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    original_engine = db_session_mod._engine
    original_factory = db_session_mod._async_session_factory

    db_session_mod._engine = test_engine
    db_session_mod._async_session_factory = test_factory

    from cbi.api.main import app

    app.state.redis = test_redis
    _gateway_cache.clear()

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client

    db_session_mod._engine = original_engine
    db_session_mod._async_session_factory = original_factory


@pytest_asyncio.fixture(loop_scope="session")
async def test_officer(db_session: AsyncSession) -> Officer:
    """Seed an admin officer for auth tests."""
    officer = Officer(
        id=uuid.uuid4(),
        email="test.officer@cbi.example.com",
        password_hash=hash_password("testpassword123"),
        name="Test Officer",
        region="Khartoum",
        role="admin",
        is_active=True,
    )
    db_session.add(officer)
    await db_session.commit()
    return officer


@pytest.fixture
def test_officer_token(test_officer: Officer) -> str:
    """JWT access token for the test officer."""
    return create_access_token(test_officer.id, test_officer.role)


@pytest.fixture
def auth_headers(test_officer_token: str) -> dict[str, str]:
    """Authorization headers dict."""
    return {"Authorization": f"Bearer {test_officer_token}"}


@pytest_asyncio.fixture(loop_scope="session")
async def test_report(db_session: AsyncSession, test_officer: Officer) -> Report:
    """Seed a known cholera report."""
    report = Report(
        id=uuid.uuid4(),
        conversation_id="conv-test-001",
        status=ReportStatus.open,
        symptoms=["diarrhea", "vomiting", "dehydration"],
        suspected_disease=DiseaseType.cholera,
        location_text="Khartoum, Bahri district",
        location_normalized="Khartoum",
        onset_text="3 days ago",
        cases_count=5,
        deaths_count=0,
        urgency=UrgencyLevel.critical,
        alert_type=AlertType.suspected_outbreak,
        data_completeness=0.85,
        source="telegram",
        raw_conversation=[{"role": "user", "content": "test"}],
        extracted_entities={"symptoms": ["diarrhea"]},
        investigation_notes=[],
    )
    db_session.add(report)
    await db_session.commit()
    return report


@pytest_asyncio.fixture(loop_scope="session")
async def seed_multiple_reports(db_session: AsyncSession):
    """Factory fixture to seed N reports with configurable attributes."""

    async def _seed(
        count: int = 3,
        disease: DiseaseType = DiseaseType.cholera,
        urgency: UrgencyLevel = UrgencyLevel.medium,
        status: ReportStatus = ReportStatus.open,
    ) -> list[Report]:
        reports = []
        for i in range(count):
            report = Report(
                id=uuid.uuid4(),
                conversation_id=f"conv-seed-{uuid.uuid4().hex[:8]}",
                status=status,
                symptoms=["fever", "headache"],
                suspected_disease=disease,
                location_text=f"Location {i}",
                location_normalized="Khartoum",
                cases_count=1,
                deaths_count=0,
                urgency=urgency,
                alert_type=AlertType.single_case,
                data_completeness=0.5,
                source="telegram",
                raw_conversation=[],
                extracted_entities={},
                investigation_notes=[],
            )
            db_session.add(report)
            reports.append(report)
        await db_session.commit()
        return reports

    return _seed


# ── Helpers ──────────────────────────────────────────────────────────────────

def _split_sql_statements(sql: str) -> list[str]:
    """Split SQL into individual statements, handling $$ function bodies."""
    statements: list[str] = []
    current: list[str] = []
    in_dollar_block = False

    for line in sql.split("\n"):
        stripped = line.strip()
        if stripped.startswith("--") and not in_dollar_block:
            continue

        dollar_count = line.count("$$")
        if dollar_count % 2 == 1:
            in_dollar_block = not in_dollar_block

        current.append(line)

        if stripped.endswith(";") and not in_dollar_block:
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []

    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)

    return statements
