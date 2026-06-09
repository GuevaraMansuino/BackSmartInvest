from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from dependencies import AuthenticatedUser, get_optional_current_user
from services.notification_service import NotificationRunResult, run_monthly_invest_notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationRunResponse(BaseModel):
    status: str
    task_name: str
    executed_at: datetime | None = None
    reason: str | None = None
    message_sent: bool


def authorize_notification_run(
    x_cron_secret: str | None = Header(default=None),
    current_user: AuthenticatedUser | None = Depends(get_optional_current_user),
) -> AuthenticatedUser | None:
    if settings.CRON_SECRET and x_cron_secret == settings.CRON_SECRET:
        return current_user

    if current_user is not None:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authorized to run notifications.",
    )


@router.post("/run", response_model=NotificationRunResponse)
async def run_notifications(
    force: bool = Query(default=False),
    _: AuthenticatedUser | None = Depends(authorize_notification_run),
    db: Session = Depends(get_db),
) -> NotificationRunResponse:
    try:
        result: NotificationRunResult = await run_monthly_invest_notification(
            db=db,
            force=force,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return NotificationRunResponse.model_validate(asdict(result))
