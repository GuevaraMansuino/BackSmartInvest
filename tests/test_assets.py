"""
Tests de integracion para el CRUD de assets.
Usa SQLite en memoria.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database import Base
from models import entities  # noqa: F401
from schemas.asset import AssetCreate, AssetUpdate
from services.asset_service import (
    create_asset,
    delete_asset,
    get_asset_by_id,
    get_asset_by_symbol,
    list_assets,
    update_asset,
    upsert_asset,
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


class TestCreateAsset:
    def test_creates_asset(self, db):
        asset = create_asset(db, AssetCreate(symbol="AAPL", name="Apple Inc."))
        assert asset.symbol == "AAPL"
        assert asset.name == "Apple Inc."

    def test_normalizes_symbol_to_uppercase(self, db):
        asset = create_asset(db, AssetCreate(symbol="aapl", name="Apple"))
        assert asset.symbol == "AAPL"

    def test_raises_on_duplicate_symbol(self, db):
        create_asset(db, AssetCreate(symbol="MSFT", name="Microsoft"))
        with pytest.raises(ValueError, match="already exists"):
            create_asset(db, AssetCreate(symbol="MSFT", name="Microsoft Corp"))


class TestListAssets:
    def test_returns_all_assets(self, db):
        create_asset(db, AssetCreate(symbol="BTC", name="Bitcoin"))
        create_asset(db, AssetCreate(symbol="ETH", name="Ethereum"))
        result = list_assets(db)
        assert len(result) == 2

    def test_filters_by_symbol(self, db):
        create_asset(db, AssetCreate(symbol="BTC", name="Bitcoin"))
        create_asset(db, AssetCreate(symbol="ETH", name="Ethereum"))
        result = list_assets(db, query="bt")
        assert len(result) == 1
        assert result[0].symbol == "BTC"

    def test_filters_by_name(self, db):
        create_asset(db, AssetCreate(symbol="SPY", name="S&P 500 ETF"))
        create_asset(db, AssetCreate(symbol="QQQ", name="Nasdaq-100 ETF"))
        result = list_assets(db, query="nasdaq")
        assert len(result) == 1
        assert result[0].symbol == "QQQ"

    def test_returns_empty_when_no_match(self, db):
        create_asset(db, AssetCreate(symbol="TSLA", name="Tesla"))
        result = list_assets(db, query="zzz")
        assert result == []


class TestGetAsset:
    def test_finds_existing_asset_by_symbol(self, db):
        create_asset(db, AssetCreate(symbol="NVDA", name="NVIDIA"))
        result = get_asset_by_symbol(db, "NVDA")
        assert result is not None
        assert result.symbol == "NVDA"

    def test_case_insensitive_lookup(self, db):
        create_asset(db, AssetCreate(symbol="NVDA", name="NVIDIA"))
        result = get_asset_by_symbol(db, "nvda")
        assert result is not None

    def test_returns_none_for_missing_symbol(self, db):
        result = get_asset_by_symbol(db, "UNKNOWN")
        assert result is None

    def test_finds_existing_asset_by_id(self, db):
        asset = create_asset(db, AssetCreate(symbol="META", name="Meta"))
        result = get_asset_by_id(db, asset.id)
        assert result is not None
        assert result.id == asset.id


class TestUpdateAsset:
    def test_updates_name(self, db):
        asset = create_asset(db, AssetCreate(symbol="BBD", name="Banco Bradesco"))
        updated = update_asset(db, asset, AssetUpdate(name="Banco Bradesco S.A."))
        assert updated.name == "Banco Bradesco S.A."
        assert updated.symbol == "BBD"

    def test_updates_symbol_and_normalizes_it(self, db):
        asset = create_asset(db, AssetCreate(symbol="meli", name="Mercado Libre"))
        updated = update_asset(db, asset, AssetUpdate(symbol="meli.ba"))
        assert updated.symbol == "MELI.BA"

    def test_raises_on_duplicate_symbol(self, db):
        create_asset(db, AssetCreate(symbol="AAPL", name="Apple"))
        asset = create_asset(db, AssetCreate(symbol="MSFT", name="Microsoft"))
        with pytest.raises(ValueError, match="already exists"):
            update_asset(db, asset, AssetUpdate(symbol="AAPL"))


class TestDeleteAsset:
    def test_deletes_asset(self, db):
        asset = create_asset(db, AssetCreate(symbol="KO", name="Coca-Cola"))
        delete_asset(db, asset)
        assert get_asset_by_id(db, asset.id) is None


class TestUpsertAsset:
    def test_creates_if_not_exists(self, db):
        asset = upsert_asset(db, "SOL", "Solana")
        assert asset.symbol == "SOL"

    def test_returns_existing_without_error(self, db):
        create_asset(db, AssetCreate(symbol="SOL", name="Solana"))
        asset = upsert_asset(db, "SOL", "Solana Duplicate")
        assert asset.symbol == "SOL"
