"""
Guardia de Autenticación (Auth Guard) de rutas para Smart Invest API.
Verifica tokens JWT en:
1. Cookie HttpOnly 'access_token' (prioridad para clientes web y prevención XSS)
2. Cabecera 'Authorization: Bearer <token>' (soporte API / móvil)
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from security.jwt_tokens import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class AuthenticatedUser:
    user_id: UUID
    email: str | None
    role: str | None
    access_token: str


def get_current_user_guard(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """
    Dependencia Auth Guard obligatoria para endpoints protegidos.
    """
    token: str | None = request.cookies.get("access_token")
    if not token and credentials:
        token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida. Por favor inicia sesión.",
        )

    payload = decode_token(token, expected_type="access")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: sujeto no encontrado.",
        )

    try:
        user_id = UUID(sub)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: identificador de usuario corrupto.",
        ) from exc

    return AuthenticatedUser(
        user_id=user_id,
        email=payload.get("email"),
        role=payload.get("role", "authenticated"),
        access_token=token,
    )
