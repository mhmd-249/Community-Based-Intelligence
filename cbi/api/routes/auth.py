"""
Authentication API endpoints.

JWT-based authentication for health officers.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from passlib.context import CryptContext

from cbi.api.deps import CurrentOfficer, DB
from cbi.api.schemas import (
    LoginRequest,
    MessageResponse,
    OfficerResponse,
    OfficerUpdateRequest,
    PasswordChangeRequest,
    RefreshRequest,
    TokenResponse,
)
from cbi.config import get_logger, get_settings
from cbi.db.queries import get_officer_by_email

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(officer_id: str, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    expire = datetime.utcnow() + (
        expires_delta or timedelta(hours=settings.jwt_expiry_hours)
    )
    to_encode = {
        "sub": officer_id,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(
        to_encode,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: DB,
) -> TokenResponse:
    """
    Authenticate an officer and return JWT token.

    Args:
        request: Login credentials (email, password).
        db: Database session.

    Returns:
        JWT access token.

    Raises:
        HTTPException: If credentials are invalid.
    """
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

    access_token = create_access_token(str(officer.id))
    logger.info("Officer logged in", officer_id=str(officer.id))

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expiry_hours * 3600,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: DB,
) -> TokenResponse:
    """
    Refresh an access token.

    TODO: Implement proper refresh token logic
    - Validate refresh token
    - Issue new access token
    """
    # Placeholder - not fully implemented
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Token refresh not yet implemented",
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
