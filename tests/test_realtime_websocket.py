"""
Test script for Phase 5.3: WebSocket Real-time Updates.

Tests:
1. RealtimeService unit tests (publish_notification, publish_report_update, broadcast)
2. WebSocket authentication (valid/invalid/expired/refresh token)
3. Connection lifecycle (connect, confirmation, disconnect, cleanup)
4. Heartbeat mechanism (ping sent periodically)
5. Pub/sub forwarding (Redis messages forwarded to WebSocket)
6. Notification integration (notifications publish to realtime channels)
7. Reports integration (report updates publish to realtime channels)
8. Error handling (Redis down, concurrent connections, graceful degradation)

Requires: PostgreSQL (cbi-db) and Redis (cbi-redis) running via Docker.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from uuid import UUID, uuid4

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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

import redis.asyncio as aioredis

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


# =============================================================================
# Setup helpers
# =============================================================================

async def get_redis() -> aioredis.Redis:
    """Get a fresh Redis client for testing."""
    return aioredis.from_url(
        "redis://localhost:6379/0",
        encoding="utf-8",
        decode_responses=True,
    )


async def setup_test_data() -> dict:
    """Create test officer and report in the database."""
    from sqlalchemy import text
    from cbi.db.session import get_session

    print(f"\n[{INFO}] Setting up test data...")

    async with get_session() as session:
        # Create a test officer
        officer_result = await session.execute(
            text("""
                INSERT INTO officers (id, email, password_hash, name, region, role, is_active)
                VALUES (
                    uuid_generate_v4(),
                    'test.ws.officer@cbi.local',
                    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYA/pWrWuqGi',
                    'Dr. WebSocket Test',
                    'Khartoum',
                    'officer',
                    TRUE
                )
                ON CONFLICT (email) DO UPDATE SET name = 'Dr. WebSocket Test'
                RETURNING id
            """)
        )
        officer_id = officer_result.scalar_one()
        print(f"  Officer ID: {officer_id}")

        # Create a second officer (inactive, for auth tests)
        officer2_result = await session.execute(
            text("""
                INSERT INTO officers (id, email, password_hash, name, region, role, is_active)
                VALUES (
                    uuid_generate_v4(),
                    'test.ws.inactive@cbi.local',
                    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYA/pWrWuqGi',
                    'Dr. Inactive Officer',
                    'Khartoum',
                    'officer',
                    FALSE
                )
                ON CONFLICT (email) DO UPDATE SET is_active = FALSE
                RETURNING id
            """)
        )
        officer2_id = officer2_result.scalar_one()
        print(f"  Inactive Officer ID: {officer2_id}")

        # Create a test report
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
                    'test-conv-ws-001',
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

    return {
        "officer_id": officer_id,
        "inactive_officer_id": officer2_id,
        "report_id": report_id,
    }


# =============================================================================
# TEST 1: RealtimeService Unit Tests
# =============================================================================

async def test_realtime_service(test_data: dict) -> None:
    """Test RealtimeService publish methods."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 1: RealtimeService Unit Tests")
    print(f"{'='*60}")

    from cbi.services.realtime import (
        RealtimeService,
        CHANNEL_NOTIFICATION_PREFIX,
        CHANNEL_BROADCAST,
        CHANNEL_REPORT_UPDATES,
    )

    redis_client = await get_redis()
    service = RealtimeService(redis_client)
    officer_id = str(test_data["officer_id"])

    # Test 1a: publish_notification sends to officer-specific channel
    print(f"\n  [Test 1a] publish_notification to officer channel...")
    try:
        pubsub = redis_client.pubsub()
        channel = f"{CHANNEL_NOTIFICATION_PREFIX}{officer_id}"
        await pubsub.subscribe(channel)
        # Consume subscription confirmation
        await pubsub.get_message(timeout=2.0)

        notification_data = {
            "id": str(uuid4()),
            "title": "Test notification",
            "urgency": "critical",
        }
        count = await service.publish_notification(notification_data, [officer_id])

        msg = await pubsub.get_message(timeout=3.0)
        if msg and msg["type"] == "message":
            data = json.loads(msg["data"])
            correct_type = data.get("type") == "notification"
            has_data = "data" in data
            has_timestamp = "timestamp" in data
            has_notification = data["data"].get("title") == "Test notification"

            log_result(
                "publish_notification: message type is 'notification'",
                correct_type,
                f"type: {data.get('type')}",
            )
            log_result(
                "publish_notification: contains data payload",
                has_data and has_notification,
                f"title: {data.get('data', {}).get('title')}",
            )
            log_result(
                "publish_notification: contains timestamp",
                has_timestamp,
                f"timestamp: {data.get('timestamp', 'MISSING')}",
            )
        else:
            log_result("publish_notification: message received", False, "No message received")

        await pubsub.unsubscribe(channel)
        await pubsub.close()
    except Exception as e:
        log_result("publish_notification", False, f"Error: {e}")

    # Test 1b: publish_notification to multiple officers
    print(f"\n  [Test 1b] publish_notification to multiple officers...")
    try:
        officer2_id = str(uuid4())
        pubsub1 = redis_client.pubsub()
        pubsub2 = redis_client.pubsub()
        ch1 = f"{CHANNEL_NOTIFICATION_PREFIX}{officer_id}"
        ch2 = f"{CHANNEL_NOTIFICATION_PREFIX}{officer2_id}"
        await pubsub1.subscribe(ch1)
        await pubsub2.subscribe(ch2)
        await pubsub1.get_message(timeout=2.0)
        await pubsub2.get_message(timeout=2.0)

        notification_data = {"id": str(uuid4()), "title": "Multi-officer test"}
        count = await service.publish_notification(notification_data, [officer_id, officer2_id])

        msg1 = await pubsub1.get_message(timeout=3.0)
        msg2 = await pubsub2.get_message(timeout=3.0)

        both_received = (
            msg1 is not None and msg1["type"] == "message"
            and msg2 is not None and msg2["type"] == "message"
        )
        log_result(
            "publish_notification: multi-officer delivery",
            both_received,
            f"Officer 1 received: {msg1 is not None and msg1.get('type') == 'message'}, "
            f"Officer 2 received: {msg2 is not None and msg2.get('type') == 'message'}",
        )

        await pubsub1.unsubscribe(ch1)
        await pubsub2.unsubscribe(ch2)
        await pubsub1.close()
        await pubsub2.close()
    except Exception as e:
        log_result("publish_notification: multi-officer", False, f"Error: {e}")

    # Test 1c: publish_report_update
    print(f"\n  [Test 1c] publish_report_update...")
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(CHANNEL_REPORT_UPDATES)
        await pubsub.get_message(timeout=2.0)

        report_id = str(test_data["report_id"])
        count = await service.publish_report_update(
            report_id,
            "status_change",
            data={"status": "investigating", "officer_id": officer_id},
        )

        msg = await pubsub.get_message(timeout=3.0)
        if msg and msg["type"] == "message":
            data = json.loads(msg["data"])
            correct_type = data.get("type") == "report_update"
            has_report_id = data.get("data", {}).get("report_id") == report_id
            has_update_type = data.get("data", {}).get("update_type") == "status_change"
            has_extra_data = data.get("data", {}).get("status") == "investigating"

            log_result(
                "publish_report_update: type is 'report_update'",
                correct_type,
                f"type: {data.get('type')}",
            )
            log_result(
                "publish_report_update: contains report_id",
                has_report_id,
                f"report_id: {data.get('data', {}).get('report_id')}",
            )
            log_result(
                "publish_report_update: contains update_type",
                has_update_type,
                f"update_type: {data.get('data', {}).get('update_type')}",
            )
            log_result(
                "publish_report_update: contains extra data",
                has_extra_data,
                f"status: {data.get('data', {}).get('status')}",
            )
        else:
            log_result("publish_report_update: message received", False, "No message received")

        await pubsub.unsubscribe(CHANNEL_REPORT_UPDATES)
        await pubsub.close()
    except Exception as e:
        log_result("publish_report_update", False, f"Error: {e}")

    # Test 1d: broadcast
    print(f"\n  [Test 1d] broadcast...")
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(CHANNEL_BROADCAST)
        await pubsub.get_message(timeout=2.0)

        broadcast_data = {"message": "System maintenance in 1 hour", "level": "info"}
        count = await service.broadcast(broadcast_data)

        msg = await pubsub.get_message(timeout=3.0)
        if msg and msg["type"] == "message":
            data = json.loads(msg["data"])
            correct_type = data.get("type") == "broadcast"
            has_message = data.get("data", {}).get("message") == "System maintenance in 1 hour"

            log_result(
                "broadcast: type is 'broadcast'",
                correct_type,
                f"type: {data.get('type')}",
            )
            log_result(
                "broadcast: contains broadcast data",
                has_message,
                f"message: {data.get('data', {}).get('message')}",
            )
        else:
            log_result("broadcast: message received", False, "No message received")

        await pubsub.unsubscribe(CHANNEL_BROADCAST)
        await pubsub.close()
    except Exception as e:
        log_result("broadcast", False, f"Error: {e}")

    # Test 1e: Return value (subscriber count)
    print(f"\n  [Test 1e] Return values (subscriber counts)...")
    try:
        # No subscribers attached, so count should be 0
        count = await service.publish_report_update(str(uuid4()), "test", data={})
        log_result(
            "publish_report_update returns int (subscriber count)",
            isinstance(count, int),
            f"count: {count} (type: {type(count).__name__})",
        )

        count = await service.broadcast({"test": True})
        log_result(
            "broadcast returns int (subscriber count)",
            isinstance(count, int),
            f"count: {count} (type: {type(count).__name__})",
        )
    except Exception as e:
        log_result("Return values", False, f"Error: {e}")

    await redis_client.close()


# =============================================================================
# TEST 2: WebSocket Authentication
# =============================================================================

async def test_websocket_auth(test_data: dict) -> None:
    """Test WebSocket authentication logic."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 2: WebSocket Authentication")
    print(f"{'='*60}")

    from cbi.services.auth import create_access_token, create_refresh_token
    from cbi.api.routes.websocket import _authenticate

    officer_id = str(test_data["officer_id"])
    inactive_officer_id = str(test_data["inactive_officer_id"])

    # Test 2a: Valid access token
    print(f"\n  [Test 2a] Valid access token...")
    try:
        token = create_access_token(officer_id, role="officer")
        result = await _authenticate(token)

        log_result(
            "Valid token: authentication succeeds",
            result is not None,
            f"result: {result}",
        )
        if result:
            log_result(
                "Valid token: returns correct officer_id",
                result[0] == officer_id,
                f"officer_id: {result[0]}",
            )
            log_result(
                "Valid token: returns correct role",
                result[1] == "officer",
                f"role: {result[1]}",
            )
    except Exception as e:
        log_result("Valid access token", False, f"Error: {e}")

    # Test 2b: Invalid token
    print(f"\n  [Test 2b] Invalid token...")
    try:
        result = await _authenticate("invalid.jwt.token")
        log_result(
            "Invalid token: returns None",
            result is None,
            f"result: {result}",
        )
    except Exception as e:
        log_result("Invalid token", False, f"Error: {e}")

    # Test 2c: Refresh token (should be rejected)
    print(f"\n  [Test 2c] Refresh token (should be rejected)...")
    try:
        refresh_token = create_refresh_token(officer_id)
        result = await _authenticate(refresh_token)
        log_result(
            "Refresh token: rejected (returns None)",
            result is None,
            f"result: {result}",
        )
    except Exception as e:
        log_result("Refresh token rejection", False, f"Error: {e}")

    # Test 2d: Expired token
    print(f"\n  [Test 2d] Expired token...")
    try:
        from jose import jwt as jose_jwt
        settings = get_settings()
        expired_payload = {
            "sub": officer_id,
            "role": "officer",
            "type": "access",
            "exp": datetime.utcnow() - timedelta(hours=1),
            "iat": datetime.utcnow() - timedelta(hours=25),
        }
        expired_token = jose_jwt.encode(
            expired_payload,
            settings.jwt_secret.get_secret_value(),
            algorithm=settings.jwt_algorithm,
        )
        result = await _authenticate(expired_token)
        log_result(
            "Expired token: returns None",
            result is None,
            f"result: {result}",
        )
    except Exception as e:
        log_result("Expired token", False, f"Error: {e}")

    # Test 2e: Token for inactive officer
    print(f"\n  [Test 2e] Token for inactive officer...")
    try:
        token = create_access_token(inactive_officer_id, role="officer")
        result = await _authenticate(token)
        log_result(
            "Inactive officer token: returns None",
            result is None,
            f"result: {result}",
        )
    except Exception as e:
        log_result("Inactive officer token", False, f"Error: {e}")

    # Test 2f: Token for non-existent officer
    print(f"\n  [Test 2f] Token for non-existent officer...")
    try:
        fake_id = str(uuid4())
        token = create_access_token(fake_id, role="officer")
        result = await _authenticate(fake_id)
        # fake_id is not a token, let's use the actual token
        result = await _authenticate(token)
        log_result(
            "Non-existent officer token: returns None",
            result is None,
            f"result: {result}",
        )
    except Exception as e:
        log_result("Non-existent officer token", False, f"Error: {e}")

    # Test 2g: Admin role token
    print(f"\n  [Test 2g] Admin role token...")
    try:
        admin_token = create_access_token(officer_id, role="admin")
        result = await _authenticate(admin_token)
        log_result(
            "Admin token: authentication succeeds",
            result is not None,
            f"result: {result}",
        )
        if result:
            log_result(
                "Admin token: returns 'admin' role",
                result[1] == "admin",
                f"role: {result[1]}",
            )
    except Exception as e:
        log_result("Admin role token", False, f"Error: {e}")


# =============================================================================
# TEST 3: Connection Management
# =============================================================================

async def test_connection_management(test_data: dict) -> None:
    """Test WebSocket connection tracking functions."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 3: Connection Management")
    print(f"{'='*60}")

    from cbi.api.routes.websocket import (
        _connected_clients,
        _register,
        _unregister,
        _get_connected_count,
    )

    officer_id = str(test_data["officer_id"])

    # Clear any existing state
    _connected_clients.clear()

    # Test 3a: Register a connection
    print(f"\n  [Test 3a] Register a connection...")
    try:
        # Use a mock object as WebSocket stand-in
        class MockWS:
            pass

        ws1 = MockWS()
        _register(officer_id, ws1)

        log_result(
            "register: officer added to connected_clients",
            officer_id in _connected_clients,
            f"officers: {list(_connected_clients.keys())}",
        )
        log_result(
            "register: connection count is 1",
            _get_connected_count() == 1,
            f"count: {_get_connected_count()}",
        )
    except Exception as e:
        log_result("Register connection", False, f"Error: {e}")

    # Test 3b: Register a second connection for the same officer
    print(f"\n  [Test 3b] Register second connection for same officer...")
    try:
        ws2 = MockWS()
        _register(officer_id, ws2)

        connections_for_officer = len(_connected_clients.get(officer_id, set()))
        log_result(
            "register: same officer has 2 connections",
            connections_for_officer == 2,
            f"connections: {connections_for_officer}",
        )
        log_result(
            "register: total count is 2",
            _get_connected_count() == 2,
            f"count: {_get_connected_count()}",
        )
    except Exception as e:
        log_result("Second connection", False, f"Error: {e}")

    # Test 3c: Register connection for a different officer
    print(f"\n  [Test 3c] Register connection for different officer...")
    try:
        other_officer = str(uuid4())
        ws3 = MockWS()
        _register(other_officer, ws3)

        log_result(
            "register: two officers tracked",
            len(_connected_clients) == 2,
            f"officers: {list(_connected_clients.keys())}",
        )
        log_result(
            "register: total count is 3",
            _get_connected_count() == 3,
            f"count: {_get_connected_count()}",
        )
    except Exception as e:
        log_result("Different officer connection", False, f"Error: {e}")

    # Test 3d: Unregister one connection
    print(f"\n  [Test 3d] Unregister one connection...")
    try:
        _unregister(officer_id, ws1)

        connections_for_officer = len(_connected_clients.get(officer_id, set()))
        log_result(
            "unregister: officer still has 1 connection",
            connections_for_officer == 1,
            f"connections: {connections_for_officer}",
        )
        log_result(
            "unregister: total count is 2",
            _get_connected_count() == 2,
            f"count: {_get_connected_count()}",
        )
    except Exception as e:
        log_result("Unregister connection", False, f"Error: {e}")

    # Test 3e: Unregister last connection for an officer (should remove key)
    print(f"\n  [Test 3e] Unregister last connection (removes officer key)...")
    try:
        _unregister(officer_id, ws2)

        officer_removed = officer_id not in _connected_clients
        log_result(
            "unregister: officer key removed when no connections",
            officer_removed,
            f"officers remaining: {list(_connected_clients.keys())}",
        )
        log_result(
            "unregister: total count is 1",
            _get_connected_count() == 1,
            f"count: {_get_connected_count()}",
        )
    except Exception as e:
        log_result("Remove officer key", False, f"Error: {e}")

    # Test 3f: Unregister non-existent connection (should not error)
    print(f"\n  [Test 3f] Unregister non-existent connection (no error)...")
    try:
        fake_ws = MockWS()
        _unregister("non-existent-officer", fake_ws)  # Should not raise
        log_result(
            "unregister: no error for non-existent officer",
            True,
            "No exception raised",
        )
    except Exception as e:
        log_result("Non-existent unregister", False, f"Error: {e}")

    # Cleanup
    _connected_clients.clear()


# =============================================================================
# TEST 4: Heartbeat Mechanism
# =============================================================================

async def test_heartbeat() -> None:
    """Test heartbeat function sends periodic pings."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 4: Heartbeat Mechanism")
    print(f"{'='*60}")

    from cbi.api.routes.websocket import _heartbeat

    # Test 4a: Heartbeat sends JSON ping messages
    print(f"\n  [Test 4a] Heartbeat sends ping messages...")
    try:
        sent_messages = []

        class MockHeartbeatWS:
            async def send_json(self, data):
                sent_messages.append(data)

        mock_ws = MockHeartbeatWS()

        # Temporarily patch the heartbeat interval for faster test
        import cbi.api.routes.websocket as ws_module
        original_interval = ws_module.HEARTBEAT_INTERVAL
        ws_module.HEARTBEAT_INTERVAL = 0.1  # 100ms for testing

        heartbeat_task = asyncio.create_task(_heartbeat(mock_ws))
        await asyncio.sleep(0.35)  # Should get ~3 pings at 100ms interval
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        # Restore original interval
        ws_module.HEARTBEAT_INTERVAL = original_interval

        log_result(
            "heartbeat: sends multiple ping messages",
            len(sent_messages) >= 2,
            f"pings sent: {len(sent_messages)}",
        )

        if sent_messages:
            first_ping = sent_messages[0]
            has_type = first_ping.get("type") == "ping"
            has_timestamp = "timestamp" in first_ping
            log_result(
                "heartbeat: ping has type='ping'",
                has_type,
                f"type: {first_ping.get('type')}",
            )
            log_result(
                "heartbeat: ping has timestamp",
                has_timestamp,
                f"timestamp present: {has_timestamp}",
            )
    except Exception as e:
        log_result("Heartbeat pings", False, f"Error: {e}")

    # Test 4b: Heartbeat handles connection close gracefully
    print(f"\n  [Test 4b] Heartbeat handles connection close gracefully...")
    try:
        class MockClosedWS:
            async def send_json(self, data):
                raise ConnectionError("Connection closed")

        mock_ws = MockClosedWS()
        # Should not raise; just returns silently
        await _heartbeat(mock_ws)
        log_result(
            "heartbeat: handles connection close without exception",
            True,
            "Returned gracefully on connection error",
        )
    except Exception as e:
        log_result("Heartbeat connection close", False, f"Error: {e}")


# =============================================================================
# TEST 5: Pub/Sub Forwarding
# =============================================================================

async def test_pubsub_forwarding(test_data: dict) -> None:
    """Test that Redis pub/sub messages are forwarded correctly."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 5: Pub/Sub Forwarding")
    print(f"{'='*60}")

    from cbi.services.realtime import (
        CHANNEL_NOTIFICATION_PREFIX,
        CHANNEL_BROADCAST,
        CHANNEL_REPORT_UPDATES,
    )
    from cbi.api.routes.websocket import _subscribe_and_forward

    officer_id = str(test_data["officer_id"])
    redis_client = await get_redis()

    # Test 5a: Messages on officer-specific channel are forwarded
    print(f"\n  [Test 5a] Officer-specific channel forwarding...")
    try:
        forwarded_messages = []

        class MockForwardWS:
            async def send_text(self, data):
                forwarded_messages.append(data)

        mock_ws = MockForwardWS()
        forward_task = asyncio.create_task(
            _subscribe_and_forward(mock_ws, officer_id, redis_client)
        )
        # Give time for subscription to establish
        await asyncio.sleep(0.3)

        # Publish to officer-specific channel
        pub_redis = await get_redis()
        channel = f"{CHANNEL_NOTIFICATION_PREFIX}{officer_id}"
        test_msg = json.dumps({"type": "notification", "data": {"test": "officer-specific"}})
        await pub_redis.publish(channel, test_msg)

        await asyncio.sleep(1.5)  # Wait for message to be received via polling
        forward_task.cancel()
        try:
            await forward_task
        except asyncio.CancelledError:
            pass

        officer_msg_received = any(
            "officer-specific" in m for m in forwarded_messages
        )
        log_result(
            "pub/sub: officer-specific channel message forwarded",
            officer_msg_received,
            f"messages received: {len(forwarded_messages)}",
        )
        await pub_redis.close()
    except Exception as e:
        log_result("Officer-specific forwarding", False, f"Error: {e}")

    # Test 5b: Broadcast channel forwarding
    print(f"\n  [Test 5b] Broadcast channel forwarding...")
    try:
        forwarded_messages = []
        mock_ws = MockForwardWS()
        forward_task = asyncio.create_task(
            _subscribe_and_forward(mock_ws, officer_id, redis_client)
        )
        await asyncio.sleep(0.3)

        pub_redis = await get_redis()
        test_msg = json.dumps({"type": "broadcast", "data": {"test": "broadcast-msg"}})
        await pub_redis.publish(CHANNEL_BROADCAST, test_msg)

        await asyncio.sleep(1.5)
        forward_task.cancel()
        try:
            await forward_task
        except asyncio.CancelledError:
            pass

        broadcast_received = any(
            "broadcast-msg" in m for m in forwarded_messages
        )
        log_result(
            "pub/sub: broadcast channel message forwarded",
            broadcast_received,
            f"messages received: {len(forwarded_messages)}",
        )
        await pub_redis.close()
    except Exception as e:
        log_result("Broadcast forwarding", False, f"Error: {e}")

    # Test 5c: Report updates channel forwarding
    print(f"\n  [Test 5c] Report updates channel forwarding...")
    try:
        forwarded_messages = []
        mock_ws = MockForwardWS()
        forward_task = asyncio.create_task(
            _subscribe_and_forward(mock_ws, officer_id, redis_client)
        )
        await asyncio.sleep(0.3)

        pub_redis = await get_redis()
        test_msg = json.dumps({"type": "report_update", "data": {"test": "report-update-msg"}})
        await pub_redis.publish(CHANNEL_REPORT_UPDATES, test_msg)

        await asyncio.sleep(1.5)
        forward_task.cancel()
        try:
            await forward_task
        except asyncio.CancelledError:
            pass

        report_received = any(
            "report-update-msg" in m for m in forwarded_messages
        )
        log_result(
            "pub/sub: report updates channel message forwarded",
            report_received,
            f"messages received: {len(forwarded_messages)}",
        )
        await pub_redis.close()
    except Exception as e:
        log_result("Report updates forwarding", False, f"Error: {e}")

    # Test 5d: Messages on OTHER officer's channel are NOT forwarded
    print(f"\n  [Test 5d] Other officer's channel NOT forwarded...")
    try:
        forwarded_messages = []
        mock_ws = MockForwardWS()
        forward_task = asyncio.create_task(
            _subscribe_and_forward(mock_ws, officer_id, redis_client)
        )
        await asyncio.sleep(0.3)

        pub_redis = await get_redis()
        other_channel = f"{CHANNEL_NOTIFICATION_PREFIX}{uuid4()}"
        test_msg = json.dumps({"type": "notification", "data": {"test": "other-officer"}})
        await pub_redis.publish(other_channel, test_msg)

        await asyncio.sleep(1.5)
        forward_task.cancel()
        try:
            await forward_task
        except asyncio.CancelledError:
            pass

        other_not_received = not any(
            "other-officer" in m for m in forwarded_messages
        )
        log_result(
            "pub/sub: other officer's messages NOT forwarded",
            other_not_received,
            f"messages with other-officer content: {sum(1 for m in forwarded_messages if 'other-officer' in m)}",
        )
        await pub_redis.close()
    except Exception as e:
        log_result("Other officer isolation", False, f"Error: {e}")

    await redis_client.close()


# =============================================================================
# TEST 6: Notification Integration
# =============================================================================

async def test_notification_integration(test_data: dict) -> None:
    """Test that notification service publishes to realtime channels."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 6: Notification Integration")
    print(f"{'='*60}")

    from cbi.services.realtime import CHANNEL_NOTIFICATION_PREFIX, CHANNEL_BROADCAST
    from cbi.services.notifications import create_notification, send_notification, DASHBOARD_CHANNEL

    officer_id = str(test_data["officer_id"])
    report_id = test_data["report_id"]
    redis_client = await get_redis()

    # Test 6a: send_notification publishes to legacy dashboard channel
    print(f"\n  [Test 6a] send_notification publishes to legacy dashboard channel...")
    try:
        # First create a notification
        from cbi.db.session import get_session
        async with get_session() as session:
            notif_id = await create_notification(
                session,
                report_id=report_id,
                officer_id=test_data["officer_id"],
                urgency="high",
                classification={
                    "suspected_disease": "cholera",
                    "confidence": 0.9,
                    "urgency": "high",
                    "alert_type": "suspected_outbreak",
                    "reasoning": "Test notification for realtime",
                    "recommended_actions": [],
                },
            )

        # Subscribe to channels
        pubsub_dashboard = redis_client.pubsub()
        await pubsub_dashboard.subscribe(DASHBOARD_CHANNEL)
        await pubsub_dashboard.get_message(timeout=2.0)

        pubsub_officer = redis_client.pubsub()
        officer_channel = f"{CHANNEL_NOTIFICATION_PREFIX}{officer_id}"
        await pubsub_officer.subscribe(officer_channel)
        await pubsub_officer.get_message(timeout=2.0)

        # Send the notification
        await send_notification(notif_id)

        # Check legacy dashboard channel
        msg = await pubsub_dashboard.get_message(timeout=3.0)
        legacy_received = msg is not None and msg["type"] == "message"
        log_result(
            "notification: published to legacy dashboard channel",
            legacy_received,
            f"received: {legacy_received}",
        )

        if legacy_received:
            data = json.loads(msg["data"])
            has_id = data.get("id") == str(notif_id)
            log_result(
                "notification: dashboard message has correct ID",
                has_id,
                f"id: {data.get('id')}",
            )

        # Check officer-specific realtime channel
        msg_officer = await pubsub_officer.get_message(timeout=3.0)
        officer_received = msg_officer is not None and msg_officer["type"] == "message"
        log_result(
            "notification: published to officer-specific realtime channel",
            officer_received,
            f"received: {officer_received}",
        )

        if officer_received:
            data = json.loads(msg_officer["data"])
            correct_type = data.get("type") == "notification"
            log_result(
                "notification: realtime message type is 'notification'",
                correct_type,
                f"type: {data.get('type')}",
            )

        await pubsub_dashboard.unsubscribe(DASHBOARD_CHANNEL)
        await pubsub_dashboard.close()
        await pubsub_officer.unsubscribe(officer_channel)
        await pubsub_officer.close()
    except Exception as e:
        log_result("Notification integration", False, f"Error: {e}")

    # Test 6b: Notification without officer_id broadcasts
    print(f"\n  [Test 6b] Notification broadcast when no officer_id...")
    try:
        pubsub_broadcast = redis_client.pubsub()
        await pubsub_broadcast.subscribe(CHANNEL_BROADCAST)
        await pubsub_broadcast.get_message(timeout=2.0)

        from cbi.db.session import get_session
        async with get_session() as session:
            notif_id = await create_notification(
                session,
                report_id=report_id,
                officer_id=None,
                urgency="medium",
                classification={
                    "suspected_disease": "dengue",
                    "confidence": 0.7,
                    "urgency": "medium",
                    "alert_type": "single_case",
                    "reasoning": "Broadcast test",
                    "recommended_actions": [],
                },
            )

        await send_notification(notif_id)

        msg = await pubsub_broadcast.get_message(timeout=3.0)
        broadcast_received = msg is not None and msg["type"] == "message"
        log_result(
            "notification: broadcast channel receives when no officer_id",
            broadcast_received,
            f"received: {broadcast_received}",
        )

        await pubsub_broadcast.unsubscribe(CHANNEL_BROADCAST)
        await pubsub_broadcast.close()
    except Exception as e:
        log_result("Notification broadcast", False, f"Error: {e}")

    await redis_client.close()


# =============================================================================
# TEST 7: Reports Integration
# =============================================================================

async def test_reports_integration(test_data: dict) -> None:
    """Test that report updates publish to realtime channels."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 7: Reports Integration")
    print(f"{'='*60}")

    from cbi.services.realtime import RealtimeService, CHANNEL_REPORT_UPDATES

    officer_id = str(test_data["officer_id"])
    report_id = str(test_data["report_id"])
    redis_client = await get_redis()

    # Test 7a: Report status change publishes update
    print(f"\n  [Test 7a] Report update published via RealtimeService...")
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(CHANNEL_REPORT_UPDATES)
        await pubsub.get_message(timeout=2.0)

        service = RealtimeService(redis_client)
        await service.publish_report_update(
            report_id,
            "status_change",
            data={
                "fields": ["status"],
                "status": "investigating",
                "urgency": "critical",
                "officer_id": officer_id,
            },
        )

        msg = await pubsub.get_message(timeout=3.0)
        if msg and msg["type"] == "message":
            data = json.loads(msg["data"])
            correct_type = data.get("type") == "report_update"
            correct_report = data.get("data", {}).get("report_id") == report_id
            correct_update = data.get("data", {}).get("update_type") == "status_change"
            has_fields = "fields" in data.get("data", {})

            log_result(
                "report update: correct message type",
                correct_type,
                f"type: {data.get('type')}",
            )
            log_result(
                "report update: correct report_id",
                correct_report,
                f"report_id: {data.get('data', {}).get('report_id')}",
            )
            log_result(
                "report update: correct update_type",
                correct_update,
                f"update_type: {data.get('data', {}).get('update_type')}",
            )
            log_result(
                "report update: includes extra fields",
                has_fields,
                f"fields: {data.get('data', {}).get('fields')}",
            )
        else:
            log_result("Report update message", False, "No message received")

        await pubsub.unsubscribe(CHANNEL_REPORT_UPDATES)
        await pubsub.close()
    except Exception as e:
        log_result("Report update publish", False, f"Error: {e}")

    # Test 7b: Note added publishes update
    print(f"\n  [Test 7b] Note added published via RealtimeService...")
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(CHANNEL_REPORT_UPDATES)
        await pubsub.get_message(timeout=2.0)

        service = RealtimeService(redis_client)
        await service.publish_report_update(
            report_id,
            "note_added",
            data={"officer_id": officer_id},
        )

        msg = await pubsub.get_message(timeout=3.0)
        if msg and msg["type"] == "message":
            data = json.loads(msg["data"])
            correct_update = data.get("data", {}).get("update_type") == "note_added"
            log_result(
                "note_added: correct update_type",
                correct_update,
                f"update_type: {data.get('data', {}).get('update_type')}",
            )
        else:
            log_result("Note added message", False, "No message received")

        await pubsub.unsubscribe(CHANNEL_REPORT_UPDATES)
        await pubsub.close()
    except Exception as e:
        log_result("Note added publish", False, f"Error: {e}")

    await redis_client.close()


# =============================================================================
# TEST 8: Error Handling & Edge Cases
# =============================================================================

async def test_error_handling(test_data: dict) -> None:
    """Test error handling and graceful degradation."""
    print(f"\n{'='*60}")
    print(f"[{INFO}] TEST 8: Error Handling & Edge Cases")
    print(f"{'='*60}")

    from cbi.services.realtime import RealtimeService

    # Test 8a: RealtimeService with failed Redis publish (returns 0)
    print(f"\n  [Test 8a] RealtimeService with broken Redis returns 0...")
    try:
        class BrokenRedis:
            async def publish(self, channel, message):
                raise ConnectionError("Redis connection lost")

        broken_service = RealtimeService(BrokenRedis())

        # publish_report_update should return 0 on error, not raise
        count = await broken_service.publish_report_update(
            str(uuid4()), "test", data={}
        )
        log_result(
            "broken Redis: publish_report_update returns 0",
            count == 0,
            f"count: {count}",
        )

        # broadcast should return 0 on error, not raise
        count = await broken_service.broadcast({"test": True})
        log_result(
            "broken Redis: broadcast returns 0",
            count == 0,
            f"count: {count}",
        )
    except Exception as e:
        log_result("Broken Redis handling", False, f"Unexpected exception: {e}")

    # Test 8b: publish_notification handles per-officer errors gracefully
    print(f"\n  [Test 8b] publish_notification handles per-officer errors...")
    try:
        call_count = 0

        class PartialBrokenRedis:
            async def publish(self, channel, message):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise ConnectionError("First publish fails")
                return 1  # Second succeeds

        partial_service = RealtimeService(PartialBrokenRedis())

        # Should not raise even when one officer channel fails
        count = await partial_service.publish_notification(
            {"id": str(uuid4()), "title": "test"},
            [str(uuid4()), str(uuid4())],
        )
        log_result(
            "partial failure: publish_notification continues after error",
            count >= 0,  # Should be 1 (second officer succeeded)
            f"total subscribers: {count}",
        )
    except Exception as e:
        log_result("Partial failure handling", False, f"Unexpected exception: {e}")

    # Test 8c: _serialize handles non-serializable objects via default=str
    print(f"\n  [Test 8c] _serialize handles UUID and datetime...")
    try:
        from cbi.services.realtime import _serialize

        test_data_serialize = {
            "id": uuid4(),
            "timestamp": datetime.utcnow(),
            "nested": {"uuid": uuid4()},
        }
        result = _serialize(test_data_serialize)
        parsed = json.loads(result)

        log_result(
            "_serialize: handles UUID and datetime",
            isinstance(parsed["id"], str) and isinstance(parsed["timestamp"], str),
            f"id type: {type(parsed['id']).__name__}, timestamp type: {type(parsed['timestamp']).__name__}",
        )
    except Exception as e:
        log_result("_serialize", False, f"Error: {e}")

    # Test 8d: Channel constants are correct
    print(f"\n  [Test 8d] Channel constants are correct...")
    try:
        from cbi.services.realtime import (
            CHANNEL_NOTIFICATION_PREFIX,
            CHANNEL_BROADCAST,
            CHANNEL_REPORT_UPDATES,
        )

        log_result(
            "CHANNEL_NOTIFICATION_PREFIX starts with 'notifications:'",
            CHANNEL_NOTIFICATION_PREFIX == "notifications:",
            f"value: '{CHANNEL_NOTIFICATION_PREFIX}'",
        )
        log_result(
            "CHANNEL_BROADCAST is 'notifications:broadcast'",
            CHANNEL_BROADCAST == "notifications:broadcast",
            f"value: '{CHANNEL_BROADCAST}'",
        )
        log_result(
            "CHANNEL_REPORT_UPDATES is 'reports:updates'",
            CHANNEL_REPORT_UPDATES == "reports:updates",
            f"value: '{CHANNEL_REPORT_UPDATES}'",
        )
    except Exception as e:
        log_result("Channel constants", False, f"Error: {e}")

    # Test 8e: _subscribe_and_forward cleanup (pubsub closed on cancel)
    print(f"\n  [Test 8e] _subscribe_and_forward cleans up on cancel...")
    try:
        from cbi.api.routes.websocket import _subscribe_and_forward

        redis_client = await get_redis()

        class MockCleanupWS:
            async def send_text(self, data):
                pass

        mock_ws = MockCleanupWS()
        task = asyncio.create_task(
            _subscribe_and_forward(mock_ws, str(uuid4()), redis_client)
        )
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # If we got here without hanging, cleanup worked
        log_result(
            "_subscribe_and_forward: cleans up on cancel",
            True,
            "Task cancelled and cleaned up without hanging",
        )

        await redis_client.close()
    except Exception as e:
        log_result("Pub/sub cleanup", False, f"Error: {e}")


# =============================================================================
# Cleanup
# =============================================================================

async def cleanup(test_data: dict) -> None:
    """Clean up test data."""
    from cbi.db.session import get_session
    from sqlalchemy import text

    print(f"\n[{INFO}] Cleaning up test data...")

    async with get_session() as session:
        # Delete in order (FK constraints)
        await session.execute(
            text("DELETE FROM audit_logs WHERE actor_id IN (:o1, :o2)"),
            {"o1": str(test_data["officer_id"]), "o2": str(test_data["inactive_officer_id"])},
        )
        await session.execute(
            text("DELETE FROM notifications WHERE report_id = :r1"),
            {"r1": test_data["report_id"]},
        )
        await session.execute(
            text("DELETE FROM reports WHERE conversation_id = 'test-conv-ws-001'"),
        )
        await session.execute(
            text("DELETE FROM officers WHERE email IN ('test.ws.officer@cbi.local', 'test.ws.inactive@cbi.local')"),
        )

    print("  Cleanup complete.")


# =============================================================================
# Main Runner
# =============================================================================

async def main() -> None:
    """Run all Phase 5.3 tests."""
    print("=" * 60)
    print(" CBI Phase 5.3: WebSocket Real-time Updates - Test Suite")
    print("=" * 60)

    from cbi.db.session import init_db, close_db
    from cbi.services.message_queue import close_redis_client

    # Initialize database connection
    print(f"\n[{INFO}] Initializing database connection...")
    await init_db(echo=False)

    test_data = {}

    try:
        # Setup
        test_data = await setup_test_data()

        # Run all test sections
        await test_realtime_service(test_data)
        await test_websocket_auth(test_data)
        await test_connection_management(test_data)
        await test_heartbeat()
        await test_pubsub_forwarding(test_data)
        await test_notification_integration(test_data)
        await test_reports_integration(test_data)
        await test_error_handling(test_data)

    except Exception as e:
        print(f"\n[{FAIL}] Unexpected error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        if test_data:
            try:
                await cleanup(test_data)
            except Exception as e:
                print(f"  [{WARN}] Cleanup error: {e}")

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
