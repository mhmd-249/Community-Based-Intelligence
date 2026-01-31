"""
Real-time messaging service for CBI.

Publishes events to Redis pub/sub channels for WebSocket delivery
to connected dashboard clients.

Channel structure:
- notifications:{officer_id}  - Officer-specific notifications
- notifications:broadcast      - Broadcast to all connected officers
- reports:updates              - Report create/update events
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cbi.config import get_logger

logger = get_logger(__name__)

# Channel names
CHANNEL_NOTIFICATION_PREFIX = "notifications:"
CHANNEL_BROADCAST = "notifications:broadcast"
CHANNEL_REPORT_UPDATES = "reports:updates"


def _serialize(data: dict[str, Any]) -> str:
    """Serialize a message dict to JSON string."""
    return json.dumps(data, ensure_ascii=False, default=str)


class RealtimeService:
    """
    Publishes real-time events to Redis pub/sub channels.

    Requires an async Redis client. Obtain one from app.state.redis
    or from the message_queue module.
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def publish_notification(
        self,
        notification_data: dict[str, Any],
        officer_ids: list[str | UUID],
    ) -> int:
        """
        Publish a notification to each target officer's channel.

        Args:
            notification_data: Notification payload (id, title, urgency, etc.).
            officer_ids: List of officer UUIDs to notify.

        Returns:
            Total number of subscribers that received the message.
        """
        message = _serialize({
            "type": "notification",
            "data": notification_data,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        total_subscribers = 0
        for oid in officer_ids:
            channel = f"{CHANNEL_NOTIFICATION_PREFIX}{oid}"
            try:
                count = await self._redis.publish(channel, message)
                total_subscribers += count
            except Exception as e:
                logger.error(
                    "Failed to publish notification to officer channel",
                    officer_id=str(oid),
                    error=str(e),
                )

        logger.debug(
            "Published notification",
            notification_id=notification_data.get("id"),
            officer_count=len(officer_ids),
            subscribers=total_subscribers,
        )
        return total_subscribers

    async def publish_report_update(
        self,
        report_id: str | UUID,
        update_type: str,
        data: dict[str, Any] | None = None,
    ) -> int:
        """
        Publish a report update event.

        Args:
            report_id: ID of the updated report.
            update_type: Type of update (created, updated, status_change, note_added).
            data: Additional data about the update.

        Returns:
            Number of subscribers that received the message.
        """
        message = _serialize({
            "type": "report_update",
            "data": {
                "report_id": str(report_id),
                "update_type": update_type,
                **(data or {}),
            },
            "timestamp": datetime.now(UTC).isoformat(),
        })

        try:
            count = await self._redis.publish(CHANNEL_REPORT_UPDATES, message)
            logger.debug(
                "Published report update",
                report_id=str(report_id),
                update_type=update_type,
                subscribers=count,
            )
            return count
        except Exception as e:
            logger.error(
                "Failed to publish report update",
                report_id=str(report_id),
                error=str(e),
            )
            return 0

    async def broadcast(self, message_data: dict[str, Any]) -> int:
        """
        Broadcast a message to all connected officers.

        Args:
            message_data: Arbitrary payload to broadcast.

        Returns:
            Number of subscribers that received the message.
        """
        message = _serialize({
            "type": "broadcast",
            "data": message_data,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        try:
            count = await self._redis.publish(CHANNEL_BROADCAST, message)
            logger.debug("Broadcast message sent", subscribers=count)
            return count
        except Exception as e:
            logger.error("Failed to broadcast message", error=str(e))
            return 0
