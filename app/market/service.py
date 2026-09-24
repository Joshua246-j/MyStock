from typing import Dict, Any, List
from app.market.providers.base import MarketDataProvider
from app.market.providers.yfinance_provider import YFinanceProvider
from app.market.providers.stooq_provider import StooqProvider
from app.db.cache import get_cache, set_cache
from app.market.symbol_resolver import resolve_symbol
from app.db.database import SessionLocal
from app.db.models import UserSettings
import pandas as pd
from app.analysis.technical import calculate_technical_indicators

class MarketDataService:
    def __init__(self, provider: MarketDataProvider = None, fallback_provider: MarketDataProvider = None):
        self.provider = provider or YFinanceProvider()
        self.fallback_provider = fallback_provider or StooqProvider()

    def _get_cache_ttl(self) -> int:
        with SessionLocal() as db:
            settings_record = db.query(UserSettings).first()
            if settings_record and settings_record.settings:
                return settings_record.settings.get("cache_ttl", 300)
        return 300

    def _get_with_cache(self, key_prefix: str, symbol: str, fetch_func_name: str, **kwargs):
        res = resolve_symbol(symbol)
        if not res["valid"]:
            return {"success": False, "error": "Invalid symbol format"}
            
        resolved_symbol = res["resolved_symbol"]
        cache_key = f"{key_prefix}_{resolved_symbol}_{str(kwargs)}"
        
        cached_data = get_cache(cache_key)
        if cached_data:
            cached_data["status"] = "CACHED"
            return cached_data
            
        ttl = self._get_cache_ttl()
        
        # Primary provider
        primary_func = getattr(self.provider, fetch_func_name)
        data = primary_func(resolved_symbol, **kwargs)
        
        # Fallback provider if primary fails
        if isinstance(data, dict) and not data.get("success"):
            fallback_func = getattr(self.fallback_provider, fetch_func_name)
            fallback_data = fallback_func(resolved_symbol, **kwargs)
            if isinstance(fallback_data, dict) and fallback_data.get("success"):
                data = fallback_data
        elif isinstance(data, list) and not data:
            fallback_func = getattr(self.fallback_provider, fetch_func_name)
            fallback_data = fallback_func(resolved_symbol, **kwargs)
            if fallback_data:
                data = fallback_data

        if (isinstance(data, dict) and data.get("success")) or (isinstance(data, list) and data):
            if isinstance(data, dict):
                data["exchange"] = res["exchange"]
                data["market"] = res["market"]
            set_cache(cache_key, data, ttl_seconds=ttl, source=data.get("source", "unknown") if isinstance(data, dict) else "unknown")
        return data

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return self._get_with_cache("quote", symbol, "get_quote")

    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
        return self._get_with_cache("history", symbol, "get_history", period=period, interval=interval)

    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        return self._get_with_cache("profile", symbol, "get_company_profile")

    def get_financials(self, symbol: str) -> Dict[str, Any]:
        return self._get_with_cache("financials", symbol, "get_financials")

    def get_news(self, symbol: str) -> List[Dict[str, Any]]:
        # News returns a list, handled slightly differently
        res = resolve_symbol(symbol)
        if not res["valid"]:
            return []
        resolved_symbol = res["resolved_symbol"]
        cache_key = f"news_{resolved_symbol}"
        
        cached_data = get_cache(cache_key)
        if cached_data:
            return cached_data
            
        news = self.provider.get_news(resolved_symbol)
        if not news:
            news = self.fallback_provider.get_news(resolved_symbol)
        
        if news:
            set_cache(cache_key, news, ttl_seconds=self._get_cache_ttl(), source="yfinance")
        return news

    def get_technical_analysis(self, symbol: str, period: str = "6mo") -> Dict[str, Any]:
        history = self.get_history(symbol, period=period)
        if not history.get("success") or not history.get("data"):
            return {"success": False, "error": "Insufficient history for technical analysis"}
        
        df = pd.DataFrame(history["data"])
        return calculate_technical_indicators(df)

# Singleton instance
market_service = MarketDataService()
