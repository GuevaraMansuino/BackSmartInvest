from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from models import SystemLog
from services.telegram_bot import TelegramBotService

MONTHLY_INVEST_TASK_NAME = "monthly_invest"


@dataclass(slots=True)
class NotificationRunResult:
    status: str
    task_name: str
    executed_at: datetime | None
    reason: str | None
    message_sent: bool


def get_current_datetime() -> datetime:
    return datetime.now(tz=ZoneInfo(settings.APP_TIMEZONE))


def is_run_day(current_datetime: datetime | None = None) -> bool:
    today = current_datetime or get_current_datetime()
    is_weekend = today.weekday() >= 5

    if today.day == 3 and not is_weekend:
        return True
    if today.day == 4 and today.weekday() == 0:
        return True
    if today.day == 5 and today.weekday() == 0:
        return True

    return False


def month_bounds(current_datetime: datetime) -> tuple[datetime, datetime]:
    month_start = current_datetime.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)

    return (
        month_start.astimezone(timezone.utc),
        next_month_start.astimezone(timezone.utc),
    )


def has_monthly_run(
    db: Session,
    current_datetime: datetime,
    task_name: str = MONTHLY_INVEST_TASK_NAME,
) -> bool:
    month_start, next_month_start = month_bounds(current_datetime)
    statement = (
        select(SystemLog.id)
        .where(SystemLog.task_name == task_name)
        .where(SystemLog.executed_at >= month_start)
        .where(SystemLog.executed_at < next_month_start)
        .limit(1)
    )

    return db.execute(statement).scalar_one_or_none() is not None


def create_monthly_message(current_datetime: datetime) -> str:
    month_label = current_datetime.strftime("%B %Y")
    return (
        f"Inversiones Inteligentes\n"
        f"Recordatorio de inversion mensual: {month_label}\n"
        f"Revisa aportes pendientes y sugerencias de rebalanceo."
    )


async def run_monthly_invest_notification(
    db: Session,
    force: bool = False,
) -> NotificationRunResult:
    current_datetime = get_current_datetime()

    if not force and not is_run_day(current_datetime):
        return NotificationRunResult(
            status="skipped",
            task_name=MONTHLY_INVEST_TASK_NAME,
            executed_at=None,
            reason="not_run_day",
            message_sent=False,
        )

    if has_monthly_run(db=db, current_datetime=current_datetime):
        return NotificationRunResult(
            status="skipped",
            task_name=MONTHLY_INVEST_TASK_NAME,
            executed_at=None,
            reason="already_executed_this_month",
            message_sent=False,
        )

    await TelegramBotService.send_message(create_monthly_message(current_datetime))

    executed_at = current_datetime.astimezone(timezone.utc)
    db.add(SystemLog(task_name=MONTHLY_INVEST_TASK_NAME, executed_at=executed_at))
    db.commit()

    return NotificationRunResult(
        status="success",
        task_name=MONTHLY_INVEST_TASK_NAME,
        executed_at=executed_at,
        reason=None,
        message_sent=True,
    )
