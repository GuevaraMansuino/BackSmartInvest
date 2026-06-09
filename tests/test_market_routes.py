import asyncio
import time
from decimal import Decimal

import pytest

import routes.market as market_routes


@pytest.fixture(autouse=True)
def reset_featured_cache(monkeypatch):
    monkeypatch.setattr(market_routes, "_featured_cache", None)
    monkeypatch.setattr(market_routes, "_featured_cache_updated_at", None)
    monkeypatch.setattr(market_routes, "_featured_refresh_task", None)


@pytest.mark.asyncio
async def test_fetch_featured_asset_returns_market_values(monkeypatch):
    def fake_get_detailed_info(symbol: str, ticker_variations=None):
        return {
            "price": Decimal("100"),
            "prev_close": Decimal("80"),
        }

    monkeypatch.setattr(
        market_routes.market_data_service,
        "get_detailed_info",
        fake_get_detailed_info,
    )

    asset = await market_routes._fetch_featured_asset(
        {"symbol": "SPY", "quote_symbol": "SPY.BA", "name": "SPY", "currency": "ARS"}
    )

    assert asset.symbol == "SPY"
    assert asset.quote_symbol == "SPY.BA"
    assert asset.currency == "ARS"
    assert asset.instrument_type == "CEDEAR"
    assert asset.price == Decimal("100")
    assert asset.change_value == Decimal("20")
    assert asset.change_percent == Decimal("25")


@pytest.mark.asyncio
async def test_fetch_featured_asset_returns_zero_on_timeout(monkeypatch):
    original_timeout = market_routes.FEATURED_FETCH_TIMEOUT_SECONDS

    def slow_get_detailed_info(symbol: str, ticker_variations=None):
        time.sleep(0.05)
        return {
            "price": Decimal("100"),
            "prev_close": Decimal("90"),
        }

    monkeypatch.setattr(
        market_routes.market_data_service,
        "get_detailed_info",
        slow_get_detailed_info,
    )
    monkeypatch.setattr(market_routes, "FEATURED_FETCH_TIMEOUT_SECONDS", 0.01)

    try:
        asset = await market_routes._fetch_featured_asset(
            {"symbol": "NVDA", "quote_symbol": "NVDA.BA", "name": "NVDA", "currency": "ARS"}
        )
    finally:
        monkeypatch.setattr(market_routes, "FEATURED_FETCH_TIMEOUT_SECONDS", original_timeout)

    assert asset.symbol == "NVDA"
    assert asset.quote_symbol == "NVDA.BA"
    assert asset.price == Decimal("0")
    assert asset.change_percent is None


@pytest.mark.asyncio
async def test_refresh_featured_cache_preserves_symbol_order(monkeypatch):
    assets_meta = [
        {"symbol": "AAA", "quote_symbol": "AAA.BA", "name": "Alpha", "currency": "ARS"},
        {"symbol": "BBB", "quote_symbol": "BBB.BA", "name": "Beta", "currency": "ARS"},
    ]

    def fake_get_detailed_info(symbol: str, ticker_variations=None):
        return {
            "price": Decimal("1"),
            "prev_close": Decimal("1"),
        }

    monkeypatch.setattr(market_routes, "FEATURED_ASSETS", assets_meta)
    monkeypatch.setattr(
        market_routes.market_data_service,
        "get_detailed_info",
        fake_get_detailed_info,
    )

    await market_routes._refresh_featured_cache()

    assert [item.symbol for item in market_routes._featured_cache] == ["AAA", "BBB"]


def test_merge_featured_assets_preserves_existing_prices_when_refresh_fails():
    current_assets = [
        market_routes.FeaturedAsset(symbol="SPY", quote_symbol="SPY.BA", name="SPY", price=Decimal("701.66")),
        market_routes.FeaturedAsset(symbol="NVDA", quote_symbol="NVDA.BA", name="NVDA", price=Decimal("198.35")),
    ]
    refreshed_assets = [
        market_routes.FeaturedAsset(symbol="SPY", quote_symbol="SPY.BA", name="SPY", price=Decimal("0")),
        market_routes.FeaturedAsset(symbol="NVDA", quote_symbol="NVDA.BA", name="NVDA", price=Decimal("0")),
    ]

    merged_assets = market_routes._merge_featured_assets(current_assets, refreshed_assets)

    assert [asset.price for asset in merged_assets] == [Decimal("701.66"), Decimal("198.35")]


@pytest.mark.asyncio
async def test_get_featured_assets_returns_fallback_immediately(monkeypatch):
    created_tasks: list[asyncio.Task] = []

    original_create_task = asyncio.create_task

    def track_task(coro):
        task = original_create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(asyncio, "create_task", track_task)

    items = await market_routes.get_featured_assets()

    assert [item.price for item in items] == [Decimal("0")] * len(market_routes.FEATURED_ASSETS)
    assert all(item.instrument_type == "CEDEAR" for item in items)
    assert len(created_tasks) == 1

    for task in created_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
