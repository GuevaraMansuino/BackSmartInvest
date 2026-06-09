from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from services.market_data_service import MarketDataService


@pytest.fixture
def service():
    MarketDataService._instance = None
    return MarketDataService()


def test_singleton(service):
    s2 = MarketDataService()
    assert service is s2


@patch("yfinance.Ticker")
def test_get_price_success(mock_ticker, service):
    mock_instance = MagicMock()
    mock_instance.history.return_value = pd.DataFrame({"Close": [149.0, 150.5]})
    mock_ticker.return_value = mock_instance

    price = service.get_price("AAPL")

    assert price == Decimal("150.5")
    assert mock_ticker.called


@patch("yfinance.Ticker")
def test_get_price_cache(mock_ticker, service):
    mock_instance = MagicMock()
    mock_instance.history.return_value = pd.DataFrame({"Close": [99.0, 100.0]})
    mock_ticker.return_value = mock_instance

    p1 = service.get_price("MSFT")
    p2 = service.get_price("MSFT")

    assert p1 == p2 == Decimal("100.0")
    assert mock_ticker.call_count == 1


@patch("yfinance.Ticker")
def test_get_price_crypto_mapping(mock_ticker, service):
    mock_instance = MagicMock()
    mock_instance.history.return_value = pd.DataFrame({"Close": [59000.0, 60000.0]})
    mock_ticker.return_value = mock_instance

    price = service.get_price("BTC")

    mock_ticker.assert_any_call("BTC-USD", session=service._session)
    assert price == Decimal("60000.0")


@patch("yfinance.Ticker")
def test_get_price_not_found(mock_ticker, service):
    mock_instance = MagicMock()
    mock_instance.history.return_value = pd.DataFrame({"Close": []})
    mock_ticker.return_value = mock_instance

    price = service.get_price("UNKNOWN")

    assert price is None
