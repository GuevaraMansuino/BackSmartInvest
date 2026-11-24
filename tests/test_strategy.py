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
from schemas.strategy import StrategyItemCreate, StrategyReserveManageRequest, StrategySetRequest
from services.asset_service import create_asset
from services.portfolio_service import create_portfolio
from services.strategy_service import (
    delete_strategy_item,
    deposit_strategy_budget,
    get_portfolio_reserves,
    get_strategy,
    reallocate_reserves,
    set_strategy,
)


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


class TestReallocateReserves:
    def test_reallocate_to_global_fund(self, db, user, portfolio, asset_btc):
        # Primero depositamos presupuesto en BTC
        payload = StrategySetRequest(
            items=[StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("100"))]
        )
        set_strategy(db, user.user_id, portfolio.id, payload)
        deposit_strategy_budget(db, user.user_id, portfolio.id, amount=Decimal("1000.00"))

        # Reasignamos 400 de BTC al Fondo General
        manage_payload = StrategyReserveManageRequest(
            action="TO_GLOBAL",
            source_asset_id=asset_btc.id,
            amount=Decimal("400.00"),
        )
        txns = reallocate_reserves(db, user.user_id, portfolio.id, manage_payload)
        assert len(txns) == 2
        assert txns[0].type == "WITHDRAW"
        assert txns[0].asset_id == asset_btc.id
        assert txns[0].amount == Decimal("400.00")
        assert txns[1].type == "DEPOSIT"
        assert txns[1].asset_id is None
        assert txns[1].amount == Decimal("400.00")

        asset_res, global_res = get_portfolio_reserves(db, portfolio.id)
        assert asset_res[asset_btc.id] == Decimal("600.00")
        assert global_res == Decimal("400.00")

    def test_reallocate_between_assets(self, db, user, portfolio, asset_btc, asset_eth):
        payload = StrategySetRequest(
            items=[StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("100"))]
        )
        set_strategy(db, user.user_id, portfolio.id, payload)
        deposit_strategy_budget(db, user.user_id, portfolio.id, amount=Decimal("1000.00"))

        # Reasignamos 300 de BTC a ETH
        manage_payload = StrategyReserveManageRequest(
            action="TO_ASSET",
            source_asset_id=asset_btc.id,
            target_asset_id=asset_eth.id,
            amount=Decimal("300.00"),
        )
        txns = reallocate_reserves(db, user.user_id, portfolio.id, manage_payload)
        assert len(txns) == 2

        asset_res, global_res = get_portfolio_reserves(db, portfolio.id)
        assert asset_res[asset_btc.id] == Decimal("700.00")
        assert asset_res[asset_eth.id] == Decimal("300.00")
        assert global_res == Decimal("0.00")

    def test_clear_remaining_reserve(self, db, user, portfolio, asset_btc):
        payload = StrategySetRequest(
            items=[StrategyItemCreate(asset_id=asset_btc.id, percentage=Decimal("100"))]
        )
        set_strategy(db, user.user_id, portfolio.id, payload)
        deposit_strategy_budget(db, user.user_id, portfolio.id, amount=Decimal("250.00"))

        # Borramos/liberamos la reserva que queda en BTC
        manage_payload = StrategyReserveManageRequest(
            action="CLEAR",
            source_asset_id=asset_btc.id,
        )
        txns = reallocate_reserves(db, user.user_id, portfolio.id, manage_payload)
        assert len(txns) == 1
        assert txns[0].type == "WITHDRAW"
        assert txns[0].asset_id == asset_btc.id
        assert txns[0].amount == Decimal("250.00")

        asset_res, global_res = get_portfolio_reserves(db, portfolio.id)
        assert asset_res[asset_btc.id] == Decimal("0.00")

