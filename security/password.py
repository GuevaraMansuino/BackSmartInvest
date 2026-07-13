"""
Módulo de Hashing Criptográfico robusto para contraseñas.
Utiliza bcrypt moderno con factor de costo alto y verificación resistente a timing attacks.
"""

from __future__ import annotations

import bcrypt

_BCRYPT_ROUNDS = 12
_DUMMY_HASH = b"$2b$12$e8gA8n0BvVzQ1v9gK1X9eeZg/7e0S8iUq8dM5w5yG8d6L3rNqA8jG"


def _prepare_password(password: str) -> bytes:
    # Bcrypt admite como máximo 72 bytes en la entrada
    pwd_bytes = password.encode("utf-8")
    return pwd_bytes[:72]


def hash_password(password: str) -> str:
    """
    Genera el hash criptográfico robusto de una contraseña utilizando bcrypt.
    """
    pwd_bytes = _prepare_password(password)
    hashed = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))
    return hashed.decode("ascii")


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """
    Verifica de forma segura si una contraseña coincide con su hash.
    Protegido contra ataques de tiempo (timing attacks): si hashed_password es None o inválida,
    ejecuta checkpw contra un hash dummy para asegurar tiempo de procesamiento constante.
    """
    pwd_bytes = _prepare_password(plain_password)
    if not hashed_password:
        bcrypt.checkpw(pwd_bytes, _DUMMY_HASH)
        return False
    try:
        hashed_bytes = hashed_password.encode("ascii")
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except Exception:
        bcrypt.checkpw(pwd_bytes, _DUMMY_HASH)
        return False
