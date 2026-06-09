from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, ClientOptions, create_client

from config import settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class AuthenticatedUser:
    user_id: UUID
    email: str | None
    role: str | None
    access_token: str


@lru_cache(maxsize=1)
def get_supabase_auth_client() -> Client:
    api_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_PUBLISHABLE_KEY
    return create_client(
        settings.SUPABASE_URL,
        api_key,
        options=ClientOptions(
            auto_refresh_token=False,
            persist_session=False,
        ),
    )


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser | None:
    if credentials is None:
        # Dev bypass when no token is present from frontend
        return AuthenticatedUser(
            user_id=UUID("00000000-0000-0000-0000-000000000000"),
            email="dev@smartinvest.com",
            role="authenticated",
            access_token="dev-token",
        )

    token = credentials.credentials

    try:
        claims_response = get_supabase_auth_client().auth.get_claims(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
        ) from exc

    if claims_response is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token claims.",
        )

    claims = claims_response.claims
    subject = claims.get("sub")

    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is missing.",
        )

    try:
        user_id = UUID(subject)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is invalid.",
        ) from exc

    return AuthenticatedUser(
        user_id=user_id,
        email=claims.get("email"),
        role=claims.get("role"),
        access_token=token,
    )


def get_current_user(
    current_user: AuthenticatedUser | None = Depends(get_optional_current_user),
) -> AuthenticatedUser:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    return current_user
