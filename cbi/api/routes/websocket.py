"""
WebSocket endpoint for real-time dashboard updates.

Authenticates officers via JWT query parameter, subscribes to
Redis pub/sub channels, and forwards messages to the WebSocket.
Implements heartbeat pings to detect stale connections.
"""

import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from uuid import UUID

from cbi.config import get_logger, get_settings
from cbi.db import get_session
from cbi.db.queries import get_officer_by_id
from cbi.services.auth import verify_token
from cbi.services.realtime import (
    CHANNEL_BROADCAST,
    CHANNEL_NOTIFICATION_PREFIX,
    CHANNEL_REPORT_UPDATES,
)

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 30

# Connected clients: officer_id -> set of WebSocket connections
_connected_clients: dict[str, set[WebSocket]] = {}


def _get_connected_count() -> int:
    """Return total number of active WebSocket connections."""
    return sum(len(sockets) for sockets in _connected_clients.values())


def _register(officer_id: str, ws: WebSocket) -> None:
    """Track a new WebSocket connection."""
    if officer_id not in _connected_clients:
        _connected_clients[officer_id] = set()
    _connected_clients[officer_id].add(ws)
    logger.info(
        "WebSocket connected",
        officer_id=officer_id,
        total_connections=_get_connected_count(),
    )


def _unregister(officer_id: str, ws: WebSocket) -> None:
    """Remove a WebSocket connection from tracking."""
    if officer_id in _connected_clients:
        _connected_clients[officer_id].discard(ws)
        if not _connected_clients[officer_id]:
            del _connected_clients[officer_id]
    logger.info(
        "WebSocket disconnected",
        officer_id=officer_id,
        total_connections=_get_connected_count(),
    )


async def _authenticate(token: str) -> tuple[str, str] | None:
    """
    Validate a JWT token and return (officer_id, role) or None.

    Uses a fresh DB session since WebSocket handlers don't get
    the normal FastAPI dependency injection for auth.
    """
    try:
        payload = verify_token(token)
    except JWTError:
        return None

    if payload.get("type") != "access":
        return None

    officer_id: str | None = payload.get("sub")
    if officer_id is None:
        return None

    # Verify officer exists and is active
    async with get_session() as session:
        officer = await get_officer_by_id(session, UUID(officer_id))
        if officer is None or not officer.is_active:
            return None

    return officer_id, payload.get("role", "officer")


async def _subscribe_and_forward(
    ws: WebSocket,
    officer_id: str,
    redis_client,
) -> None:
    """
    Subscribe to Redis pub/sub channels and forward messages to WebSocket.

    Runs until the WebSocket disconnects or an error occurs.
    Uses a dedicated Redis connection for pub/sub (required by Redis).
    """
    # Create a dedicated pub/sub connection (pub/sub requires its own connection)
    pubsub = redis_client.pubsub()

    channels = [
        f"{CHANNEL_NOTIFICATION_PREFIX}{officer_id}",
        CHANNEL_BROADCAST,
        CHANNEL_REPORT_UPDATES,
    ]

    try:
        await pubsub.subscribe(*channels)
        logger.debug(
            "Subscribed to channels",
            officer_id=officer_id,
            channels=channels,
        )

        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message and message["type"] == "message":
                data = message["data"]
                # data may be str or bytes depending on Redis config
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                await ws.send_text(data)
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.close()


async def _heartbeat(ws: WebSocket) -> None:
    """
    Send periodic ping frames to detect stale connections.

    WebSocket protocol pings keep the connection alive through
    proxies and load balancers, and detect disconnected clients.
    """
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            await ws.send_json({
                "type": "ping",
                "timestamp": asyncio.get_event_loop().time(),
            })
    except Exception:
        # Connection closed; task will be cancelled by the caller
        pass


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
) -> None:
    """
    WebSocket endpoint for real-time dashboard updates.

    Authentication is done via JWT token in query parameter.

    Subscribes the officer to:
    - notifications:{officer_id} - personal notifications
    - notifications:broadcast    - system-wide broadcasts
    - reports:updates            - report create/update events

    Message format (JSON):
    {
        "type": "notification" | "report_update" | "broadcast" | "ping",
        "data": {...},
        "timestamp": "ISO8601"
    }
    """
    # Authenticate before accepting
    auth_result = await _authenticate(token)
    if auth_result is None:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    officer_id, role = auth_result

    # Get Redis from app state
    redis_client = getattr(websocket.app.state, "redis", None)
    if redis_client is None:
        await websocket.close(code=4002, reason="Service unavailable")
        return

    await websocket.accept()
    _register(officer_id, websocket)

    # Send initial connection confirmation
    await websocket.send_json({
        "type": "connected",
        "data": {
            "officer_id": officer_id,
            "channels": [
                f"{CHANNEL_NOTIFICATION_PREFIX}{officer_id}",
                CHANNEL_BROADCAST,
                CHANNEL_REPORT_UPDATES,
            ],
        },
    })

    # Run pub/sub forwarding and heartbeat concurrently
    pubsub_task = asyncio.create_task(
        _subscribe_and_forward(websocket, officer_id, redis_client)
    )
    heartbeat_task = asyncio.create_task(_heartbeat(websocket))

    try:
        # Listen for client messages (pong responses, or explicit close)
        while True:
            data = await websocket.receive_text()
            # Handle client pong or other messages
            try:
                msg = json.loads(data)
                if msg.get("type") == "pong":
                    # Client responded to heartbeat; connection is alive
                    pass
            except (json.JSONDecodeError, TypeError):
                pass
    except WebSocketDisconnect:
        logger.debug("Client disconnected", officer_id=officer_id)
    except Exception as e:
        logger.error(
            "WebSocket error",
            officer_id=officer_id,
            error=str(e),
        )
    finally:
        pubsub_task.cancel()
        heartbeat_task.cancel()
        _unregister(officer_id, websocket)

        # Suppress CancelledError from tasks
        for task in (pubsub_task, heartbeat_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
