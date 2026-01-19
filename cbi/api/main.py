"""
CBI API - FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cbi.config import configure_logging, get_settings, get_logger
from cbi.db import init_db, close_db, health_check as db_health_check

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
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

    yield

    # Shutdown
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


@app.get("/health")
async def health_check() -> dict[str, str | bool]:
    """Health check endpoint for Docker and load balancers."""
    db_ok = await db_health_check()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": db_ok,
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
