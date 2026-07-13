"""
Suite de pruebas unitarias para el sistema integral de Autenticación y Seguridad.
Cubre:
1. Hashing criptográfico resistente a timing attacks
2. Emisión y rotación de Tokens JWT Duales
3. Prevención de fuerza bruta (bloqueo temporal de cuenta)
4. Guardia de Autenticación (Auth Guard)
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from models.entities import Profile
from security.jwt_tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_refresh_token,
)
from security.password import hash_password, verify_password
from security.rate_limiter import (
    check_account_lockout,
    record_failed_login,
    reset_failed_login,
)
from dependencies.auth_guard import get_current_user_guard, AuthenticatedUser


class TestPasswordHashing:
    def test_hash_and_verify_success(self):
        pwd = "SecurePassword123!"
        hashed = hash_password(pwd)
        assert hashed != pwd
        assert verify_password(pwd, hashed) is True

    def test_verify_invalid_password(self):
        pwd = "SecurePassword123!"
        hashed = hash_password(pwd)
        assert verify_password("WrongPassword!", hashed) is False

    def test_verify_none_hash_constant_time(self):
        # Debe retornar False de manera segura ante hash nulo
        assert verify_password("AnyPassword!", None) is False


class TestJWTTokens:
    def test_create_and_decode_access_token(self):
        user_id = str(uuid4())
        email = "gguevaraman@gmail.com"
        token = create_access_token(user_id=user_id, email=email, role="authenticated")

        payload = decode_token(token, expected_type="access")
        assert payload["sub"] == user_id
        assert payload["email"] == email
        assert payload["type"] == "access"

    def test_create_and_hash_refresh_token(self):
        user_id = str(uuid4())
        token, jti, expire = create_refresh_token(user_id=user_id)

        assert len(token) > 20
        assert jti
        assert expire > datetime.now(timezone.utc)

        hashed_token = hash_refresh_token(token)
        assert hashed_token != token
        assert len(hashed_token) == 64


class TestRateLimiterAndAccountLockout:
    def test_account_lockout_triggered_after_5_failures(self):
        db = MagicMock()
        profile = Profile(email="test@smartinvest.com", failed_login_attempts=0)

        for _ in range(5):
            record_failed_login(db, profile)

        assert profile.failed_login_attempts == 5
        assert profile.locked_until is not None

        # Al intentar chequear bloqueo debe lanzar HTTPException 429
        with pytest.raises(HTTPException) as exc_info:
            check_account_lockout(profile)
        assert exc_info.value.status_code == 429

    def test_reset_failed_login_clears_counter_and_lock(self):
        db = MagicMock()
        profile = Profile(
            email="test@smartinvest.com",
            failed_login_attempts=5,
            locked_until=datetime.now(timezone.utc) + timedelta(minutes=15),
        )

        reset_failed_login(db, profile)
        assert profile.failed_login_attempts == 0
        assert profile.locked_until is None


class TestAuthGuard:
    def test_guard_rejects_missing_credentials_and_cookie(self):
        req = MagicMock()
        req.cookies = {}

        with pytest.raises(HTTPException) as exc_info:
            get_current_user_guard(request=req, credentials=None)
        assert exc_info.value.status_code == 401

    def test_guard_authenticates_via_cookie(self):
        user_id = str(uuid4())
        token = create_access_token(user_id=user_id, email="gguevaraman@gmail.com")

        req = MagicMock()
        req.cookies = {"access_token": token}

        user = get_current_user_guard(request=req, credentials=None)
        assert isinstance(user, AuthenticatedUser)
        assert str(user.user_id) == user_id
        assert user.email == "gguevaraman@gmail.com"
