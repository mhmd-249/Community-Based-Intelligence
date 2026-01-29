"""
Authentication service for CBI.

Handles password hashing, JWT token creation/verification,
and refresh token blacklisting via Redis.
"""

from datetime import datetime, timedelta
from uuid import UUID

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from cbi.config import get_logger, get_settings

logger = get_logger(__name__)
settings = get_settings()

# Bcrypt password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Redis key prefix for blacklisted refresh tokens
BLACKLIST_PREFIX = "token:blacklist:"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def create_access_token(officer_id: str | UUID, role: str = "officer") -> str:
    """
    Create a JWT access token.

    Args:
        officer_id: Officer UUID (converted to string).
        role: Officer role for authorization checks.

    Returns:
        Encoded JWT string with 24-hour expiry.
    """
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiry_hours)
    payload = {
        "sub": str(officer_id),
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(officer_id: str | UUID) -> str:
    """
    Create a JWT refresh token.

    Args:
        officer_id: Officer UUID (converted to string).

    Returns:
        Encoded JWT string with 7-day expiry.
    """
    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_expiry_days)
    payload = {
        "sub": str(officer_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def verify_token(token: str) -> dict:
    """
    Decode and verify a JWT token.

    Args:
        token: Encoded JWT string.

    Returns:
        Decoded payload dict with 'sub', 'type', 'exp', etc.

    Raises:
        ExpiredSignatureError: If the token has expired.
        JWTError: If the token is invalid or malformed.
    """
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )


async def is_token_blacklisted(redis_client, token: str) -> bool:
    """
    Check if a refresh token has been blacklisted (logged out).

    Args:
        redis_client: Async Redis client.
        token: The refresh token to check.

    Returns:
        True if the token is blacklisted.
    """
    if redis_client is None:
        return False
    result = await redis_client.get(f"{BLACKLIST_PREFIX}{token}")
    return result is not None


async def blacklist_token(redis_client, token: str, expires_in: int) -> None:
    """
    Add a refresh token to the blacklist in Redis.

    The blacklist entry expires when the token would have expired,
    so we don't accumulate stale entries.

    Args:
        redis_client: Async Redis client.
        token: The refresh token to blacklist.
        expires_in: Seconds until the token expires (TTL for the blacklist entry).
    """
    if redis_client is None:
        logger.warning("Redis unavailable, cannot blacklist token")
        return
    await redis_client.setex(
        f"{BLACKLIST_PREFIX}{token}",
        expires_in,
        "1",
    )
