import yfinance as yf
from decimal import Decimal

def test_ticker(name):
    print(f"--- Probiendo {name} ---")
    try:
        t = yf.Ticker(name)
        info = t.fast_info
        print(f"Keys: {list(info.keys())}")
        price = info.get('lastPrice') or info.get('last_price') or info.get('regularMarketPrice')
        print(f"Price: {price}")
        return price
    except Exception as e:
        print(f"Error: {e}")
        return None

test_ticker("BTC-USD")
test_ticker("AAPL")
test_ticker("GGAL.BA")
