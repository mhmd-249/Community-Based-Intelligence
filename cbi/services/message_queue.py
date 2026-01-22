"""
Redis Stream-based message queue for incoming messages.

Provides reliable message queuing with consumer groups for
processing incoming messages from Telegram and WhatsApp.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

from cbi.config import get_logger, get_settings
from cbi.services.messaging import IncomingMessage

logger = get_logger(__name__)

# Stream and consumer group names
INCOMING_MESSAGES_STREAM = "cbi:messages:incoming"
CONSUMER_GROUP = "cbi:workers"
CONSUMER_NAME_PREFIX = "worker"

# Redis client singleton
_redis_client: aioredis.Redis | None = None


async def get_redis_client() -> aioredis.Redis:
    """
    Get or create the Redis client singleton.

    Returns:
        Redis client instance
    """
    global _redis_client

    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url.get_secret_value(),
            encoding="utf-8",
            decode_responses=True,
        )

    return _redis_client


async def set_redis_client(client: aioredis.Redis) -> None:
    """
    Set the Redis client (used for dependency injection in FastAPI).

    Args:
        client: Pre-configured Redis client
    """
    global _redis_client
    _redis_client = client


async def close_redis_client() -> None:
    """Close the Redis client if we own it."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def ensure_consumer_group() -> None:
    """
    Ensure the consumer group exists for the incoming messages stream.

    Creates the stream and consumer group if they don't exist.
    """
    client = await get_redis_client()

    try:
        # Try to create the consumer group
        # This will fail if the group already exists, which is fine
        await client.xgroup_create(
            INCOMING_MESSAGES_STREAM,
            CONSUMER_GROUP,
            id="0",  # Start from beginning
            mkstream=True,  # Create stream if it doesn't exist
        )
        logger.info(
            "Created consumer group",
            stream=INCOMING_MESSAGES_STREAM,
            group=CONSUMER_GROUP,
        )
    except aioredis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            # Consumer group already exists, that's fine
            pass
        else:
            raise


async def queue_incoming_message(message: IncomingMessage) -> str:
    """
    Add an incoming message to the Redis Stream for processing.

    Args:
        message: The incoming message to queue

    Returns:
        The stream entry ID

    Example:
        >>> msg = IncomingMessage(...)
        >>> entry_id = await queue_incoming_message(msg)
        >>> print(f"Queued with ID: {entry_id}")
    """
    client = await get_redis_client()

    # Convert message to dict for storage
    # We need to handle datetime serialization
    message_data = {
        "platform": message.platform,
        "message_id": message.message_id,
        "chat_id": message.chat_id,
        "from_id": message.from_id,
        "text": message.text or "",
        "timestamp": message.timestamp.isoformat(),
        "reply_to_id": message.reply_to_id or "",
        "queued_at": datetime.now(UTC).isoformat(),
    }

    # Add to stream
    entry_id = await client.xadd(
        INCOMING_MESSAGES_STREAM,
        message_data,
        maxlen=10000,  # Keep last 10k messages
    )

    logger.debug(
        "Queued incoming message",
        entry_id=entry_id,
        platform=message.platform,
        chat_id=message.chat_id,
    )

    return entry_id


def _parse_stream_message(
    entry_id: str,
    data: dict[str, str],
) -> tuple[str, IncomingMessage]:
    """
    Parse a Redis Stream entry into an IncomingMessage.

    Args:
        entry_id: The stream entry ID
        data: The message data from Redis

    Returns:
        Tuple of (entry_id, IncomingMessage)
    """
    timestamp = datetime.fromisoformat(data["timestamp"])

    message = IncomingMessage(
        platform=data["platform"],
        message_id=data["message_id"],
        chat_id=data["chat_id"],
        from_id=data["from_id"],
        text=data["text"] if data["text"] else None,
        timestamp=timestamp,
        reply_to_id=data["reply_to_id"] if data["reply_to_id"] else None,
    )

    return entry_id, message


async def consume_messages(
    consumer_name: str,
    batch_size: int = 10,
    block_ms: int = 5000,
) -> AsyncGenerator[tuple[str, IncomingMessage], None]:
    """
    Consume messages from the Redis Stream using consumer groups.

    This generator yields messages that need to be processed.
    Messages must be acknowledged after successful processing.

    Args:
        consumer_name: Unique name for this consumer
        batch_size: Maximum messages to fetch per iteration
        block_ms: How long to block waiting for messages (milliseconds)

    Yields:
        Tuple of (entry_id, IncomingMessage)

    Example:
        >>> async for entry_id, message in consume_messages("worker-1"):
        ...     process_message(message)
        ...     await acknowledge_message(entry_id)
    """
    client = await get_redis_client()
    await ensure_consumer_group()

    logger.info(
        "Starting message consumer",
        consumer=consumer_name,
        group=CONSUMER_GROUP,
        stream=INCOMING_MESSAGES_STREAM,
    )

    while True:
        try:
            # First, check for pending messages (failed/unacknowledged)
            pending = await client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=consumer_name,
                streams={INCOMING_MESSAGES_STREAM: "0"},  # "0" = pending messages
                count=batch_size,
                block=None,  # Don't block for pending
            )

            # Process pending messages first
            if pending:
                for _stream_name, messages in pending:
                    for entry_id, data in messages:
                        if data:  # Skip if message was deleted
                            yield _parse_stream_message(entry_id, data)

            # Then read new messages
            new_messages = await client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=consumer_name,
                streams={INCOMING_MESSAGES_STREAM: ">"},  # ">" = new messages only
                count=batch_size,
                block=block_ms,
            )

            if new_messages:
                for _stream_name, messages in new_messages:
                    for entry_id, data in messages:
                        yield _parse_stream_message(entry_id, data)

        except aioredis.ConnectionError as e:
            logger.error("Redis connection error in consumer", error=str(e))
            # Wait a bit before retrying
            import asyncio

            await asyncio.sleep(1)
        except Exception as e:
            logger.exception("Error consuming messages", error=str(e))
            import asyncio

            await asyncio.sleep(1)


async def acknowledge_message(entry_id: str) -> bool:
    """
    Acknowledge a message as successfully processed.

    This removes it from the pending entries list.

    Args:
        entry_id: The stream entry ID to acknowledge

    Returns:
        True if acknowledged, False if already acknowledged
    """
    client = await get_redis_client()

    result = await client.xack(
        INCOMING_MESSAGES_STREAM,
        CONSUMER_GROUP,
        entry_id,
    )

    if result:
        logger.debug("Acknowledged message", entry_id=entry_id)

    return result > 0


async def get_pending_count() -> int:
    """
    Get the count of pending (unacknowledged) messages.

    Returns:
        Number of pending messages
    """
    client = await get_redis_client()

    try:
        info = await client.xpending(INCOMING_MESSAGES_STREAM, CONSUMER_GROUP)
        return info.get("pending", 0) if info else 0
    except Exception:
        return 0


async def get_stream_length() -> int:
    """
    Get the total number of messages in the stream.

    Returns:
        Number of messages in stream
    """
    client = await get_redis_client()

    try:
        return await client.xlen(INCOMING_MESSAGES_STREAM)
    except Exception:
        return 0


async def get_queue_stats() -> dict[str, Any]:
    """
    Get statistics about the message queue.

    Returns:
        Dictionary with queue statistics
    """
    client = await get_redis_client()

    try:
        stream_length = await client.xlen(INCOMING_MESSAGES_STREAM)

        # Get pending info
        pending_info = await client.xpending(INCOMING_MESSAGES_STREAM, CONSUMER_GROUP)
        pending_count = pending_info.get("pending", 0) if pending_info else 0

        # Get consumer info
        consumers = await client.xinfo_consumers(
            INCOMING_MESSAGES_STREAM,
            CONSUMER_GROUP,
        )

        return {
            "stream_length": stream_length,
            "pending_count": pending_count,
            "consumer_count": len(consumers) if consumers else 0,
            "consumers": [
                {
                    "name": c.get("name"),
                    "pending": c.get("pending"),
                    "idle": c.get("idle"),
                }
                for c in (consumers or [])
            ],
        }
    except aioredis.ResponseError:
        # Stream or group might not exist yet
        return {
            "stream_length": 0,
            "pending_count": 0,
            "consumer_count": 0,
            "consumers": [],
        }
    except Exception as e:
        logger.error("Error getting queue stats", error=str(e))
        return {"error": str(e)}
