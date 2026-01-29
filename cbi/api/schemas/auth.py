"""
Pydantic schemas for Authentication API.
"""

from datetime import datetime

from pydantic import EmailStr, Field

from cbi.api.schemas.base import CamelCaseModel, IDMixin


class LoginRequest(CamelCaseModel):
    """Login request with email and password."""

    email: EmailStr
    password: str = Field(..., min_length=6)


class TokenResponse(CamelCaseModel):
    """JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(CamelCaseModel):
    """Token refresh request."""

    refresh_token: str


class OfficerResponse(IDMixin):
    """Officer profile response."""

    email: str
    name: str
    phone: str | None
    region: str | None
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class LoginResponse(CamelCaseModel):
    """Login response with tokens and officer info."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    officer: OfficerResponse


class OfficerUpdateRequest(CamelCaseModel):
    """Request to update officer profile."""

    name: str | None = None
    phone: str | None = None
    region: str | None = None


class PasswordChangeRequest(CamelCaseModel):
    """Request to change password."""

    current_password: str
    new_password: str = Field(..., min_length=8)
