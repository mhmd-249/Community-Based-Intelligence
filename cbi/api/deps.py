"""
FastAPI dependency injection.

Provides reusable dependencies for routes:
- Database sessions
- Redis connections
- Authentication
"""

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from cbi.config import get_settings
from cbi.db import get_session, Officer
from cbi.db.queries import get_officer_by_id

settings = get_settings()
security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that yields an async database session.

    Handles commit on success and rollback on error.

    Yields:
        AsyncSession instance.

    Example:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with get_session() as session:
        yield session


async def get_redis(request: Request) -> Redis:
    """
    Dependency that returns the Redis connection from app state.

    Args:
        request: FastAPI request object.

    Returns:
        Redis client instance.

    Raises:
        HTTPException: If Redis is not available.
    """
    redis: Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis connection not available",
        )
    return redis


async def get_current_officer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Officer:
    """
    Dependency that extracts and validates the current officer from JWT token.

    Args:
        credentials: Bearer token from Authorization header.
        db: Database session.

    Returns:
        Authenticated Officer instance.

    Raises:
        HTTPException: If token is missing, invalid, or officer not found.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        officer_id: str | None = payload.get("sub")
        if officer_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    officer = await get_officer_by_id(db, UUID(officer_id))
    if officer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Officer not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not officer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Officer account is deactivated",
        )

    return officer


async def get_optional_officer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Officer | None:
    """
    Dependency that optionally extracts the current officer.

    Returns None if no token provided, raises error only if token is invalid.

    Args:
        credentials: Bearer token from Authorization header.
        db: Database session.

    Returns:
        Officer instance or None.
    """
    if credentials is None:
        return None

    return await get_current_officer(credentials, db)


# Type aliases for cleaner route signatures
DB = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]
CurrentOfficer = Annotated[Officer, Depends(get_current_officer)]
OptionalOfficer = Annotated[Officer | None, Depends(get_optional_officer)]
