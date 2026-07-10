import logging
import threading
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional

import httpx
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

_YF_CACHE_DIR = Path(__file__).resolve().parent.parent / "scratch" / "yfinance-cache"
_YF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
yf.set_tz_cache_location(str(_YF_CACHE_DIR))


class MarketDataService:
    _instance = None
    _lock = threading.Lock()

    _cache: Dict[str, tuple[dict, datetime]] = {}
    _cache_ttl = timedelta(minutes=10)

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MarketDataService, cls).__new__(cls)
                cls._instance._session = requests.Session()
                cls._instance._session.trust_env = False
            return cls._instance

    def get_price(self, symbol: str) -> Optional[Decimal]:
        info = self.get_detailed_info(symbol)
        return info.get("price") if info else None

    def get_detailed_info(
        self,
        symbol: str,
        ticker_variations: list[str] | None = None,
    ) -> Optional[dict]:
        symbol = symbol.upper().strip()
        cache_key = self._build_cache_key(symbol, ticker_variations)

        with self._lock:
            if cache_key in self._cache:
                data, timestamp = self._cache[cache_key]
                if datetime.now() - timestamp < self._cache_ttl:
                    return data

        variations = ticker_variations or self._default_ticker_variations(symbol)
        info = self._fetch_detailed_from_yahoo(variations)

        if info:
            with self._lock:
                self._cache[cache_key] = (info, datetime.now())

        return info

    def _build_cache_key(self, symbol: str, ticker_variations: list[str] | None) -> str:
        if not ticker_variations:
            return symbol
        return f"{symbol}|{'|'.join(ticker_variations)}"

    def _default_ticker_variations(self, symbol: str) -> list[str]:
        variations: list[str] = []
        if len(symbol) <= 4 and symbol in ["BTC", "ETH", "SOL", "USDT", "DAI"]:
            variations.append(f"{symbol}-USD")
        variations.append(f"{symbol}.BA")
        variations.append(symbol)
        return variations

    def _fetch_detailed_from_yahoo(self, variations: list[str]) -> Optional[dict]:
        for ticker_name in variations:
            direct_info = self._fetch_direct_yahoo_http(ticker_name)
            if direct_info:
                return direct_info

            try:
                ticker = yf.Ticker(ticker_name, session=self._session)
                history = ticker.history(period="5d", interval="1d", auto_adjust=False)
                if history.empty:
                    continue

                closes = history["Close"].dropna()
                if closes.empty:
                    continue

                price = Decimal(str(closes.iloc[-1]))
                prev_close = Decimal(str(closes.iloc[-2])) if len(closes) > 1 else None

                return {
                    "price": price,
                    "prev_close": prev_close,
                    "ticker_used": ticker_name,
                }
            except Exception as exc:
                logger.debug("Error en Yahoo para %s: %s", ticker_name, exc)
            stooq_info = self._fetch_detailed_from_stooq(ticker_name)
            if stooq_info:
                return stooq_info
        return None

    def _fetch_direct_yahoo_http(self, ticker_name: str) -> Optional[dict]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }
        urls = [
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_name}?interval=1d&range=5d",
            f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker_name}?interval=1d&range=5d",
        ]
        for url in urls:
            try:
                with httpx.Client(timeout=6.0, headers=headers, follow_redirects=True, trust_env=False) as client:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        result = data.get("chart", {}).get("result")
                        if result and len(result) > 0:
                            meta = result[0].get("meta", {})
                            price = meta.get("regularMarketPrice")
                            prev_close = meta.get("previousClose")
                            if price is not None and float(price) > 0:
                                return {
                                    "price": Decimal(str(price)),
                                    "prev_close": Decimal(str(prev_close)) if prev_close else None,
                                    "ticker_used": ticker_name,
                                }
            except Exception as exc:
                logger.debug("Direct Yahoo HTTP error for %s on %s: %s", ticker_name, url, exc)
        return None

    def _fetch_detailed_from_stooq(self, ticker_name: str) -> Optional[dict]:
        stooq_symbol = self._map_to_stooq_symbol(ticker_name)
        if stooq_symbol is None:
            return None

        try:
            with httpx.Client(timeout=10.0, trust_env=False, follow_redirects=True) as client:
                response = client.get(
                    "https://stooq.com/q/l/",
                    params={"s": stooq_symbol, "f": "sd2t2ohlcvn", "e": "json"},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.debug("Error en Stooq para %s: %s", ticker_name, exc)
            return None

        symbols = payload.get("symbols") or []
        if not symbols:
            return None

        quote = symbols[0]
        close = quote.get("close")
        if close in (None, ""):
            return None

        try:
            price = Decimal(str(close))
        except Exception:
            return None

        return {
            "price": price,
            "prev_close": None,
            "ticker_used": stooq_symbol,
        }

    def _map_to_stooq_symbol(self, ticker_name: str) -> str | None:
        if any(separator in ticker_name for separator in [".", "-"]):
            return None
        if not ticker_name.isalnum():
            return None
        return f"{ticker_name.lower()}.us"


market_data_service = MarketDataService()
