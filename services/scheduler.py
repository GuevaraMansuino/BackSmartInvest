import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text
from database import engine

logger = logging.getLogger("smart_invest.scheduler")

scheduler = AsyncIOScheduler()

def ping_database():
    """
    Pings the database to keep the Supabase instance awake.
    """
    try:
        logger.info("Executing scheduled task: ping_database")
        with engine.connect() as conn:
            conn.execute(text("select 1"))
            conn.commit()
        logger.info("Database ping successful.")
    except Exception as exc:
        logger.error(f"Database ping failed: {exc}")


def start_scheduler() -> None:
    # Schedule the ping every 1 hour to keep Supabase DB active
    scheduler.add_job(ping_database, "interval", hours=1, id="ping_db_job", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started.")


def shutdown_scheduler() -> None:
    scheduler.shutdown()
    logger.info("Scheduler shutdown.")
