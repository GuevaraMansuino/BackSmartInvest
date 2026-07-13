from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(..., description="Correo electrónico del usuario")
    password: str = Field(..., min_length=8, max_length=128, description="Contraseña de al menos 8 caracteres")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if not EMAIL_REGEX.match(v_clean):
            raise ValueError("Formato de correo electrónico inválido.")
        return v_clean

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("La contraseña debe incluir al menos una letra y un número.")
        return v


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(..., description="Correo electrónico del usuario")
    password: str = Field(..., min_length=1, max_length=128, description="Contraseña del usuario")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class CurrentUserResponse(BaseModel):
    id: UUID
    email: str | None = None
    role: str | None = "authenticated"


class AuthResponse(BaseModel):
    user: CurrentUserResponse
    message: str = "Autenticación exitosa."
    access_token: str | None = None


class MessageResponse(BaseModel):
    message: str
