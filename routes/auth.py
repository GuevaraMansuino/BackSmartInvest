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

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from dependencies.auth_guard import AuthenticatedUser, get_current_user_guard
from models.entities import Profile
from schemas.auth import (
    AuthResponse,
    CurrentUserResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    RequestPasswordChangeResponse,
    VerifyPasswordChangeRequest,
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


def _hash_reset_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def _send_smtp_verification_email(to_email: str, code: str) -> None:
    if not settings.SMTP_SERVER or not settings.SMTP_USER:
        return
    try:
        html_body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #000; color: #fff; padding: 20px;">
            <div style="max-width: 500px; margin: 0 auto; background-color: #111; border: 1px solid #333; border-radius: 12px; padding: 24px;">
              <h2 style="color: #10b981; margin-top: 0;">SmartInvest Seguridad</h2>
              <p style="color: #ccc;">Has solicitado cambiar tu contraseña de SmartInvest. Utiliza el siguiente código de verificación temporal (válido por 15 minutos):</p>
              <div style="font-size: 28px; font-weight: bold; letter-spacing: 4px; color: #fff; background-color: #222; padding: 16px; border-radius: 8px; text-align: center; margin: 20px 0;">
                {code}
              </div>
              <p style="font-size: 12px; color: #777;">Si no has solicitado este cambio, puedes ignorar este correo.</p>
            </div>
          </body>
        </html>
        """

        # 1. Si es Resend, usar API REST por HTTPS (puerto 443) instantáneo en lugar de SMTP (que Render bloquea en puerto 587)
        if (
            "resend" in settings.SMTP_SERVER.lower()
            or settings.SMTP_USER == "resend"
            or settings.SMTP_PASSWORD.startswith("re_")
        ):
            import requests

            headers = {
                "Authorization": f"Bearer {settings.SMTP_PASSWORD}",
                "Content-Type": "application/json",
            }
            payload = {
                "from": settings.SMTP_FROM_EMAIL or "onboarding@resend.dev",
                "to": [to_email],
                "subject": "Código de verificación - Cambio de contraseña SmartInvest",
                "html": html_body,
            }
            res = requests.post("https://api.resend.com/emails", json=payload, headers=headers, timeout=5)
            if res.status_code in (200, 201):
                print(f"[RESEND OK] Correo enviado exitosamente vía API REST a {to_email}")
            else:
                print(f"[RESEND WARNING {res.status_code}] Error al enviar con Resend API: {res.text}")
            return

        # 2. Si es Brevo API REST por HTTPS (puerto 443) - permite enviar a cualquier correo gratis
        if (
            "brevo" in settings.SMTP_SERVER.lower()
            or settings.SMTP_USER == "brevo"
            or settings.SMTP_PASSWORD.startswith("xkeysib-")
        ):
            import requests

            headers = {
                "api-key": settings.SMTP_PASSWORD,
                "Content-Type": "application/json",
            }
            payload = {
                "sender": {"email": settings.SMTP_FROM_EMAIL or "no-reply@smartinvest.com", "name": "SmartInvest"},
                "to": [{"email": to_email}],
                "subject": "Código de verificación - Cambio de contraseña SmartInvest",
                "htmlContent": html_body,
            }
            res = requests.post("https://api.brevo.com/v3/smtp/email", json=payload, headers=headers, timeout=5)
            if res.status_code in (200, 201, 202):
                print(f"[BREVO OK] Correo enviado exitosamente vía API REST a {to_email}")
            else:
                print(f"[BREVO WARNING {res.status_code}] Error al enviar con Brevo API: {res.text}")
            return

        # 3. Si es otro SMTP tradicional
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Código de verificación - Cambio de contraseña SmartInvest"
        msg["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=8) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        print(f"[SMTP OK] Correo de verificación enviado exitosamente a {to_email}")
    except Exception as exc:
        print(f"[EMAIL WARNING] No se pudo enviar el correo: {exc}")


@router.post("/request-password-change", response_model=RequestPasswordChangeResponse)
async def request_password_change(
    current_user: AuthenticatedUser = Depends(get_current_user_guard),
    db: Session = Depends(get_db),
) -> RequestPasswordChangeResponse:
    """
    Genera un código de verificación de 6 dígitos para cambio de contraseña y lo envía al correo.
    """
    try:
        profile = db.get(Profile, current_user.user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado en base de datos.",
            )

        code = f"{secrets.randbelow(1000000):06d}"
        now = datetime.now(timezone.utc)
        expire_dt = now + timedelta(minutes=15)

        profile.reset_code_hash = _hash_reset_code(code)
        profile.reset_code_expires_at = expire_dt
        db.add(profile)
        db.commit()

        print(f"\n[SECURITY EMAIL] Correo de verificación para {profile.email}")
        print(f"[SECURITY EMAIL] Código temporal (válido 15 min): {code}\n")

        _send_smtp_verification_email(profile.email, code)

        return RequestPasswordChangeResponse(
            message="Código de verificación enviado al correo electrónico.",
            dev_code=code,
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en base de datos al solicitar cambio de contraseña ({type(exc).__name__}): {exc}",
        )


@router.post("/verify-and-change-password", response_model=MessageResponse)
async def verify_and_change_password(
    payload: VerifyPasswordChangeRequest,
    current_user: AuthenticatedUser = Depends(get_current_user_guard),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """
    Verifica el código de 6 dígitos y actualiza la contraseña del usuario.
    """
    profile = db.get(Profile, current_user.user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )

    if not profile.reset_code_hash or not profile.reset_code_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No has solicitado un código de verificación o ya fue utilizado.",
        )

    now = datetime.now(timezone.utc)
    db_expire = profile.reset_code_expires_at
    if db_expire.tzinfo is None:
        db_expire = db_expire.replace(tzinfo=timezone.utc)

    if now > db_expire:
        profile.reset_code_hash = None
        profile.reset_code_expires_at = None
        db.add(profile)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El código de verificación ha expirado. Solicita uno nuevo.",
        )

    incoming_hash = _hash_reset_code(payload.code.strip())
    if incoming_hash != profile.reset_code_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de verificación incorrecto.",
        )

    profile.password_hash = hash_password(payload.new_password)
    profile.reset_code_hash = None
    profile.reset_code_expires_at = None
    db.add(profile)
    db.commit()

    return MessageResponse(message="Contraseña actualizada exitosamente.")
