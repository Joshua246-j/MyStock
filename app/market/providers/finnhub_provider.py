import httpx
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from app.market.providers.base import MarketDataProvider
import os
import logging

logger = logging.getLogger(__name__)

class FinnhubProvider(MarketDataProvider):
    supports_company_news = True
    """
    Provides market data using the Finnhub API.
    Requires FINNHUB_API_KEY environment variable.
    """
    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self):
        self.api_key = os.getenv("FINNHUB_API_KEY", "")
        self.source_name = "Finnhub"

    def _request(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self.api_key:
            return {"success": False, "error": "Finnhub API key not configured", "source": self.source_name}
        
        url = f"{self.BASE_URL}{endpoint}"
        params = {"token": self.api_key}
        params.update(kwargs)
        
        try:
            # We use a synchronous request here to align with the current architecture, 
            # though an async client is recommended for future refactoring.
            response = httpx.get(url, params=params, timeout=10.0)
            if response.status_code == 429:
                return {"success": False, "error": "Finnhub rate limit exceeded", "source": self.source_name}
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Finnhub API error for {endpoint}: {e}")
            return {"success": False, "error": str(e), "source": self.source_name}

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        data = self._request("/quote", symbol=symbol)
        if isinstance(data, dict) and "c" in data and data["c"] is not None:
            return {
                "success": True,
                "symbol": symbol,
                "price": data["c"],
                "change": data["d"],
                "change_percent": data["dp"],
                "high": data["h"],
                "low": data["l"],
                "open": data["o"],
                "previous_close": data["pc"],
                "source": self.source_name
            }
        return {"success": False, "error": data.get("error", "Invalid response"), "source": self.source_name}

    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
        # Approximate period mapping to timestamp
        now = datetime.now(timezone.utc)
        if period == "1mo":
            start = now - timedelta(days=30)
        elif period == "3mo":
            start = now - timedelta(days=90)
        elif period == "6mo":
            start = now - timedelta(days=180)
        elif period == "1y":
            start = now - timedelta(days=365)
        else:
            start = now - timedelta(days=30)

        res = "D" if interval in ["1d", "1wk", "1mo"] else "60" # Simplify interval mapping
        
        data = self._request("/stock/candle", symbol=symbol, resolution=res, **{"from": int(start.timestamp()), "to": int(now.timestamp())})
        
        if isinstance(data, dict) and data.get("s") == "ok":
            formatted_data = []
            for i in range(len(data["c"])):
                formatted_data.append({
                    "Date": datetime.fromtimestamp(data["t"][i]).strftime('%Y-%m-%d'),
                    "Open": data["o"][i],
                    "High": data["h"][i],
                    "Low": data["l"][i],
                    "Close": data["c"][i],
                    "Volume": data["v"][i]
                })
            return {"success": True, "symbol": symbol, "data": formatted_data, "source": self.source_name}
            
        return {"success": False, "error": data.get("error", "No historical data available"), "source": self.source_name}

    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        data = self._request("/stock/profile2", symbol=symbol)
        if isinstance(data, dict) and data.get("name"):
            return {
                "success": True,
                "symbol": symbol,
                "name": data.get("name"),
                "sector": data.get("finnhubIndustry"),
                "industry": data.get("finnhubIndustry"),
                "market_cap": data.get("marketCapitalization", 0) * 1000000,
                "website": data.get("weburl"),
                "description": "N/A", # Finnhub profile doesn't include a long description
                "source": self.source_name
            }
        return {"success": False, "error": data.get("error", "Profile not found"), "source": self.source_name}

    def get_financials(self, symbol: str) -> Dict[str, Any]:
        data = self._request("/stock/metric", symbol=symbol, metric="all")
        if isinstance(data, dict) and "metric" in data:
            metrics = data["metric"]
            return {
                "success": True,
                "symbol": symbol,
                "metrics": {
                    "pe_ratio": metrics.get("peExclExtraTTM") or metrics.get("peBasicExclExtraTTM"),
                    "eps": metrics.get("epsTTM"),
                    "dividend_yield": metrics.get("dividendYieldIndicatedAnnual"),
                    "52_week_high": metrics.get("52WeekHigh"),
                    "52_week_low": metrics.get("52WeekLow"),
                    "beta": metrics.get("beta")
                },
                "source": self.source_name
            }
        return {"success": False, "error": data.get("error", "Financials not found"), "source": self.source_name}

    def get_balance_sheet(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported in Finnhub free tier", "source": self.source_name}

    def get_cash_flow(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported in Finnhub free tier", "source": self.source_name}

    def get_news(self, symbol: str) -> List[Dict[str, Any]]:
        # Get news for the past 7 days
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        data = self._request("/company-news", symbol=symbol, **{"from": from_date, "to": to_date})
        
        if isinstance(data, list):
            formatted = []
            for item in data[:10]: # Return top 10
                formatted.append({
                    "title": item.get("headline"),
                    "publisher": item.get("source"),
                    "url": item.get("url"),
                    "published_at": datetime.fromtimestamp(item.get("datetime"), timezone.utc).isoformat() if item.get("datetime") else None,
                    "summary": item.get("summary"),
                    "image": item.get("image") or None,
                    "ticker": symbol,
                    "related_tickers": [str(symbol).upper()],
                })
            return formatted
        return []

    def get_dividends(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported in Finnhub free tier", "source": self.source_name}

    def get_splits(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported in Finnhub free tier", "source": self.source_name}
