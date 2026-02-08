"""
CBI Worker - Background Message Processor

Consumes messages from Redis Streams and processes them through the
LangGraph agent pipeline for health incident reporting.
"""

import asyncio
import os
import signal
import time
import uuid
from typing import NoReturn

from cbi.agents.graph import get_graph, reset_graph
from cbi.agents.state import (
    ConversationState,
    MessageRole,
    add_message_to_state,
)
from cbi.config import configure_logging, get_logger, get_settings
from cbi.db import close_db, init_db
from cbi.services.message_queue import (
    acknowledge_message,
    close_redis_client,
    consume_messages,
    ensure_consumer_group,
    get_pending_count,
    get_queue_stats,
)
from cbi.services.messaging import IncomingMessage
from cbi.services.state import (
    StateService,
    StateServiceError,
    close_state_service,
    get_state_service,
)

settings = get_settings()
logger = get_logger(__name__)

# Worker configuration
DEFAULT_BATCH_SIZE = 10
DEFAULT_BLOCK_MS = 5000  # 5 seconds
PROCESSING_TIMEOUT = 60  # 60 seconds max per message
METRICS_LOG_INTERVAL = 60  # Log metrics every 60 seconds


class WorkerMetrics:
    """Track worker performance metrics."""

    def __init__(self) -> None:
        self.messages_processed = 0
        self.messages_failed = 0
        self.total_processing_time = 0.0
        self.start_time = time.time()
        self.last_metrics_log = time.time()

    def record_success(self, duration: float) -> None:
        """Record a successful message processing."""
        self.messages_processed += 1
        self.total_processing_time += duration

    def record_failure(self) -> None:
        """Record a failed message processing."""
        self.messages_failed += 1

    @property
    def average_processing_time(self) -> float:
        """Get average processing time in seconds."""
        if self.messages_processed == 0:
            return 0.0
        return self.total_processing_time / self.messages_processed

    @property
    def uptime(self) -> float:
        """Get worker uptime in seconds."""
        return time.time() - self.start_time

    def to_dict(self) -> dict:
        """Convert metrics to dictionary."""
        return {
            "messages_processed": self.messages_processed,
            "messages_failed": self.messages_failed,
            "average_processing_time_ms": round(self.average_processing_time * 1000, 2),
            "uptime_seconds": round(self.uptime, 2),
            "success_rate": (
                round(
                    self.messages_processed
                    / (self.messages_processed + self.messages_failed)
                    * 100,
                    2,
                )
                if (self.messages_processed + self.messages_failed) > 0
                else 100.0
            ),
        }

    def should_log_metrics(self) -> bool:
        """Check if it's time to log metrics."""
        now = time.time()
        if now - self.last_metrics_log >= METRICS_LOG_INTERVAL:
            self.last_metrics_log = now
            return True
        return False


class Worker:
    """
    Background worker for processing messages from Redis Streams.

    Consumes incoming messages, processes them through the LangGraph
    agent pipeline, and manages conversation state.
    """

    def __init__(
        self,
        worker_id: str | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        block_ms: int = DEFAULT_BLOCK_MS,
    ) -> None:
        """
        Initialize the worker.

        Args:
            worker_id: Unique identifier for this worker instance.
                      Defaults to hostname + random suffix.
            batch_size: Maximum messages to fetch per iteration.
            block_ms: How long to block waiting for messages.
        """
        self.worker_id = worker_id or self._generate_worker_id()
        self.batch_size = batch_size
        self.block_ms = block_ms
        self._running = False
        self._current_message: str | None = None
        self._state_service: StateService | None = None
        self._metrics = WorkerMetrics()

    @staticmethod
    def _generate_worker_id() -> str:
        """Generate a unique worker ID."""
        hostname = os.environ.get("HOSTNAME", "worker")
        suffix = uuid.uuid4().hex[:8]
        return f"{hostname}-{suffix}"

    async def initialize(self) -> None:
        """Initialize worker connections and resources."""
        logger.info(
            "Initializing worker",
            worker_id=self.worker_id,
            batch_size=self.batch_size,
        )

        # Initialize database
        await init_db(pool_size=3, max_overflow=5)

        # Initialize state service
        self._state_service = await get_state_service()

        # Ensure consumer group exists
        await ensure_consumer_group()

        # Initialize the graph
        get_graph()

        logger.info("Worker initialized", worker_id=self.worker_id)

    async def shutdown(self) -> None:
        """Clean up worker resources."""
        logger.info("Shutting down worker", worker_id=self.worker_id)

        # Close state service
        await close_state_service()

        # Close Redis connections
        await close_redis_client()

        # Close database connections
        await close_db()

        # Reset graph singleton
        reset_graph()

        logger.info(
            "Worker shutdown complete",
            worker_id=self.worker_id,
            metrics=self._metrics.to_dict(),
        )

    async def process_message(self, message: IncomingMessage) -> ConversationState:
        """
        Process a single incoming message through the agent pipeline.

        Args:
            message: The incoming message to process

        Returns:
            The final conversation state after processing

        Raises:
            StateServiceError: If state operations fail
            Exception: If graph processing fails
        """
        start_time = time.time()

        logger.info(
            "Processing message",
            worker_id=self.worker_id,
            platform=message.platform,
            chat_id=message.chat_id,
            message_id=message.message_id,
        )

        # Get or create conversation state
        state, is_new = await self._state_service.get_or_create_conversation(
            platform=message.platform,
            phone=message.chat_id,  # chat_id is the phone number for our purposes
        )

        if is_new:
            logger.info(
                "New conversation started",
                conversation_id=state["conversation_id"],
                platform=message.platform,
            )

        # Add user message to state
        state = add_message_to_state(
            state,
            MessageRole.user,
            message.text or "",
            message_id=message.message_id,
        )

        # Get the compiled graph
        graph = get_graph()

        # Run the graph with timeout
        try:
            result = await asyncio.wait_for(
                graph.ainvoke(
                    state,
                    {"configurable": {"thread_id": state["conversation_id"]}},
                ),
                timeout=PROCESSING_TIMEOUT,
            )
        except TimeoutError:
            logger.error(
                "Graph processing timeout",
                conversation_id=state["conversation_id"],
                timeout=PROCESSING_TIMEOUT,
            )
            raise

        # Save the final state
        await self._state_service.save_state(result)

        # Calculate processing duration
        duration = time.time() - start_time

        logger.info(
            "Message processed",
            worker_id=self.worker_id,
            conversation_id=result["conversation_id"],
            mode=result.get("current_mode"),
            turn_count=result.get("turn_count"),
            duration_ms=round(duration * 1000, 2),
            data_completeness=result.get("classification", {}).get(
                "data_completeness", 0
            ),
        )

        return result

    async def start(self) -> None:
        """
        Start the worker loop.

        Continuously consumes messages from Redis Streams and processes
        them through the agent pipeline.
        """
        self._running = True

        logger.info(
            "Worker started",
            worker_id=self.worker_id,
            environment=settings.environment,
        )

        try:
            async for entry_id, message in consume_messages(
                consumer_name=self.worker_id,
                batch_size=self.batch_size,
                block_ms=self.block_ms,
            ):
                if not self._running:
                    logger.info("Worker stopping, finishing current batch")
                    break

                self._current_message = entry_id
                start_time = time.time()

                try:
                    # Process the message
                    await self.process_message(message)

                    # Acknowledge successful processing
                    await acknowledge_message(entry_id)

                    # Record metrics
                    duration = time.time() - start_time
                    self._metrics.record_success(duration)

                except StateServiceError as e:
                    logger.error(
                        "State service error processing message",
                        worker_id=self.worker_id,
                        entry_id=entry_id,
                        error=str(e),
                    )
                    self._metrics.record_failure()
                    # Don't acknowledge - message will be retried

                except TimeoutError:
                    logger.error(
                        "Timeout processing message",
                        worker_id=self.worker_id,
                        entry_id=entry_id,
                    )
                    self._metrics.record_failure()
                    # Don't acknowledge - message will be retried

                except Exception as e:
                    logger.exception(
                        "Error processing message",
                        worker_id=self.worker_id,
                        entry_id=entry_id,
                        error=str(e),
                    )
                    self._metrics.record_failure()
                    # Don't acknowledge - message will be retried

                finally:
                    self._current_message = None

                # Periodically log metrics
                if self._metrics.should_log_metrics():
                    await self._log_metrics()

        except Exception as e:
            logger.exception(
                "Fatal error in worker loop",
                worker_id=self.worker_id,
                error=str(e),
            )
            raise

        logger.info(
            "Worker loop ended",
            worker_id=self.worker_id,
            metrics=self._metrics.to_dict(),
        )

    def stop(self) -> None:
        """
        Signal the worker to stop.

        The worker will finish processing the current message before stopping.
        """
        logger.info(
            "Worker stop requested",
            worker_id=self.worker_id,
            current_message=self._current_message,
        )
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if the worker is running."""
        return self._running

    @property
    def metrics(self) -> dict:
        """Get current worker metrics."""
        return self._metrics.to_dict()

    async def _log_metrics(self) -> None:
        """Log current metrics and queue stats."""
        try:
            queue_stats = await get_queue_stats()
            pending = await get_pending_count()

            logger.info(
                "Worker metrics",
                worker_id=self.worker_id,
                metrics=self._metrics.to_dict(),
                queue_length=queue_stats.get("stream_length", 0),
                pending_messages=pending,
                active_consumers=queue_stats.get("consumer_count", 0),
            )
        except Exception as e:
            logger.warning(
                "Failed to log metrics",
                worker_id=self.worker_id,
                error=str(e),
            )


async def main() -> NoReturn:
    """Main entry point for the worker."""
    configure_logging(
        json_format=settings.is_production,
        log_level="DEBUG" if settings.debug else "INFO",
    )

    worker = Worker()

    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        worker.stop()
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        # Initialize the worker
        await worker.initialize()

        # Start processing
        await worker.start()

    except Exception as e:
        logger.exception("Worker failed", error=str(e))
        raise

    finally:
        # Clean shutdown
        await worker.shutdown()


def run() -> None:
    """Run the worker."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
