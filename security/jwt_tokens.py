"""
Módulo de Gestión de Tokens JWT Duales y Cookies Seguras.
- Access Token de corta duración (15 minutos)
- Refresh Token rotatorio de larga duración (7 días)
- Gestión de cookies HttpOnly, Secure, SameSite=Strict para mitigación XSS/CSRF
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from starlette.responses import Response
from jose import JWTError, jwt

from config import settings

ACCESS_TOKEN_EXPIRE_MINUTES = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 15)
REFRESH_TOKEN_EXPIRE_DAYS = 7


def _get_secret_key() -> str:
    # Priorizar JWT_SECRET configurado, o fallback a SUPABASE_SERVICE_ROLE_KEY
    return settings.JWT_SECRET or settings.SUPABASE_SERVICE_ROLE_KEY or "dev-secret-key-smart-invest-change-me"


def create_access_token(user_id: str, email: str, role: str = "authenticated") -> str:
    """
    Crea un Access Token JWT de corta duración.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, _get_secret_key(), algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    """
    Crea un Refresh Token JWT rotatorio.
    Retorna: (token_string, jti, exp_datetime_utc)
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    jti = str(uuid4())
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, _get_secret_key(), algorithm=settings.ALGORITHM)
    return token, jti, expire


def decode_token(token: str, expected_type: str | None = None) -> dict:
    """
    Decodifica y verifica la firma y expiración de un token JWT.
    """
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[settings.ALGORITHM])
        if expected_type and payload.get("type") != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tipo de token inválido.",
            )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado o inválido.",
        ) from exc


def hash_refresh_token(token: str) -> str:
    """
    Genera un hash SHA256 del refresh token para almacenamiento seguro en DB.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """
    Adjunta los tokens duales en Cookies seguras con atributos:
    - HttpOnly=True (Inaccesible desde Javascript del navegador, previene XSS)
    - Secure=False en localhost, True en producción
    - SameSite='strict' (Previene CSRF)
    """
    is_secure = not ("localhost" in settings.BACKEND_CORS_ORIGINS or "127.0.0.1" in settings.BACKEND_CORS_ORIGINS)

    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=is_secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=is_secure,
        samesite="strict",
        path="/api/auth",
    )


def clear_auth_cookies(response: Response) -> None:
    """
    Limpia las cookies de autenticación al cerrar sesión.
    """
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth")
