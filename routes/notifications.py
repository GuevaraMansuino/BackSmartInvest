from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from services.notification_service import NotificationRunResult, run_monthly_invest_notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationRunResponse(BaseModel):
    status: str
    task_name: str
    executed_at: datetime | None = None
    reason: str | None = None
    message_sent: bool


@router.post("/run", response_model=NotificationRunResponse)
async def run_notifications(
    force: bool = Query(default=False),
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
