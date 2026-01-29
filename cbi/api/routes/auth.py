"""
Authentication API endpoints.

JWT-based authentication for health officers with access and refresh tokens.
Includes rate limiting on login and refresh token blacklisting via Redis.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from jose import ExpiredSignatureError, JWTError

from cbi.api.deps import CurrentOfficer, DB, RedisClient
from cbi.api.schemas import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    OfficerResponse,
    OfficerUpdateRequest,
    PasswordChangeRequest,
    RefreshRequest,
    TokenResponse,
)
from cbi.config import get_logger, get_settings
from cbi.db.queries import get_officer_by_email, get_officer_by_id
from cbi.services.auth import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    is_token_blacklisted,
    verify_password,
    verify_token,
)

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()

# Redis key prefix for login rate limiting
RATE_LIMIT_PREFIX = "rate:login:"


async def _check_login_rate_limit(redis, request: Request) -> None:
    """
    Enforce login rate limiting: max attempts per minute per IP.

    Args:
        redis: Async Redis client.
        request: FastAPI request (for client IP).

    Raises:
        HTTPException: 429 if rate limit exceeded.
    """
    if redis is None:
        return

    client_ip = request.client.host if request.client else "unknown"
    key = f"{RATE_LIMIT_PREFIX}{client_ip}"

    current = await redis.get(key)
    if current is not None and int(current) >= settings.login_rate_limit:
        logger.warning("Login rate limit exceeded", client_ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(settings.login_rate_limit_window)},
        )

    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, settings.login_rate_limit_window)
    await pipe.execute()


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    raw_request: Request,
    db: DB,
    redis: RedisClient,
) -> LoginResponse:
    """
    Authenticate an officer and return access + refresh tokens.

    Args:
        request: Login credentials (email, password).
        raw_request: FastAPI request for rate limiting.
        db: Database session.
        redis: Redis client for rate limiting.

    Returns:
        Access token, refresh token, and officer profile.

    Raises:
        HTTPException: 401 if credentials invalid, 403 if account inactive,
                       429 if rate limit exceeded.
    """
    await _check_login_rate_limit(redis, raw_request)

    officer = await get_officer_by_email(db, request.email)

    if officer is None or not verify_password(request.password, officer.password_hash):
        logger.warning("Failed login attempt", email=request.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not officer.is_active:
        logger.warning("Login attempt for inactive officer", email=request.email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # Update last login
    officer.last_login_at = datetime.utcnow()
    await db.commit()

    access_token = create_access_token(officer.id, officer.role)
    refresh_token = create_refresh_token(officer.id)
    logger.info("Officer logged in", officer_id=str(officer.id))

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_expiry_hours * 3600,
        officer=OfficerResponse(
            id=officer.id,
            email=officer.email,
            name=officer.name,
            phone=officer.phone,
            region=officer.region,
            role=officer.role,
            is_active=officer.is_active,
            last_login_at=officer.last_login_at,
            created_at=officer.created_at,
        ),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: DB,
    redis: RedisClient,
) -> TokenResponse:
    """
    Issue a new access token using a valid refresh token.

    Args:
        request: Refresh token.
        db: Database session.
        redis: Redis client for blacklist checking.

    Returns:
        New access token and the same refresh token.

    Raises:
        HTTPException: 401 if refresh token is invalid, expired, or blacklisted.
    """
    token = request.refresh_token

    # Check blacklist
    if await is_token_blacklisted(redis, token):
        logger.warning("Blacklisted refresh token used")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    try:
        payload = verify_token(token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    officer_id = payload.get("sub")
    if officer_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Verify officer still exists and is active
    from uuid import UUID

    officer = await get_officer_by_id(db, UUID(officer_id))
    if officer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Officer not found",
        )

    if not officer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    new_access_token = create_access_token(officer.id, officer.role)
    logger.info("Token refreshed", officer_id=str(officer.id))

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expiry_hours * 3600,
    )


@router.get("/me", response_model=OfficerResponse)
async def get_current_user(
    officer: CurrentOfficer,
) -> OfficerResponse:
    """
    Get the current authenticated officer's profile.

    Args:
        officer: Current authenticated officer.

    Returns:
        Officer profile data.
    """
    return OfficerResponse(
        id=officer.id,
        email=officer.email,
        name=officer.name,
        phone=officer.phone,
        region=officer.region,
        role=officer.role,
        is_active=officer.is_active,
        last_login_at=officer.last_login_at,
        created_at=officer.created_at,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: RefreshRequest,
    officer: CurrentOfficer,
    redis: RedisClient,
) -> MessageResponse:
    """
    Logout by blacklisting the refresh token in Redis.

    The blacklist entry has the same TTL as the token's remaining lifetime,
    so entries auto-expire and don't accumulate.

    Args:
        request: Refresh token to invalidate.
        officer: Current authenticated officer (ensures caller is authenticated).
        redis: Redis client for blacklist storage.

    Returns:
        Success message.
    """
    token = request.refresh_token

    try:
        payload = verify_token(token)
    except (ExpiredSignatureError, JWTError):
        # Token already invalid, nothing to blacklist
        return MessageResponse(message="Logged out successfully")

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expected a refresh token",
        )

    # Calculate remaining TTL for the blacklist entry
    exp = payload.get("exp", 0)
    remaining = max(int(exp - datetime.utcnow().timestamp()), 0)

    if remaining > 0:
        await blacklist_token(redis, token, remaining)

    logger.info("Officer logged out", officer_id=str(officer.id))
    return MessageResponse(message="Logged out successfully")


@router.patch("/me", response_model=OfficerResponse)
async def update_current_user(
    update: OfficerUpdateRequest,
    officer: CurrentOfficer,
    db: DB,
) -> OfficerResponse:
    """
    Update the current officer's profile.

    TODO: Implement in Phase 2
    - Apply updates
    - Create audit log entry
    """
    logger.info("Updating officer profile", officer_id=str(officer.id))

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Profile update not yet implemented",
    )


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    request: PasswordChangeRequest,
    officer: CurrentOfficer,
    db: DB,
) -> MessageResponse:
    """
    Change the current officer's password.

    TODO: Implement in Phase 2
    - Verify current password
    - Hash new password
    - Update officer record
    - Create audit log entry
    """
    logger.info("Password change requested", officer_id=str(officer.id))

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Password change not yet implemented",
    )
