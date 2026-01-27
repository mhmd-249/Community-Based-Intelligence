"""
Health check endpoint for the CBI worker.

Provides an HTTP health endpoint for container orchestration (Kubernetes, ECS)
to determine if the worker is healthy and ready to process messages.
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any

from aiohttp import web

from cbi.config import get_logger, get_settings
from cbi.services.message_queue import get_queue_stats, get_redis_client

logger = get_logger(__name__)
settings = get_settings()

# Health check configuration
DEFAULT_PORT = 8081
REDIS_TIMEOUT = 5.0  # seconds


class HealthServer:
    """
    Simple HTTP server for health checks.

    Provides /health and /ready endpoints for container orchestration.
    """

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        worker_metrics_fn: Callable[[], dict] | None = None,
    ) -> None:
        """
        Initialize the health server.

        Args:
            port: Port to listen on
            worker_metrics_fn: Optional function to get worker metrics
        """
        self.port = port
        self.worker_metrics_fn = worker_metrics_fn
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._start_time = time.time()

    async def start(self) -> None:
        """Start the health server."""
        self._app = web.Application()
        self._app.router.add_get("/health", self._health_handler)
        self._app.router.add_get("/ready", self._ready_handler)
        self._app.router.add_get("/metrics", self._metrics_handler)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await self._site.start()

        logger.info("Health server started", port=self.port)

    async def stop(self) -> None:
        """Stop the health server."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        logger.info("Health server stopped")

    async def _health_handler(self, _request: web.Request) -> web.Response:
        """
        Liveness check endpoint.

        Returns 200 if the process is alive, 503 otherwise.
        Used by Kubernetes/ECS to determine if the container should be restarted.
        """
        return web.json_response(
            {
                "status": "healthy",
                "uptime_seconds": round(time.time() - self._start_time, 2),
            }
        )

    async def _ready_handler(self, _request: web.Request) -> web.Response:
        """
        Readiness check endpoint.

        Returns 200 if the worker is ready to process messages, 503 otherwise.
        Checks Redis connectivity and queue status.
        """
        checks: dict[str, Any] = {
            "redis": False,
            "queue": False,
        }

        try:
            # Check Redis connectivity
            client = await get_redis_client()
            pong = await asyncio.wait_for(client.ping(), timeout=REDIS_TIMEOUT)
            checks["redis"] = pong is True

            # Check queue status
            stats = await get_queue_stats()
            checks["queue"] = "error" not in stats

        except TimeoutError:
            logger.warning("Redis health check timeout")
        except Exception as e:
            logger.warning("Health check failed", error=str(e))

        # Determine overall status
        is_ready = all(checks.values())
        status_code = 200 if is_ready else 503

        return web.json_response(
            {
                "status": "ready" if is_ready else "not_ready",
                "checks": checks,
                "uptime_seconds": round(time.time() - self._start_time, 2),
            },
            status=status_code,
        )

    async def _metrics_handler(self, _request: web.Request) -> web.Response:
        """
        Metrics endpoint for monitoring.

        Returns worker and queue metrics in JSON format.
        """
        metrics: dict[str, Any] = {
            "uptime_seconds": round(time.time() - self._start_time, 2),
        }

        # Add worker metrics if available
        if self.worker_metrics_fn:
            try:
                metrics["worker"] = self.worker_metrics_fn()
            except Exception as e:
                logger.warning("Failed to get worker metrics", error=str(e))

        # Add queue metrics
        try:
            queue_stats = await get_queue_stats()
            metrics["queue"] = queue_stats
        except Exception as e:
            logger.warning("Failed to get queue metrics", error=str(e))
            metrics["queue"] = {"error": str(e)}

        return web.json_response(metrics)


async def run_health_server(
    port: int = DEFAULT_PORT,
    worker_metrics_fn: Callable[[], dict] | None = None,
) -> HealthServer:
    """
    Create and start a health server.

    Args:
        port: Port to listen on
        worker_metrics_fn: Optional function to get worker metrics

    Returns:
        Running HealthServer instance
    """
    server = HealthServer(port=port, worker_metrics_fn=worker_metrics_fn)
    await server.start()
    return server


# Standalone health server entry point
async def main() -> None:
    """Run the health server standalone (for testing)."""
    from cbi.config import configure_logging

    configure_logging(
        json_format=settings.is_production,
        log_level="DEBUG" if settings.debug else "INFO",
    )

    server = await run_health_server()

    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
