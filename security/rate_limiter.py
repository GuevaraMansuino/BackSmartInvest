"""
Módulo de Rate Limiting y Prevención de Fuerza Bruta.
- Limitador de peticiones por IP en memoria (sliding window)
- Gestión de bloqueo temporal de cuenta (15 minutos tras 5 intentos fallidos)
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from models.entities import Profile

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
IP_RATE_LIMIT_WINDOW_SEC = 60
MAX_REQUESTS_PER_WINDOW = 30

# Almacén en memoria thread-safe para limitación por IP
_ip_request_counts: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


def rate_limit_auth_requests(request: Request) -> None:
    """
    Dependencia / Middleware para limitar la tasa de peticiones en rutas de autenticación por IP.
    Previene inundaciones de red y ataques de fuerza bruta masiva.
    """
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or getattr(request.client, "host", "127.0.0.1")
    )

    now = time.time()
    window_start = now - IP_RATE_LIMIT_WINDOW_SEC

    with _lock:
        timestamps = _ip_request_counts[client_ip]
        # Limpiar timestamps expirados de la ventana
        valid_timestamps = [t for t in timestamps if t > window_start]
        if len(valid_timestamps) >= MAX_REQUESTS_PER_WINDOW:
            _ip_request_counts[client_ip] = valid_timestamps
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiadas peticiones. Por favor espera antes de volver a intentarlo.",
            )
        valid_timestamps.append(now)
        _ip_request_counts[client_ip] = valid_timestamps


def check_account_lockout(profile: Profile) -> None:
    """
    Verifica si una cuenta está temporalmente bloqueada debido a sucesivos intentos fallidos.
    """
    if profile.locked_until:
        now = datetime.now(timezone.utc)
        # Aseguramos comparación con datetime timezone-aware
        locked_until = profile.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)

        if now < locked_until:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos fallidos. Intenta nuevamente en unos minutos.",
            )


def record_failed_login(db: Session, profile: Profile | None) -> None:
    """
    Registra un intento fallido en la cuenta si existe.
    Al alcanzar el límite (5), bloquea la cuenta por 15 minutos.
    """
    if profile is None:
        return

    profile.failed_login_attempts = (profile.failed_login_attempts or 0) + 1
    if profile.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        now = datetime.now(timezone.utc)
        profile.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)

    db.add(profile)
    db.commit()


def reset_failed_login(db: Session, profile: Profile) -> None:
    """
    Restablece el contador de intentos fallidos al iniciar sesión exitosamente.
    """
    if profile.failed_login_attempts > 0 or profile.locked_until is not None:
        profile.failed_login_attempts = 0
        profile.locked_until = None
        db.add(profile)
        db.commit()
