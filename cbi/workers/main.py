"""
CBI Worker - Background Message Processor

Consumes messages from Redis Streams and processes them through the agent pipeline.
"""

import asyncio
import signal
from typing import NoReturn

from cbi.config import configure_logging, get_settings, get_logger

settings = get_settings()
logger = get_logger(__name__)


class Worker:
    """Background worker for processing messages from Redis Streams."""

    def __init__(self) -> None:
        self._running = False

    async def start(self) -> None:
        """Start the worker loop."""
        self._running = True
        logger.info("Worker started", environment=settings.environment)

        while self._running:
            try:
                # TODO: Implement Redis Streams consumer
                # - Read from message queue
                # - Process through agent pipeline
                # - Update report status
                await asyncio.sleep(1)
            except Exception as e:
                logger.exception("Error processing message", error=str(e))
                await asyncio.sleep(5)

    def stop(self) -> None:
        """Stop the worker loop."""
        logger.info("Worker stopping...")
        self._running = False


async def main() -> NoReturn:
    """Main entry point for the worker."""
    configure_logging(
        json_format=settings.is_production,
        log_level="DEBUG" if settings.debug else "INFO",
    )

    worker = Worker()

    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop)

    await worker.start()


def run() -> None:
    """Run the worker."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
