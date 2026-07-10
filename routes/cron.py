import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import text

from config import settings
from database import engine

logger = logging.getLogger("smart_invest.cron")

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.get("/keep-alive")
@router.get("/ping")
async def keep_alive_ping(
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None),
) -> dict:
    """
    Endpoint de Keep-Alive diseñado para ser ejecutado por Cron Jobs
    (Vercel Cron, UptimeRobot, cron-job.org) o manualmente desde el frontend.
    
    1. Despierta y mantiene activo el backend en Render.
    2. Ejecuta `SELECT 1` sobre Supabase para prevenir la suspensión por inactividad de 7 días.
    """
    secret = settings.CRON_SECRET
    if secret:
        provided = x_cron_secret or (authorization.replace("Bearer ", "") if authorization else "")
        if provided != secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credencial de Cron inválida.",
            )

    db_ok = False
    db_error = None

    try:
        with engine.connect() as conn:
            res = conn.execute(text("select 1"))
            if res.scalar() == 1:
                db_ok = True
    except Exception as exc:
        db_error = str(exc)
        logger.error("Keep-Alive database ping falló: %s", exc)

    return {
        "status": "awake" if db_ok else "degraded",
        "message": (
            "Keep-alive ejecutado con éxito. Supabase y Render activos."
            if db_ok
            else f"Error de conexión con la base de datos: {db_error}"
        ),
        "database": "pong" if db_ok else "error",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "smart-invest-backend",
    }
