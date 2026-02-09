"""
CBI API - FastAPI Application Entry Point

Community Based Intelligence - Multi-Agent Health Surveillance System
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers
from cbi.api.routes import analytics, auth, notifications, reports, webhook, webhooks, websocket
from cbi.config import configure_logging, get_logger, get_settings
from cbi.db import close_db, init_db
from cbi.db import health_check as db_health_check
from cbi.services.messaging import close_all_gateways

settings = get_settings()
logger = get_logger(__name__)

# Redis client (initialized in lifespan)
redis_client = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    global redis_client

    # Startup
    configure_logging(
        json_format=settings.is_production,
        log_level="DEBUG" if settings.debug else "INFO",
    )
    logger.info(
        "Starting CBI API",
        environment=settings.environment,
        version=settings.app_version,
    )

    # Initialize database
    await init_db(
        pool_size=5,
        max_overflow=10,
        echo=settings.debug,
    )
    logger.info("Database connection established")

    # Initialize Redis
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(
        settings.redis_url.get_secret_value(),
        encoding="utf-8",
        decode_responses=True,
    )
    logger.info("Redis connection established")

    # Store in app state for access in dependencies
    app.state.redis = redis_client

    # Backfill geocoding for existing reports missing location_point
    try:
        from cbi.db.queries import backfill_report_locations
        from cbi.db.session import get_session

        async with get_session() as session:
            updated = await backfill_report_locations(session)
            await session.commit()
            if updated:
                logger.info("Backfilled report locations", count=updated)
    except Exception as e:
        logger.warning("Location backfill failed (non-fatal)", error=str(e))

    yield

    # Shutdown
    await close_all_gateways()
    logger.info("Messaging gateways closed")

    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")

    await close_db()
    logger.info("Shutting down CBI API")


app = FastAPI(
    title=settings.app_name,
    description="Community Based Intelligence - Multi-Agent Health Surveillance System",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(
    notifications.router, prefix="/api/notifications", tags=["Notifications"]
)
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhooks (legacy)"])
app.include_router(webhooks.router, tags=["Webhooks"])
app.include_router(websocket.router, tags=["WebSocket"])


@app.get("/health")
async def health_check() -> dict[str, str | bool]:
    """Health check endpoint for Docker and load balancers."""
    db_ok = await db_health_check()

    # Check Redis
    redis_ok = False
    try:
        if app.state.redis:
            await app.state.redis.ping()
            redis_ok = True
    except Exception:
        pass

    all_ok = db_ok and redis_ok
    return {
        "status": "healthy" if all_ok else "degraded",
        "version": settings.app_version,
        "database": db_ok,
        "redis": redis_ok,
    }


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


def run() -> None:
    """Run the application with uvicorn."""
    import uvicorn

    uvicorn.run(
        "cbi.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        workers=1 if settings.is_development else settings.workers,
    )


if __name__ == "__main__":
    run()
