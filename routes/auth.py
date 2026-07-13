"""
Controladores de Autenticación para Inversiones Inteligentes API.
Incluye:
- Registro (/register)
- Inicio de sesión (/login) con Opacidad de Errores y bloqueo por fuerza bruta
- Renovación rotatoria de sesión (/refresh)
- Cierre de sesión (/logout)
- Estado actual de usuario (/me)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from dependencies.auth_guard import AuthenticatedUser, get_current_user_guard
from models.entities import Profile
from schemas.auth import (
    AuthResponse,
    CurrentUserResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
)
from security.jwt_tokens import (
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_refresh_token,
    set_auth_cookies,
)
from security.password import hash_password, verify_password
from security.rate_limiter import (
    check_account_lockout,
    rate_limit_auth_requests,
    record_failed_login,
    reset_failed_login,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_auth_requests)],
)
async def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """
    Registra un nuevo usuario en el sistema con contraseña hasheada y tokens en Cookies HttpOnly.
    """
    normalized_email = payload.email.lower()

    # Verificar si el email ya existe
    existing = db.scalar(select(Profile).where(Profile.email == normalized_email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo electrónico ya está registrado.",
        )

    profile = Profile(
        email=normalized_email,
        password_hash=hash_password(payload.password),
        failed_login_attempts=0,
        locked_until=None,
    )
    db.add(profile)
    db.flush()

    # Emitir tokens duales
    access_token = create_access_token(user_id=str(profile.id), email=profile.email)
    refresh_token, _jti, expire_dt = create_refresh_token(user_id=str(profile.id))

    profile.refresh_token_hash = hash_refresh_token(refresh_token)
    profile.refresh_token_expires_at = expire_dt
    db.commit()
    db.refresh(profile)

    set_auth_cookies(response, access_token, refresh_token)

    return AuthResponse(
        user=CurrentUserResponse(id=profile.id, email=profile.email, role="authenticated"),
        message="Cuenta registrada exitosamente.",
        access_token=access_token,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit_auth_requests)],
)
async def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """
    Inicia sesión verificando credenciales.
    Aplica Opacidad de Errores ('Credenciales inválidas') y previene fuerza bruta.
    """
    normalized_email = payload.email.lower()
    profile = db.scalar(select(Profile).where(Profile.email == normalized_email))

    # Si la cuenta existe, validar si está temporalmente bloqueada
    if profile:
        check_account_lockout(profile)

    # Verificación segura de contraseña (previene timing attacks y enumeración de usuarios)
    hashed = profile.password_hash if profile else None
    valid_password = verify_password(payload.password, hashed)

    if not profile or not valid_password:
        record_failed_login(db, profile)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )

    # Login exitoso: restablecer contador de errores
    reset_failed_login(db, profile)

    access_token = create_access_token(user_id=str(profile.id), email=profile.email)
    refresh_token, _jti, expire_dt = create_refresh_token(user_id=str(profile.id))

    profile.refresh_token_hash = hash_refresh_token(refresh_token)
    profile.refresh_token_expires_at = expire_dt
    db.add(profile)
    db.commit()

    set_auth_cookies(response, access_token, refresh_token)

    return AuthResponse(
        user=CurrentUserResponse(id=profile.id, email=profile.email, role="authenticated"),
        message="Inicio de sesión exitoso.",
        access_token=access_token,
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """
    Rota el Refresh Token y emite un nuevo Access Token.
    Si se detecta un refresh token revocado/reutilizado, invalida la sesión.
    """
    token: str | None = request.cookies.get("refresh_token")
    if not token:
        # Intentar leer del header Authorization si fue provisto
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada o no encontrada.",
        )

    payload = decode_token(token, expected_type="refresh")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sesión inválido.",
        )

    profile = db.get(Profile, user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado.",
        )

    # Validar huella hash del refresh token (detección de rotación / robo)
    incoming_hash = hash_refresh_token(token)
    if not profile.refresh_token_hash or profile.refresh_token_hash != incoming_hash:
        # Posible robo o reutilización del refresh token: invalidar sesión en DB
        profile.refresh_token_hash = None
        profile.refresh_token_expires_at = None
        db.add(profile)
        db.commit()
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión inválida o reemplazada. Por favor inicia sesión nuevamente.",
        )

    # Validar expiración en DB
    now = datetime.now(timezone.utc)
    db_expire = profile.refresh_token_expires_at
    if db_expire and db_expire.tzinfo is None:
        db_expire = db_expire.replace(tzinfo=timezone.utc)

    if db_expire and now > db_expire:
        profile.refresh_token_hash = None
        profile.refresh_token_expires_at = None
        db.add(profile)
        db.commit()
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión ha expirado.",
        )

    # Rotar exitosamente los tokens
    new_access_token = create_access_token(user_id=str(profile.id), email=profile.email)
    new_refresh_token, _jti, new_expire_dt = create_refresh_token(user_id=str(profile.id))

    profile.refresh_token_hash = hash_refresh_token(new_refresh_token)
    profile.refresh_token_expires_at = new_expire_dt
    db.add(profile)
    db.commit()

    set_auth_cookies(response, new_access_token, new_refresh_token)

    return AuthResponse(
        user=CurrentUserResponse(id=profile.id, email=profile.email, role="authenticated"),
        message="Sesión renovada exitosamente.",
        access_token=new_access_token,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user_guard),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """
    Cierra sesión eliminando las Cookies HttpOnly y revocando el refresh token en DB.
    """
    profile = db.get(Profile, current_user.user_id)
    if profile:
        profile.refresh_token_hash = None
        profile.refresh_token_expires_at = None
        db.add(profile)
        db.commit()

    clear_auth_cookies(response)
    return MessageResponse(message="Sesión cerrada exitosamente.")


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user_guard),
) -> CurrentUserResponse:
    """
    Retorna la información del usuario autenticado actualmente.
    """
    return CurrentUserResponse(
        id=current_user.user_id,
        email=current_user.email,
        role=current_user.role,
    )
