from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings


class Base(DeclarativeBase):
    pass


def _build_database_url() -> str:
    if settings.DATABASE_URL.startswith("postgresql://"):
        return settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

    return settings.DATABASE_URL

import socket
from urllib.parse import urlparse

def get_connect_args(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.hostname:
        try:
            # Force IPv4 resolution to bypass IPv6 Network Unreachable errors
            ipv4_addr = socket.gethostbyname(parsed.hostname)
            return {"hostaddr": ipv4_addr}
        except Exception:
            pass
    return {}

engine = create_engine(
    _build_database_url(),
    pool_pre_ping=True,
    connect_args=get_connect_args(settings.DATABASE_URL),
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> None:
    with engine.connect() as connection:
        connection.execute(text("select 1"))
