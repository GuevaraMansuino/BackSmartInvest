"""
Tests de la dependencia de autenticación (dependencies/auth.py).

Usa MagicMock para simular el cliente Supabase sin necesitar conexión real.
"""

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from dependencies.auth import (
    AuthenticatedUser,
    get_current_user,
    get_optional_current_user,
)


FAKE_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
FAKE_EMAIL = "test@example.com"


def _make_credentials(token: str = "fake_token") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _make_claims_response(user_id: str = FAKE_USER_ID, email: str = FAKE_EMAIL):
    claims_response = MagicMock()
    claims_response.claims = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
    }
    return claims_response


class TestGetOptionalCurrentUser:
    def test_returns_none_when_no_credentials(self):
        result = get_optional_current_user(credentials=None)
        assert result is None

    def test_returns_authenticated_user_on_valid_token(self):
        mock_response = _make_claims_response()

        with patch(
            "dependencies.auth.get_supabase_auth_client"
        ) as mock_client_factory:
            mock_client = MagicMock()
            mock_client.auth.get_claims.return_value = mock_response
            mock_client_factory.return_value = mock_client

            result = get_optional_current_user(credentials=_make_credentials())

        assert isinstance(result, AuthenticatedUser)
        assert result.user_id == UUID(FAKE_USER_ID)
        assert result.email == FAKE_EMAIL
        assert result.role == "authenticated"

    def test_raises_401_when_supabase_throws(self):
        with patch(
            "dependencies.auth.get_supabase_auth_client"
        ) as mock_client_factory:
            mock_client = MagicMock()
            mock_client.auth.get_claims.side_effect = Exception("token expired")
            mock_client_factory.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                get_optional_current_user(credentials=_make_credentials())

        assert exc_info.value.status_code == 401

    def test_raises_401_when_claims_response_is_none(self):
        with patch(
            "dependencies.auth.get_supabase_auth_client"
        ) as mock_client_factory:
            mock_client = MagicMock()
            mock_client.auth.get_claims.return_value = None
            mock_client_factory.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                get_optional_current_user(credentials=_make_credentials())

        assert exc_info.value.status_code == 401

    def test_raises_401_when_sub_missing(self):
        mock_response = MagicMock()
        mock_response.claims = {"email": FAKE_EMAIL}  # sin "sub"

        with patch(
            "dependencies.auth.get_supabase_auth_client"
        ) as mock_client_factory:
            mock_client = MagicMock()
            mock_client.auth.get_claims.return_value = mock_response
            mock_client_factory.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                get_optional_current_user(credentials=_make_credentials())

        assert exc_info.value.status_code == 401

    def test_raises_401_when_sub_is_invalid_uuid(self):
        mock_response = MagicMock()
        mock_response.claims = {"sub": "not-a-uuid", "email": FAKE_EMAIL}

        with patch(
            "dependencies.auth.get_supabase_auth_client"
        ) as mock_client_factory:
            mock_client = MagicMock()
            mock_client.auth.get_claims.return_value = mock_response
            mock_client_factory.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                get_optional_current_user(credentials=_make_credentials())

        assert exc_info.value.status_code == 401


class TestGetCurrentUser:
    def test_raises_401_when_user_is_none(self):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(current_user=None)

        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail

    def test_returns_user_when_not_none(self):
        user = AuthenticatedUser(
            user_id=UUID(FAKE_USER_ID),
            email=FAKE_EMAIL,
            role="authenticated",
            access_token="token",
        )
        result = get_current_user(current_user=user)
        assert result is user
