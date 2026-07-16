"""
Tests de integración para Strategy (set, get, delete).
Usa SQLite en memoria.
"""

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
from schemas.strategy import StrategyItemCreate, StrategySetRequest
from services.asset_service import create_asset
from services.portfolio_service import create_portfolio
from services.strategy_service import delete_strategy_item, deposit_strategy_budget, get_strategy, set_strategy


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
    return create_portfolio(db, user, PortfolioCreate(name="Mi Portfolio"))


@pytest.fixture
def asset_btc(db):
    return create_asset(db, AssetCreate(symbol="BTC", name="Bitcoin"))


@pytest.fixture
def asset_eth(db):
    return create_asset(db, AssetCreate(symbol="ETH", name="Ethereum"))


class TestSetStrategy:
    def test_sets_strategy(self, db, user, portfolio, asset_btc, asset_eth):
        payload = StrategySetRequest(
            items=[
                StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("60")),
                StrategyItemCreate(asset_id=asset_eth.id, percentage=Decimal("40")),
            ]
        )
        items = set_strategy(db, user.user_id, portfolio.id, payload)
        assert len(items) == 2

    def test_replaces_existing_strategy(self, db, user, portfolio, asset_btc, asset_eth):
        # Primera estrategia
        payload1 = StrategySetRequest(
            items=[StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("100"))]
        )
        set_strategy(db, user.user_id, portfolio.id, payload1)

        # Reemplazar
        payload2 = StrategySetRequest(
            items=[
                StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("70")),
                StrategyItemCreate(asset_id=asset_eth.id, percentage=Decimal("30")),
            ]
        )
        items = set_strategy(db, user.user_id, portfolio.id, payload2)
        assert len(items) == 2

    def test_raises_for_wrong_owner(self, db, user, portfolio, asset_btc):
        other = AuthenticatedUser(
            user_id=uuid4(), email="x@x.com", role="authenticated", access_token="tok"
        )
        payload = StrategySetRequest(
            items=[StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("100"))]
        )
        with pytest.raises(ValueError, match="no pertenece"):
            set_strategy(db, other.user_id, portfolio.id, payload)

    def test_raises_for_nonexistent_asset(self, db, user, portfolio):
        payload = StrategySetRequest(
            items=[StrategyItemCreate(asset_id=uuid4(), percentage=Decimal("100"))]
        )
        with pytest.raises(ValueError, match="no existen"):
            set_strategy(db, user.user_id, portfolio.id, payload)


class TestStrategyValidation:
    def test_rejects_duplicate_assets_in_payload(self, db, user, portfolio, asset_btc):
        with pytest.raises(Exception):
            StrategySetRequest(
                items=[
                    StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("50")),
                    StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("50")),
                ]
            )

    def test_rejects_total_over_100(self, db, user, portfolio, asset_btc, asset_eth):
        with pytest.raises(Exception):
            StrategySetRequest(
                items=[
                    StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("60")),
                    StrategyItemCreate(asset_id=asset_eth.id, percentage=Decimal("50")),
                ]
            )

    def test_allows_total_under_100(self, db, user, portfolio, asset_btc):
        # < 100% permitido (construcción gradual)
        payload = StrategySetRequest(
            items=[StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("60"))]
        )
        assert payload  # sin excepción


class TestDeleteStrategyItem:
    def test_deletes_item(self, db, user, portfolio, asset_btc):
        payload = StrategySetRequest(
            items=[StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("100"))]
        )
        items = set_strategy(db, user.user_id, portfolio.id, payload)
        item_id = items[0].id

        delete_strategy_item(db, user.user_id, portfolio.id, item_id)
        remaining = get_strategy(db, user.user_id, portfolio.id)
        assert len(remaining) == 0

    def test_raises_for_nonexistent_item(self, db, user, portfolio):
        with pytest.raises(LookupError):
            delete_strategy_item(db, user.user_id, portfolio.id, uuid4())


class TestDepositStrategyBudget:
    def test_deposits_budget_according_to_percentages(self, db, user, portfolio, asset_btc, asset_eth):
        portfolio.monthly_amount = Decimal("1000.00")
        db.commit()

        payload = StrategySetRequest(
            items=[
                StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("60")),
                StrategyItemCreate(asset_id=asset_eth.id, percentage=Decimal("40")),
            ]
        )
        set_strategy(db, user.user_id, portfolio.id, payload)

        txns = deposit_strategy_budget(db, user.user_id, portfolio.id)
        assert len(txns) == 2

        btc_txn = next(t for t in txns if t.asset_id == asset_btc.id)
        eth_txn = next(t for t in txns if t.asset_id == asset_eth.id)

        assert btc_txn.amount == Decimal("600.00")
        assert eth_txn.amount == Decimal("400.00")
        assert btc_txn.type == "DEPOSIT"
        assert eth_txn.type == "DEPOSIT"

    def test_deposits_custom_amount_if_specified(self, db, user, portfolio, asset_btc):
        payload = StrategySetRequest(
            items=[StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("100"))]
        )
        set_strategy(db, user.user_id, portfolio.id, payload)

        txns = deposit_strategy_budget(db, user.user_id, portfolio.id, amount=Decimal("500.00"))
        assert len(txns) == 1
        assert txns[0].amount == Decimal("500.00")
