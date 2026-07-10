"""
Reemplaza el main.py con:
- Handler global de excepciones con mensajes uniformes
- Middleware de Request ID (X-Request-ID)
- Health check mejorado (DB + Telegram config)
- Logging estructurado básico
"""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from config import settings
from database import check_database_connection, engine
from routes import assets, auth, cron, market, notifications, portfolio, rebalance, strategy, transactions
from services.scheduler import shutdown_scheduler, start_scheduler

# ─────────────────────────────────────────
# Logging básico estructurado
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("smart_invest")


# ─────────────────────────────────────────
# Middleware: Request ID
# ─────────────────────────────────────────
class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ─────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting up Smart Invest API...")
    check_database_connection()
    logger.info("Database connection OK.")
    await market.warm_featured_cache()
    logger.info("Featured assets cache warm.")
    
    # Start scheduler background tasks
    start_scheduler()
    
    yield
    
    # Shutdown scheduler
    shutdown_scheduler()
    logger.info("Shutting down Smart Invest API.")


# ─────────────────────────────────────────
# App
# ─────────────────────────────────────────
app = FastAPI(
    title="Inversiones Inteligentes API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────
# Global exception handlers
# ─────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.exception(
        "Unhandled exception [request_id=%s] %s %s",
        request_id,
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "detail": "Ocurrió un error inesperado. Por favor intenta de nuevo.",
            "request_id": request_id,
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "detail": str(exc),
            "request_id": request_id,
        },
    )


# ─────────────────────────────────────────
# Root & Health check
# ─────────────────────────────────────────
@app.get("/", tags=["root"])
async def root() -> dict:
    """
    Endpoint raíz de la API.
    """
    return {
        "service": "Inversiones Inteligentes API",
        "status": "online",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "keep_alive": "/api/cron/keep-alive",
    }


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """
    Verifica el estado de la API y sus dependencias.
    - **db**: conexión a la base de datos
    - **telegram**: si el bot está configurado
    """
    db_ok = False
    db_error: str | None = None

    try:
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("select 1"))
        db_ok = True
    except Exception as exc:
        db_error = str(exc)
        logger.warning("Health check — DB failure: %s", exc)

    telegram_configured = bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)

    overall_status = "ok" if db_ok else "degraded"

    return {
        "status": overall_status,
        "service": "Inversiones Inteligentes API",
        "dependencies": {
            "database": {"status": "ok" if db_ok else "error", "error": db_error},
            "telegram": {"status": "configured" if telegram_configured else "not_configured"},
        },
    }


# ─────────────────────────────────────────
# Routers
# ─────────────────────────────────────────
app.include_router(auth.router)
app.include_router(assets.router)
app.include_router(portfolio.router)
app.include_router(strategy.router)
app.include_router(transactions.router)
app.include_router(rebalance.router)
app.include_router(market.router)
app.include_router(notifications.router)
app.include_router(cron.router)
