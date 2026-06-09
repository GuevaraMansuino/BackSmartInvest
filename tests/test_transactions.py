"""
Tests de integración para Transaction (CRUD).
Usa SQLite en memoria.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database import Base
from dependencies.auth import AuthenticatedUser
from models import entities  # noqa: F401
from schemas.asset import AssetCreate
from schemas.portfolio import PortfolioCreate
from schemas.transaction import TransactionCreate, TransactionType, TransactionUpdate
from services.asset_service import create_asset
from services.portfolio_service import create_portfolio
from services.transaction_service import (
    create_transaction,
    delete_transaction,
    list_transactions,
    update_transaction,
)

NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


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
def user():
    return AuthenticatedUser(
        user_id=uuid4(), email="test@example.com", role="authenticated", access_token="tok"
    )


@pytest.fixture
def portfolio(db, user):
    return create_portfolio(db, user, PortfolioCreate(name="Test Portfolio"))


@pytest.fixture
def asset(db):
    return create_asset(db, AssetCreate(symbol="BTC", name="Bitcoin"))


class TestCreateTransaction:
    def test_creates_buy(self, db, user, portfolio, asset):
        payload = TransactionCreate(
            type=TransactionType.BUY,
            date=NOW,
            amount=Decimal("5000"),
            asset_id=asset.id,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
        )
        txn = create_transaction(db, user.user_id, portfolio.id, payload)
        assert txn.type == "BUY"
        assert txn.asset_id == asset.id

    def test_creates_deposit_without_asset(self, db, user, portfolio):
        payload = TransactionCreate(
            type=TransactionType.DEPOSIT,
            date=NOW,
            amount=Decimal("1000"),
        )
        txn = create_transaction(db, user.user_id, portfolio.id, payload)
        assert txn.type == "DEPOSIT"
        assert txn.asset_id is None

    def test_raises_if_buy_missing_required_fields(self):
        with pytest.raises(Exception):
            TransactionCreate(
                type=TransactionType.BUY,
                date=NOW,
                amount=Decimal("1000"),
                # sin asset_id, quantity, price
            )

    def test_raises_for_nonexistent_portfolio(self, db, user, asset):
        payload = TransactionCreate(
            type=TransactionType.DEPOSIT,
            date=NOW,
            amount=Decimal("1000"),
        )
        with pytest.raises(ValueError, match="no encontrado"):
            create_transaction(db, user.user_id, uuid4(), payload)


class TestListTransactions:
    def test_lists_all_transactions(self, db, user, portfolio, asset):
        for _ in range(3):
            create_transaction(
                db, user.user_id, portfolio.id,
                TransactionCreate(type=TransactionType.DEPOSIT, date=NOW, amount=Decimal("100")),
            )
        result = list_transactions(db, user.user_id, portfolio.id)
        assert len(result) == 3

    def test_filters_by_type(self, db, user, portfolio, asset):
        create_transaction(
            db, user.user_id, portfolio.id,
            TransactionCreate(type=TransactionType.DEPOSIT, date=NOW, amount=Decimal("500")),
        )
        create_transaction(
            db, user.user_id, portfolio.id,
            TransactionCreate(
                type=TransactionType.BUY, date=NOW, amount=Decimal("5000"),
                asset_id=asset.id, quantity=Decimal("0.1"), price=Decimal("50000"),
            ),
        )
        result = list_transactions(db, user.user_id, portfolio.id, transaction_type="DEPOSIT")
        assert all(t.type == "DEPOSIT" for t in result)


class TestUpdateTransaction:
    def test_updates_amount(self, db, user, portfolio):
        txn = create_transaction(
            db, user.user_id, portfolio.id,
            TransactionCreate(type=TransactionType.DEPOSIT, date=NOW, amount=Decimal("100")),
        )
        updated = update_transaction(
            db, user.user_id, portfolio.id, txn.id,
            TransactionUpdate(amount=Decimal("200")),
        )
        assert updated.amount == Decimal("200")

    def test_raises_for_nonexistent_transaction(self, db, user, portfolio):
        with pytest.raises(LookupError):
            update_transaction(
                db, user.user_id, portfolio.id, uuid4(), TransactionUpdate(amount=Decimal("1"))
            )


class TestDeleteTransaction:
    def test_deletes_transaction(self, db, user, portfolio):
        txn = create_transaction(
            db, user.user_id, portfolio.id,
            TransactionCreate(type=TransactionType.DEPOSIT, date=NOW, amount=Decimal("100")),
        )
        delete_transaction(db, user.user_id, portfolio.id, txn.id)
        result = list_transactions(db, user.user_id, portfolio.id)
        assert len(result) == 0

    def test_raises_for_nonexistent(self, db, user, portfolio):
        with pytest.raises(LookupError):
            delete_transaction(db, user.user_id, portfolio.id, uuid4())
