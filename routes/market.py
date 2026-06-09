import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter

from schemas.market import FeaturedAsset
from services.market_data_service import market_data_service

router = APIRouter(prefix="/api/market", tags=["market"])
logger = logging.getLogger(__name__)

FEATURED_ASSETS = [
    {"symbol": "SPY", "quote_symbol": "SPY.BA", "name": "SPDR S&P 500 ETF Trust", "currency": "ARS"},
    {"symbol": "NVDA", "quote_symbol": "NVDA.BA", "name": "NVIDIA Corporation", "currency": "ARS"},
    {"symbol": "MSFT", "quote_symbol": "MSFT.BA", "name": "Microsoft Corporation", "currency": "ARS"},
    {"symbol": "AMZN", "quote_symbol": "AMZN.BA", "name": "Amazon.com Inc.", "currency": "ARS"},
    {"symbol": "GOOGL", "quote_symbol": "GOOGL.BA", "name": "Alphabet Inc.", "currency": "ARS"},
]
FEATURED_REFRESH_INTERVAL = timedelta(minutes=5)
FEATURED_FETCH_TIMEOUT_SECONDS = 4.0
ZERO = Decimal("0")

_featured_cache: list[FeaturedAsset] | None = None
_featured_cache_updated_at: datetime | None = None
_featured_refresh_task: asyncio.Task | None = None


def _fallback_featured_assets() -> list[FeaturedAsset]:
    return [
        FeaturedAsset(
            symbol=asset["symbol"],
            quote_symbol=asset["quote_symbol"],
            name=asset["name"],
            price=ZERO,
            currency=asset["currency"],
            instrument_type="CEDEAR",
        )
        for asset in FEATURED_ASSETS
    ]


def _build_featured_asset(asset_meta: dict, info: dict | None) -> FeaturedAsset:
    if not info:
        return FeaturedAsset(
            symbol=asset_meta["symbol"],
            quote_symbol=asset_meta["quote_symbol"],
            name=asset_meta["name"],
            price=ZERO,
            currency=asset_meta["currency"],
            instrument_type="CEDEAR",
        )

    price = info["price"]
    prev_close = info.get("prev_close")
    change_percent = None
    change_value = None

    if prev_close and prev_close > 0:
        change_value = price - prev_close
        change_percent = (change_value / prev_close) * 100

    return FeaturedAsset(
        symbol=asset_meta["symbol"],
        quote_symbol=asset_meta["quote_symbol"],
        name=asset_meta["name"],
        price=price,
        currency=asset_meta["currency"],
        instrument_type="CEDEAR",
        change_percent=change_percent,
        change_value=change_value,
    )


def _merge_featured_assets(
    current_assets: list[FeaturedAsset] | None,
    refreshed_assets: list[FeaturedAsset],
) -> list[FeaturedAsset]:
    if not current_assets:
        return refreshed_assets

    current_by_symbol = {asset.symbol: asset for asset in current_assets}
    merged_assets: list[FeaturedAsset] = []

    for asset in refreshed_assets:
        current_asset = current_by_symbol.get(asset.symbol)
        if asset.price > 0 or current_asset is None or current_asset.price <= 0:
            merged_assets.append(asset)
            continue

        merged_assets.append(current_asset)

    return merged_assets


async def _fetch_featured_asset(asset_meta: dict) -> FeaturedAsset:
    try:
        info = await asyncio.wait_for(
            asyncio.to_thread(
                market_data_service.get_detailed_info,
                asset_meta["quote_symbol"],
                [asset_meta["quote_symbol"]],
            ),
            timeout=FEATURED_FETCH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.info("Featured asset refresh timed out for %s", asset_meta["quote_symbol"])
        info = None
    except Exception:
        logger.exception("Unexpected error refreshing featured asset %s", asset_meta["quote_symbol"])
        info = None

    return _build_featured_asset(asset_meta, info)


async def _refresh_featured_cache() -> None:
    global _featured_cache, _featured_cache_updated_at, _featured_refresh_task

    tasks = [_fetch_featured_asset(asset_meta) for asset_meta in FEATURED_ASSETS]
    refreshed_assets = list(await asyncio.gather(*tasks))
    _featured_cache = _merge_featured_assets(_featured_cache, refreshed_assets)
    _featured_cache_updated_at = datetime.now()
    _featured_refresh_task = None


async def warm_featured_cache() -> None:
    try:
        await _refresh_featured_cache()
    except Exception:
        logger.exception("Failed to warm featured asset cache")


def _featured_cache_is_fresh() -> bool:
    if _featured_cache_updated_at is None:
        return False
    return datetime.now() - _featured_cache_updated_at < FEATURED_REFRESH_INTERVAL


def _schedule_featured_refresh() -> None:
    global _featured_refresh_task

    if _featured_refresh_task is not None and not _featured_refresh_task.done():
        return

    _featured_refresh_task = asyncio.create_task(_refresh_featured_cache())


@router.get("/featured", response_model=list[FeaturedAsset])
async def get_featured_assets() -> list[FeaturedAsset]:
    global _featured_cache

    if _featured_cache is None:
        _featured_cache = _fallback_featured_assets()

    if not _featured_cache_is_fresh():
        _schedule_featured_refresh()

    return list(_featured_cache)
