"""
Tests de integración para el CRUD de portfolios.

Usa una base de datos SQLite en memoria para correr sin infraestructura externa.
"""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database import Base
from dependencies.auth import AuthenticatedUser
from models import entities  # noqa: F401 — registra todos los modelos
from schemas.portfolio import PortfolioCreate, PortfolioUpdate
from services.portfolio_service import (
    create_portfolio,
    delete_portfolio,
    get_portfolio_or_none,
    list_portfolios,
    update_portfolio,
)


# ─────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────
@pytest.fixture(scope="function")
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=uuid4(),
        email="test@example.com",
        role="authenticated",
        access_token="fake_token",
    )


@pytest.fixture
def other_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=uuid4(),
        email="other@example.com",
        role="authenticated",
        access_token="other_token",
    )


# ─────────────────────────────────────────
# Tests: create_portfolio
# ─────────────────────────────────────────
class TestCreatePortfolio:
    def test_creates_portfolio(self, db, user):
        p = create_portfolio(db, user, PortfolioCreate(name="Mi Portfolio"))
        assert p.name == "Mi Portfolio"
        assert p.user_id == user.user_id

    def test_strips_whitespace(self, db, user):
        p = create_portfolio(db, user, PortfolioCreate(name="  Mi Portfolio  "))
        assert p.name == "Mi Portfolio"

    def test_creates_profile_if_missing(self, db, user):
        from models.entities import Profile
        assert db.get(Profile, user.user_id) is None
        create_portfolio(db, user, PortfolioCreate(name="Test"))
        assert db.get(Profile, user.user_id) is not None


# ─────────────────────────────────────────
# Tests: list_portfolios
# ─────────────────────────────────────────
class TestListPortfolios:
    def test_returns_only_user_portfolios(self, db, user, other_user):
        create_portfolio(db, user, PortfolioCreate(name="A"))
        create_portfolio(db, user, PortfolioCreate(name="B"))
        create_portfolio(db, other_user, PortfolioCreate(name="Other"))

        result = list_portfolios(db, user)
        names = {p.name for p in result}
        assert names == {"A", "B"}

    def test_returns_empty_list_when_no_portfolios(self, db, user):
        result = list_portfolios(db, user)
        assert result == []


# ─────────────────────────────────────────
# Tests: get_portfolio_or_none
# ─────────────────────────────────────────
class TestGetPortfolioOrNone:
    def test_returns_portfolio_for_owner(self, db, user):
        p = create_portfolio(db, user, PortfolioCreate(name="Test"))
        result = get_portfolio_or_none(db, user, p.id)
        assert result is not None
        assert result.id == p.id

    def test_returns_none_for_other_user(self, db, user, other_user):
        p = create_portfolio(db, user, PortfolioCreate(name="Test"))
        result = get_portfolio_or_none(db, other_user, p.id)
        assert result is None

    def test_returns_none_for_nonexistent(self, db, user):
        result = get_portfolio_or_none(db, user, uuid4())
        assert result is None


# ─────────────────────────────────────────
# Tests: update_portfolio
# ─────────────────────────────────────────
class TestUpdatePortfolio:
    def test_updates_name(self, db, user):
        p = create_portfolio(db, user, PortfolioCreate(name="Old"))
        updated = update_portfolio(db, p, PortfolioUpdate(name="New"))
        assert updated.name == "New"


# ─────────────────────────────────────────
# Tests: delete_portfolio
# ─────────────────────────────────────────
class TestDeletePortfolio:
    def test_deletes_portfolio(self, db, user):
        p = create_portfolio(db, user, PortfolioCreate(name="ToDelete"))
        delete_portfolio(db, p)
        assert get_portfolio_or_none(db, user, p.id) is None
