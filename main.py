from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import check_database_connection
from routes import auth, notifications, portfolio


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_database_connection()
    yield


app = FastAPI(
    title="Inversiones Inteligentes API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Inversiones Inteligentes API"}


app.include_router(auth.router)
app.include_router(portfolio.router)
app.include_router(notifications.router)
