from fastapi import APIRouter, Depends

from dependencies import AuthenticatedUser, get_current_user
from schemas import CurrentUserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=current_user.user_id,
        email=current_user.email,
        role=current_user.role,
    )
