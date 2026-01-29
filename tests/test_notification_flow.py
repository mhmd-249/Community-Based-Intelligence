"""
Test script for Phase 4.3: Notification Service - Full Database Flow.

Tests:
1. create_notification - creates notification with bilingual content
2. send_notification - loads from DB and dispatches to channels
3. get_unread_notifications - retrieves unread, ordered by urgency
4. mark_as_read - marks notification read + audit log

Requires: PostgreSQL (cbi-db) and Redis (cbi-redis) running via Docker.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from uuid import UUID

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../..")))

# Override env vars for localhost access (Docker ports mapped to host)
os.environ["DATABASE_URL"] = "postgresql+asyncpg://cbi:cbi_password@localhost:5432/cbi"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

# Ensure other required env vars exist
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-not-needed-for-this-test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("JWT_SECRET", "a" * 64)
os.environ.setdefault("ENCRYPTION_KEY", "b" * 64)
os.environ.setdefault("PHONE_HASH_SALT", "c" * 32)


# Clear cached settings so our overrides take effect
from cbi.config.settings import get_settings
get_settings.cache_clear()

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
INFO = "\033[94mINFO\033[0m"
WARN = "\033[93mWARN\033[0m"

results: list[tuple[str, bool, str]] = []


def log_result(name: str, passed: bool, detail: str = "") -> None:
    status = PASS if passed else FAIL
    results.append((name, passed, detail))
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")


async def setup_test_data() -> dict:
    """Create test officer and report in the database."""
    from sqlalchemy import text
    from cbi.db.session import get_session

    print(f"\n[{INFO}] Setting up test data...")

    async with get_session() as session:
        # Create a test officer with a region (will get Arabic notifications)
        officer_result = await session.execute(
            text("""
                INSERT INTO officers (id, email, password_hash, name, region, role, is_active)
                VALUES (
                    uuid_generate_v4(),
                    'test.officer.notif@cbi.local',
                    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYA/pWrWuqGi',
                    'Dr. Ahmed Hassan',
                    'Khartoum',
                    'officer',
                    TRUE
                )
                ON CONFLICT (email) DO UPDATE SET name = 'Dr. Ahmed Hassan'
                RETURNING id
            """)
        )
        officer_id = officer_result.scalar_one()
        print(f"  Officer ID: {officer_id}")

        # Create a second officer WITHOUT a region (will get English notifications)
        officer2_result = await session.execute(
            text("""
                INSERT INTO officers (id, email, password_hash, name, region, role, is_active)
                VALUES (
                    uuid_generate_v4(),
                    'test.officer2.notif@cbi.local',
                    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYA/pWrWuqGi',
                    'Dr. Sarah Wilson',
                    NULL,
                    'officer',
                    TRUE
                )
                ON CONFLICT (email) DO UPDATE SET name = 'Dr. Sarah Wilson'
                RETURNING id
            """)
        )
        officer2_id = officer2_result.scalar_one()
        print(f"  Officer 2 ID: {officer2_id}")

        # Create a test report (cholera case)
        report_result = await session.execute(
            text("""
                INSERT INTO reports (
                    id, conversation_id, status,
                    symptoms, suspected_disease, location_text,
                    cases_count, deaths_count, urgency, alert_type,
                    data_completeness, confidence_score, source
                )
                VALUES (
                    uuid_generate_v4(),
                    'test-conv-notif-001',
                    'open',
                    ARRAY['diarrhea', 'vomiting', 'dehydration'],
                    'cholera',
                    'Omdurman, Khartoum',
                    5, 1, 'critical', 'suspected_outbreak',
                    0.85, 0.92, 'telegram'
                )
                RETURNING id
            """)
        )
        report_id = report_result.scalar_one()
        print(f"  Report ID: {report_id}")

        # Create a second report (dengue, medium urgency)
        report2_result = await session.execute(
            text("""
                INSERT INTO reports (
                    id, conversation_id, status,
                    symptoms, suspected_disease, location_text,
                    cases_count, deaths_count, urgency, alert_type,
                    data_completeness, confidence_score, source
                )
                VALUES (
                    uuid_generate_v4(),
                    'test-conv-notif-002',
                    'open',
                    ARRAY['fever', 'headache', 'joint_pain'],
                    'dengue',
                    'Port Sudan',
                    2, 0, 'medium', 'single_case',
                    0.70, 0.75, 'telegram'
                )
                RETURNING id
            """)
        )
        report2_id = report2_result.scalar_one()
        print(f"  Report 2 ID: {report2_id}")

    return {
        "officer_id": officer_id,
        "officer2_id": officer2_id,
        "report_id": report_id,
        "report2_id": report2_id,
    }


async def test_create_notification(test_data: dict) -> dict:
    """Test 1: create_notification with bilingual content."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 1: create_notification")
    print(f"{'='*60}")

    from cbi.db.session import get_session
    from cbi.services.notifications import create_notification

    notification_ids = {}

    # Test 1a: Critical cholera notification for Arabic-speaking officer
    print(f"\n  [Test 1a] Critical cholera notification (Arabic officer)...")
    try:
        async with get_session() as session:
            classification_data = {
                "suspected_disease": "cholera",
                "confidence": 0.92,
                "urgency": "critical",
                "alert_type": "suspected_outbreak",
                "reasoning": "Multiple cholera cases with deaths reported",
                "recommended_actions": [
                    "Deploy rapid response team immediately",
                    "Set up oral rehydration stations",
                    "Initiate water source testing",
                ],
                "follow_up_questions": [],
            }

            notif_id = await create_notification(
                session,
                report_id=test_data["report_id"],
                officer_id=test_data["officer_id"],
                urgency="critical",
                classification=classification_data,
            )

            notification_ids["critical_ar"] = notif_id
            log_result(
                "Create critical notification (Arabic)",
                notif_id is not None,
                f"ID: {notif_id}",
            )

            # Verify the notification was persisted
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT id, title, body, urgency, channels, metadata FROM notifications WHERE id = :id"),
                {"id": notif_id},
            )
            row = result.mappings().one()

            # Check title is in Arabic (officer has region set)
            has_arabic_title = "تنبيه صحي" in row["title"]
            log_result(
                "Title is in Arabic (officer has region)",
                has_arabic_title,
                f"Title: {row['title'][:60]}...",
            )

            # Check channels for critical urgency
            channels = row["channels"]
            expected_channels = ["dashboard", "whatsapp", "email"]
            channels_match = set(channels) == set(expected_channels)
            log_result(
                "Critical channels: dashboard+whatsapp+email",
                channels_match,
                f"Channels: {channels}",
            )

            # Check metadata has bilingual content
            metadata = row["metadata"]
            has_bilingual = "title_en" in metadata and "title_ar" in metadata
            log_result(
                "Metadata has bilingual content",
                has_bilingual,
                f"EN title: {metadata.get('title_en', 'MISSING')[:50]}",
            )

            # Check body contains key information
            body = row["body"]
            has_disease_info = "الكوليرا" in body or "cholera" in body.lower()
            log_result(
                "Body contains disease information",
                has_disease_info,
                f"Body preview: {body[:80]}...",
            )

    except Exception as e:
        log_result("Create critical notification (Arabic)", False, f"Error: {e}")

    # Test 1b: Medium dengue notification for English-speaking officer
    print(f"\n  [Test 1b] Medium dengue notification (English officer)...")
    try:
        async with get_session() as session:
            classification_data = {
                "suspected_disease": "dengue",
                "confidence": 0.75,
                "urgency": "medium",
                "alert_type": "single_case",
                "reasoning": "Suspected dengue case",
                "recommended_actions": [],
                "follow_up_questions": [],
            }

            notif_id = await create_notification(
                session,
                report_id=test_data["report2_id"],
                officer_id=test_data["officer2_id"],
                urgency="medium",
                classification=classification_data,
            )

            notification_ids["medium_en"] = notif_id
            log_result(
                "Create medium notification (English)",
                notif_id is not None,
                f"ID: {notif_id}",
            )

            # Verify English title (officer has no region)
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT title, channels FROM notifications WHERE id = :id"),
                {"id": notif_id},
            )
            row = result.mappings().one()

            has_english_title = "Health Alert" in row["title"]
            log_result(
                "Title is in English (no region)",
                has_english_title,
                f"Title: {row['title']}",
            )

            # Medium urgency should only have dashboard channel
            channels = row["channels"]
            channels_correct = channels == ["dashboard"]
            log_result(
                "Medium channels: dashboard only",
                channels_correct,
                f"Channels: {channels}",
            )

    except Exception as e:
        log_result("Create medium notification (English)", False, f"Error: {e}")

    # Test 1c: Notification with Classification Pydantic model
    print(f"\n  [Test 1c] Notification with Classification model...")
    try:
        from cbi.agents.state import Classification

        async with get_session() as session:
            classification_model = Classification(
                suspected_disease="malaria",
                confidence=0.60,
                urgency="high",
                alert_type="cluster",
                reasoning="Multiple malaria cases in same area",
                recommended_actions=["Distribute bed nets", "Indoor spraying"],
            )

            notif_id = await create_notification(
                session,
                report_id=test_data["report_id"],
                officer_id=test_data["officer_id"],
                urgency="high",
                classification=classification_model,
            )

            notification_ids["high_model"] = notif_id
            log_result(
                "Create notification with Pydantic model",
                notif_id is not None,
                f"ID: {notif_id}",
            )

            # High urgency should have dashboard+email
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT channels FROM notifications WHERE id = :id"),
                {"id": notif_id},
            )
            row = result.mappings().one()
            channels = row["channels"]
            expected = ["dashboard", "email"]
            log_result(
                "High channels: dashboard+email",
                set(channels) == set(expected),
                f"Channels: {channels}",
            )

    except Exception as e:
        log_result("Create notification with Pydantic model", False, f"Error: {e}")

    return notification_ids


async def test_send_notification(notification_ids: dict) -> None:
    """Test 2: send_notification with Redis pub/sub verification."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 2: send_notification")
    print(f"{'='*60}")

    import redis.asyncio as aioredis
    from cbi.services.notifications import send_notification, DASHBOARD_CHANNEL

    # Set up a Redis subscriber to capture published messages
    redis_client = aioredis.from_url(
        "redis://localhost:6379/0",
        encoding="utf-8",
        decode_responses=True,
    )
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(DASHBOARD_CHANNEL)

    # Consume the subscription confirmation message
    msg = await pubsub.get_message(timeout=2.0)

    # Test 2a: Send critical notification (should publish to dashboard)
    print(f"\n  [Test 2a] Send critical notification...")
    try:
        critical_id = notification_ids.get("critical_ar")
        if critical_id:
            await send_notification(critical_id)

            # Check if message was published to Redis
            msg = await pubsub.get_message(timeout=3.0)
            if msg and msg["type"] == "message":
                data = json.loads(msg["data"])
                has_id = data.get("id") == str(critical_id)
                has_urgency = data.get("urgency") == "critical"
                has_bilingual = "title_en" in data and "title_ar" in data

                log_result(
                    "Dashboard pub/sub received message",
                    has_id,
                    f"Notification ID matches: {has_id}",
                )
                log_result(
                    "Published data has urgency",
                    has_urgency,
                    f"Urgency: {data.get('urgency')}",
                )
                log_result(
                    "Published data has bilingual content",
                    has_bilingual,
                    f"EN: {data.get('title_en', '')[:40]}... | AR: {data.get('title_ar', '')[:40]}...",
                )
            else:
                log_result("Dashboard pub/sub received message", False, f"No message received: {msg}")
        else:
            log_result("Send critical notification", False, "No critical notification ID")

    except Exception as e:
        log_result("Send critical notification", False, f"Error: {e}")

    # Test 2b: Send medium notification (dashboard only)
    print(f"\n  [Test 2b] Send medium notification...")
    try:
        medium_id = notification_ids.get("medium_en")
        if medium_id:
            await send_notification(medium_id)

            msg = await pubsub.get_message(timeout=3.0)
            if msg and msg["type"] == "message":
                data = json.loads(msg["data"])
                has_english = "Health Alert" in data.get("title", "")
                log_result(
                    "Medium notification published to dashboard",
                    True,
                    f"Title: {data.get('title', '')[:50]}",
                )
                log_result(
                    "English content in dashboard message",
                    has_english,
                    f"Contains 'Health Alert': {has_english}",
                )
            else:
                log_result("Medium notification published", False, "No message received")
        else:
            log_result("Send medium notification", False, "No medium notification ID")

    except Exception as e:
        log_result("Send medium notification", False, f"Error: {e}")

    await pubsub.unsubscribe(DASHBOARD_CHANNEL)
    await pubsub.close()
    await redis_client.close()


async def test_get_unread_notifications(test_data: dict) -> None:
    """Test 3: get_unread_notifications with urgency ordering."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 3: get_unread_notifications")
    print(f"{'='*60}")

    from cbi.db.session import get_session
    from cbi.services.notifications import get_unread_notifications

    # Test 3a: Get unread for officer with region (Arabic officer - has critical + high)
    print(f"\n  [Test 3a] Get unread for Arabic officer...")
    try:
        async with get_session() as session:
            unread = await get_unread_notifications(session, test_data["officer_id"])

            log_result(
                "Has unread notifications",
                len(unread) > 0,
                f"Count: {len(unread)}",
            )

            # Should have at least 2 (critical + high from test 1)
            log_result(
                "Has multiple notifications",
                len(unread) >= 2,
                f"Expected >= 2, got {len(unread)}",
            )

            # Check ordering: critical should be first
            if len(unread) >= 2:
                first_urgency = unread[0]["urgency"]
                log_result(
                    "Ordered by urgency (critical first)",
                    first_urgency == "critical",
                    f"First urgency: {first_urgency}",
                )

            # Check dict structure
            if unread:
                first = unread[0]
                has_required_keys = all(
                    k in first
                    for k in ["id", "report_id", "urgency", "title", "body", "channels"]
                )
                log_result(
                    "Notification dict has required keys",
                    has_required_keys,
                    f"Keys: {list(first.keys())}",
                )

            # Print all notifications for visual inspection
            print(f"\n  Notifications for officer (Arabic):")
            for n in unread:
                print(f"    - [{n['urgency'].upper()}] {n['title'][:60]}")

    except Exception as e:
        log_result("Get unread for Arabic officer", False, f"Error: {e}")

    # Test 3b: Get unread for English officer
    print(f"\n  [Test 3b] Get unread for English officer...")
    try:
        async with get_session() as session:
            unread = await get_unread_notifications(session, test_data["officer2_id"])

            log_result(
                "English officer has unread",
                len(unread) == 1,
                f"Count: {len(unread)} (expected 1)",
            )

            if unread:
                print(f"    - [{unread[0]['urgency'].upper()}] {unread[0]['title']}")

    except Exception as e:
        log_result("Get unread for English officer", False, f"Error: {e}")

    # Test 3c: Get unread for non-existent officer
    print(f"\n  [Test 3c] Get unread for non-existent officer...")
    try:
        from uuid import uuid4

        async with get_session() as session:
            unread = await get_unread_notifications(session, uuid4())
            log_result(
                "Non-existent officer returns empty list",
                len(unread) == 0,
                f"Count: {len(unread)}",
            )

    except Exception as e:
        log_result("Get unread for non-existent officer", False, f"Error: {e}")


async def test_mark_as_read(test_data: dict, notification_ids: dict) -> None:
    """Test 4: mark_as_read with audit log verification."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 4: mark_as_read")
    print(f"{'='*60}")

    from cbi.db.session import get_session
    from cbi.services.notifications import mark_as_read, get_unread_notifications

    # Test 4a: Mark critical notification as read
    print(f"\n  [Test 4a] Mark critical notification as read...")
    try:
        critical_id = notification_ids.get("critical_ar")
        officer_id = test_data["officer_id"]

        if critical_id:
            async with get_session() as session:
                # Count unread before
                unread_before = await get_unread_notifications(session, officer_id)
                count_before = len(unread_before)

                result = await mark_as_read(session, critical_id, officer_id)

                log_result(
                    "mark_as_read returns True",
                    result is True,
                    f"Result: {result}",
                )

            # Verify read_at is set (new session for fresh data)
            async with get_session() as session:
                from sqlalchemy import text
                row = await session.execute(
                    text("SELECT read_at FROM notifications WHERE id = :id"),
                    {"id": critical_id},
                )
                notification = row.mappings().one()
                has_read_at = notification["read_at"] is not None
                log_result(
                    "read_at timestamp is set",
                    has_read_at,
                    f"read_at: {notification['read_at']}",
                )

                # Verify audit log was created
                audit_row = await session.execute(
                    text("""
                        SELECT entity_type, entity_id, action, actor_type, actor_id, changes
                        FROM audit_logs
                        WHERE entity_id = :id AND action = 'mark_as_read'
                        ORDER BY created_at DESC LIMIT 1
                    """),
                    {"id": critical_id},
                )
                audit = audit_row.mappings().first()

                has_audit = audit is not None
                log_result(
                    "Audit log entry created",
                    has_audit,
                    f"Action: {audit['action'] if audit else 'MISSING'}, "
                    f"Actor: {audit['actor_id'] if audit else 'MISSING'}",
                )

                if audit:
                    correct_entity = audit["entity_type"] == "notification"
                    correct_actor = audit["actor_type"] == "officer"
                    correct_actor_id = audit["actor_id"] == str(officer_id)
                    log_result(
                        "Audit log has correct fields",
                        correct_entity and correct_actor and correct_actor_id,
                        f"entity_type={audit['entity_type']}, actor_type={audit['actor_type']}",
                    )

                # Verify unread count decreased
                unread_after = await get_unread_notifications(session, officer_id)
                count_after = len(unread_after)
                log_result(
                    "Unread count decreased after mark_as_read",
                    count_after < count_before,
                    f"Before: {count_before}, After: {count_after}",
                )

        else:
            log_result("Mark critical notification as read", False, "No critical notification ID")

    except Exception as e:
        log_result("Mark critical notification as read", False, f"Error: {e}")

    # Test 4b: Mark same notification again (should return False)
    print(f"\n  [Test 4b] Mark already-read notification again...")
    try:
        critical_id = notification_ids.get("critical_ar")
        officer_id = test_data["officer_id"]

        if critical_id:
            async with get_session() as session:
                result = await mark_as_read(session, critical_id, officer_id)
                log_result(
                    "Double mark returns False",
                    result is False,
                    f"Result: {result}",
                )
        else:
            log_result("Double mark returns False", False, "No notification ID")

    except Exception as e:
        log_result("Double mark returns False", False, f"Error: {e}")

    # Test 4c: Mark with wrong officer_id (should return False)
    print(f"\n  [Test 4c] Mark with wrong officer ID...")
    try:
        from uuid import uuid4

        high_id = notification_ids.get("high_model")
        if high_id:
            async with get_session() as session:
                result = await mark_as_read(session, high_id, uuid4())
                log_result(
                    "Wrong officer returns False",
                    result is False,
                    f"Result: {result}",
                )
        else:
            log_result("Wrong officer returns False", False, "No notification ID")

    except Exception as e:
        log_result("Wrong officer returns False", False, f"Error: {e}")


async def cleanup(test_data: dict) -> None:
    """Clean up test data."""
    from cbi.db.session import get_session
    from sqlalchemy import text

    print(f"\n[{INFO}] Cleaning up test data...")

    async with get_session() as session:
        # Delete in order (FK constraints)
        await session.execute(
            text("DELETE FROM audit_logs WHERE actor_id IN (:o1, :o2)"),
            {"o1": str(test_data["officer_id"]), "o2": str(test_data["officer2_id"])},
        )
        await session.execute(
            text("DELETE FROM notifications WHERE officer_id IN (:o1, :o2)"),
            {"o1": test_data["officer_id"], "o2": test_data["officer2_id"]},
        )
        await session.execute(
            text("DELETE FROM reports WHERE conversation_id IN ('test-conv-notif-001', 'test-conv-notif-002')"),
        )
        await session.execute(
            text("DELETE FROM officers WHERE email IN ('test.officer.notif@cbi.local', 'test.officer2.notif@cbi.local')"),
        )

    print("  Cleanup complete.")


async def main() -> None:
    """Run all notification flow tests."""
    print("=" * 60)
    print(" CBI Phase 4.3: Notification Service - Full Flow Test")
    print("=" * 60)

    from cbi.db.session import init_db, close_db
    from cbi.services.message_queue import close_redis_client

    # Initialize database connection
    print(f"\n[{INFO}] Initializing database connection...")
    await init_db(echo=False)

    test_data = {}
    notification_ids = {}

    try:
        # Setup
        test_data = await setup_test_data()

        # Run tests
        notification_ids = await test_create_notification(test_data)
        await test_send_notification(notification_ids)
        await test_get_unread_notifications(test_data)
        await test_mark_as_read(test_data, notification_ids)

    except Exception as e:
        print(f"\n[{FAIL}] Unexpected error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        if test_data:
            await cleanup(test_data)

        await close_redis_client()
        await close_db()

    # Print summary
    print(f"\n{'='*60}")
    print(" TEST SUMMARY")
    print(f"{'='*60}")
    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    total = len(results)
    print(f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")

    if failed > 0:
        print(f"\n  Failed tests:")
        for name, p, detail in results:
            if not p:
                print(f"    - {name}: {detail}")

    print(f"\n{'='*60}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
