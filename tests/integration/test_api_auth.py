"""
Integration tests for authentication API endpoints.

Tests login, token refresh, protected endpoints, and rate limiting.
"""

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio(loop_scope="session")

from cbi.config.settings import get_settings
from cbi.db.models import Officer
from cbi.services.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
)


# =============================================================================
# TestLogin
# =============================================================================


class TestLogin:
    """Tests for POST /api/auth/login."""

    @pytest.mark.asyncio
    async def test_valid_credentials(self, app_client, test_officer):
        """Valid email + password → access token, refresh token, officer profile."""
        resp = await app_client.post(
            "/api/auth/login",
            json={"email": "test.officer@cbi.example.com", "password": "testpassword123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "accessToken" in data
        assert "refreshToken" in data
        assert data["tokenType"] == "bearer"
        assert data["officer"]["email"] == "test.officer@cbi.example.com"
        assert data["officer"]["role"] == "admin"

    @pytest.mark.asyncio
    async def test_invalid_password(self, app_client, test_officer):
        """Wrong password → 401."""
        resp = await app_client.post(
            "/api/auth/login",
            json={"email": "test.officer@cbi.example.com", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_nonexistent_email(self, app_client, test_officer):
        """Non-existent email → 401."""
        resp = await app_client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "whatever123"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_officer(self, app_client, db_session):
        """Inactive officer → 403 'deactivated'."""
        inactive = Officer(
            id=uuid.uuid4(),
            email="inactive@cbi.example.com",
            password_hash=hash_password("testpassword123"),
            name="Inactive Officer",
            role="officer",
            is_active=False,
        )
        db_session.add(inactive)
        await db_session.commit()

        resp = await app_client.post(
            "/api/auth/login",
            json={"email": "inactive@cbi.example.com", "password": "testpassword123"},
        )
        assert resp.status_code == 403
        assert "deactivated" in resp.json()["detail"].lower()


# =============================================================================
# TestTokenRefresh
# =============================================================================


class TestTokenRefresh:
    """Tests for POST /api/auth/refresh."""

    @pytest.mark.asyncio
    async def test_valid_refresh(self, app_client, test_officer):
        """Valid refresh token → new access token."""
        refresh = create_refresh_token(test_officer.id)
        resp = await app_client.post(
            "/api/auth/refresh",
            json={"refreshToken": refresh},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "accessToken" in data
        assert data["refreshToken"] == refresh

    @pytest.mark.asyncio
    async def test_invalid_token(self, app_client, test_officer):
        """Invalid token → 401."""
        resp = await app_client.post(
            "/api/auth/refresh",
            json={"refreshToken": "not.a.valid.token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_access_token_rejected(self, app_client, test_officer):
        """Using access token for refresh → 401 'Invalid token type'."""
        access = create_access_token(test_officer.id, test_officer.role)
        resp = await app_client.post(
            "/api/auth/refresh",
            json={"refreshToken": access},
        )
        assert resp.status_code == 401
        assert "token type" in resp.json()["detail"].lower()


# =============================================================================
# TestProtectedEndpoints
# =============================================================================


class TestProtectedEndpoints:
    """Tests for authentication-protected endpoints."""

    @pytest.mark.asyncio
    async def test_get_me(self, app_client, test_officer, auth_headers):
        """GET /api/auth/me → officer profile."""
        resp = await app_client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "test.officer@cbi.example.com"
        assert data["name"] == "Test Officer"

    @pytest.mark.asyncio
    async def test_unauthenticated(self, app_client, test_officer):
        """No token → 401."""
        resp = await app_client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token(self, app_client, test_officer):
        """Expired JWT → 401."""
        settings = get_settings()
        payload = {
            "sub": str(test_officer.id),
            "role": "admin",
            "type": "access",
            "exp": datetime.utcnow() - timedelta(hours=1),
            "iat": datetime.utcnow() - timedelta(hours=25),
        }
        expired_token = jwt.encode(
            payload,
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
        resp = await app_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401


# =============================================================================
# TestRateLimiting
# =============================================================================


class TestRateLimiting:
    """Tests for login rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, app_client, test_officer, test_redis):
        """6 failed login attempts → 429."""
        for i in range(6):
            resp = await app_client.post(
                "/api/auth/login",
                json={"email": "test.officer@cbi.example.com", "password": "wrongpass"},
            )
            if resp.status_code == 429:
                # Rate limit hit before attempt 6 — still pass
                assert i >= 4  # Should be at least 5 attempts (0-indexed)
                return

        # After 6 attempts, next should be 429
        resp = await app_client.post(
            "/api/auth/login",
            json={"email": "test.officer@cbi.example.com", "password": "wrongpass"},
        )
        assert resp.status_code == 429
        assert "too many" in resp.json()["detail"].lower()
