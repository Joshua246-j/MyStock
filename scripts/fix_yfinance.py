import re

with open('app/market/providers/yfinance_provider.py', 'r') as f:
    content = f.read()

# First we need to restore the original file state by removing the `def _fetch():` and fixing indentation
import urllib.request
# Actually I have the text above, let's just write the proper script that does the whole thing.

original_text = '''import yfinance as yf
from typing import Dict, Any, List
from datetime import datetime
from app.market.providers.base import MarketDataProvider
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential
import random

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
]

class YFinanceProvider(MarketDataProvider):
    def __init__(self):
        yf.defaults = getattr(yf, "defaults", {})

    def _safe_execute(self, symbol: str, func, *args, **kwargs):
        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
        def _execute():
            if hasattr(yf, "defaults"):
                yf.defaults["user_agent"] = random.choice(USER_AGENTS)
            return func(*args, **kwargs)

        try:
            return _execute()
        except Exception as e:
            return {"success": False, "error": str(e), "symbol": symbol, "source": "yfinance", "status": "UNAVAILABLE"}

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        def _fetch():
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = getattr(info, "last_price", None)
            prev_close = getattr(info, "previous_close", None)
            
            if price is None or pd.isna(price):
                raise ValueError("Invalid quote data")
            
            change = price - prev_close if prev_close else 0
            change_percent = (change / prev_close * 100) if prev_close else 0

            return {
                "success": True,
                "symbol": symbol,
                "price": price,
                "change": change,
                "change_percent": change_percent,
                "volume": getattr(info, "last_volume", 0),
                "market_cap": getattr(info, "market_cap", 0),
                "currency": getattr(info, "currency", "USD"),
                "timestamp": datetime.now().isoformat(),
                "status": "LIVE" if price else "DELAYED",
                "source": "yfinance"
            }
        return self._safe_execute(symbol, _fetch)

    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
        def _fetch():
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)
            if hist.empty:
                raise ValueError("No historical data found")
            
            hist = hist.reset_index()
            if 'Date' in hist.columns:
                hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')
            elif 'Datetime' in hist.columns:
                hist['Datetime'] = hist['Datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')

            hist = hist.where(pd.notnull(hist), None)
            data = hist.to_dict(orient='records')
            return {
                "success": True,
                "symbol": symbol,
                "period": period,
                "interval": interval,
                "data": data,
                "source": "yfinance",
                "timestamp": datetime.now().isoformat()
            }
        return self._safe_execute(symbol, _fetch)

    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        def _fetch():
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return {
                "success": True,
                "symbol": symbol,
                "name": info.get("shortName", symbol),
                "sector": info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
                "description": info.get("longBusinessSummary", "No description available."),
                "website": info.get("website", ""),
                "country": info.get("country", ""),
                "source": "yfinance"
            }
        return self._safe_execute(symbol, _fetch)

    def get_financials(self, symbol: str) -> Dict[str, Any]:
        def _fetch():
            ticker = yf.Ticker(symbol)
            info = ticker.info
            metrics = {
                "trailingPE": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "priceToBook": info.get("priceToBook"),
                "dividendYield": info.get("dividendYield"),
                "returnOnEquity": info.get("returnOnEquity"),
                "debtToEquity": info.get("debtToEquity"),
                "revenueGrowth": info.get("revenueGrowth"),
                "ebitda": info.get("ebitda"),
                "freeCashflow": info.get("freeCashflow"),
                "grossMargins": info.get("grossMargins"),
                "operatingMargins": info.get("operatingMargins"),
                "netIncomeToCommon": info.get("netIncomeToCommon"),
            }
            metrics = {k: v for k, v in metrics.items() if v is not None}
            return {
                "success": True,
                "symbol": symbol,
                "metrics": metrics,
                "source": "yfinance",
                "retrieved_at": datetime.now().isoformat()
            }
        return self._safe_execute(symbol, _fetch)

    def get_balance_sheet(self, symbol: str) -> Dict[str, Any]:
        def _fetch():
            ticker = yf.Ticker(symbol)
            bs = ticker.balance_sheet
            if bs.empty:
                raise ValueError("No balance sheet found")
            bs = bs.where(pd.notnull(bs), None)
            bs.columns = [c.strftime('%Y-%m-%d') if hasattr(c, 'strftime') else str(c) for c in bs.columns]
            return {"success": True, "symbol": symbol, "data": bs.to_dict(), "source": "yfinance"}
        return self._safe_execute(symbol, _fetch)

    def get_cash_flow(self, symbol: str) -> Dict[str, Any]:
        def _fetch():
            ticker = yf.Ticker(symbol)
            cf = ticker.cashflow
            if cf.empty:
                raise ValueError("No cash flow found")
            cf = cf.where(pd.notnull(cf), None)
            cf.columns = [c.strftime('%Y-%m-%d') if hasattr(c, 'strftime') else str(c) for c in cf.columns]
            return {"success": True, "symbol": symbol, "data": cf.to_dict(), "source": "yfinance"}
        return self._safe_execute(symbol, _fetch)

    def get_news(self, symbol: str) -> List[Dict[str, Any]]:
        def _fetch():
            ticker = yf.Ticker(symbol)
            news = ticker.news
            formatted_news = []
            for item in news:
                formatted_news.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "publisher": item.get("publisher", ""),
                    "published_at": datetime.fromtimestamp(item.get("providerPublishTime", 0)).isoformat() if item.get("providerPublishTime") else None,
                    "retrieved_at": datetime.now().isoformat(),
                    "ticker": symbol
                })
            return formatted_news
        res = self._safe_execute(symbol, _fetch)
        if isinstance(res, dict) and not res.get("success", True):
            return []
        return res

    def get_dividends(self, symbol: str) -> Dict[str, Any]:
        def _fetch():
            ticker = yf.Ticker(symbol)
            divs = ticker.dividends
            if divs.empty:
                raise ValueError("No dividends found")
            divs.index = divs.index.strftime('%Y-%m-%d')
            return {"success": True, "symbol": symbol, "data": divs.to_dict(), "source": "yfinance"}
        return self._safe_execute(symbol, _fetch)

    def get_splits(self, symbol: str) -> Dict[str, Any]:
        def _fetch():
            ticker = yf.Ticker(symbol)
            splits = ticker.splits
            if splits.empty:
                raise ValueError("No splits found")
            splits.index = splits.index.strftime('%Y-%m-%d')
            return {"success": True, "symbol": symbol, "data": splits.to_dict(), "source": "yfinance"}
        return self._safe_execute(symbol, _fetch)
'''

with open('app/market/providers/yfinance_provider.py', 'w') as f:
    f.write(original_text)
