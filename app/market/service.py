from typing import Dict, Any, List, Callable, Optional
from app.market.providers.base import MarketDataProvider
from app.market.providers.yfinance_provider import YFinanceProvider
from app.market.providers.finnhub_provider import FinnhubProvider
from app.market.providers.stooq_provider import StooqProvider
from app.market.providers.finviz_provider import FinvizProvider
from app.market.providers.yahoo_api_provider import YahooApiProvider
from app.db.cache import CacheInterface, default_cache
from app.market.symbol_resolver import resolve_symbol
import pandas as pd
from app.analysis.technical import calculate_technical_indicators
import logging

logger = logging.getLogger("stockrag.market")

class MarketDataService:
    def __init__(
        self,
        provider: Optional[MarketDataProvider] = None,
        fallback_providers: Optional[List[MarketDataProvider]] = None,
        cache: Optional[CacheInterface] = None,
        settings_provider: Optional[Callable[[], Dict[str, Any]]] = None
    ):
        self.provider = provider or YFinanceProvider()
        self.fallback_providers = fallback_providers or [FinnhubProvider(), YahooApiProvider(), StooqProvider(), FinvizProvider()]
        self.cache = cache or default_cache
        self.settings_provider = settings_provider or self._default_settings_provider

    def _default_settings_provider(self) -> Dict[str, Any]:
        from app.db.database import SessionLocal
        from app.db.models import UserSettings
        with SessionLocal() as db:
            settings_record = db.query(UserSettings).first()
            if settings_record and settings_record.settings:
                return settings_record.settings
        return {}

    def _get_cache_ttl(self) -> int:
        settings = self.settings_provider()
        return settings.get("cache_ttl", 300)

    def _get_with_cache(self, key_prefix: str, symbol: str, fetch_func_name: str, **kwargs):
        res = resolve_symbol(symbol)
        if not res["valid"]:
            return {"success": False, "error": "Invalid symbol format"}
            
        resolved_symbol = res["resolved_symbol"]
        cache_key = f"{key_prefix}_{resolved_symbol}_{str(kwargs)}"
        
        cached_data = self.cache.get(cache_key)
        if cached_data:
            cached_data["status"] = "CACHED"
            return cached_data
            
        ttl = self._get_cache_ttl()
        
        errors = []
        
        # Primary provider
        primary_func = getattr(self.provider, fetch_func_name)
        try:
            data = primary_func(resolved_symbol, **kwargs)
        except Exception as exc:
            logger.warning("market_provider_failed", extra={"provider": type(self.provider).__name__, "operation": fetch_func_name, "reason": str(exc)})
            data = {"success": False, "error": f"{type(self.provider).__name__} could not complete the {fetch_func_name.replace('get_', '')} request.", "source": type(self.provider).__name__}
        
        if isinstance(data, dict) and not data.get("success"):
            if data.get("error"):
                errors.append(data.get("error"))
        
        # Fallback providers if primary fails
        if isinstance(data, dict) and not data.get("success"):
            for fb_provider in self.fallback_providers:
                fallback_func = getattr(fb_provider, fetch_func_name)
                try:
                    fallback_data = fallback_func(resolved_symbol, **kwargs)
                except Exception as exc:
                    logger.warning("market_fallback_failed", extra={"provider": type(fb_provider).__name__, "operation": fetch_func_name, "reason": str(exc)})
                    fallback_data = {"success": False, "error": f"{type(fb_provider).__name__} could not complete the {fetch_func_name.replace('get_', '')} request.", "source": type(fb_provider).__name__}
                
                if isinstance(fallback_data, dict) and fallback_data.get("success"):
                    data = fallback_data
                    break
                elif isinstance(fallback_data, dict) and fallback_data.get("error"):
                    if not fallback_data.get("error").startswith("Not supported"):
                        errors.append(fallback_data.get("error"))
                    if fallback_data.get("error").startswith("Not supported"):
                        continue # Try the next fallback
            
            # If still not successful, format the error nicely
            if not data.get("success"):
                error_details = " | ".join(errors)
                data = {
                    "success": False,
                    "error": f"No {fetch_func_name.replace('get_', '').replace('_', ' ')} data is available for {resolved_symbol} across all configured providers. Details: {error_details}",
                    "source": "unavailable",
                    "status": "UNAVAILABLE",
                }
        elif isinstance(data, list) and not data:
            for fb_provider in self.fallback_providers:
                fallback_func = getattr(fb_provider, fetch_func_name)
                fallback_data = fallback_func(resolved_symbol, **kwargs)
                if fallback_data:
                    data = fallback_data
                    break

        if (isinstance(data, dict) and data.get("success")) or (isinstance(data, list) and data):
            if isinstance(data, dict):
                data["exchange"] = res["exchange"]
                data["market"] = res["market"]
            self.cache.set(cache_key, data, ttl_seconds=ttl, source=data.get("source", "unknown") if isinstance(data, dict) else "unknown")
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
        result = self.get_news_result(symbol)
        return result.get("news", [])

    def get_news_result(self, symbol: str) -> Dict[str, Any]:
        # News returns a list, handled slightly differently
        res = resolve_symbol(symbol)
        if not res["valid"]:
            return {"success": False, "news": [], "error": "Invalid symbol format", "data_status": "UNAVAILABLE"}
        resolved_symbol = res["resolved_symbol"]
        cache_key = f"news_{resolved_symbol}"
        
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return {"success": True, "news": cached_data, "source": "cached", "data_status": "CACHED"}
            
        try:
            news = self.provider.get_news(resolved_symbol)
        except Exception as exc:
            logger.warning("market_news_provider_failed", extra={"provider": type(self.provider).__name__, "reason": str(exc)})
            news = []
        source = type(self.provider).__name__
        if not news:
            for fb_provider in self.fallback_providers:
                try:
                    news = fb_provider.get_news(resolved_symbol)
                    if news:
                        source = type(fb_provider).__name__
                        break
                except Exception as exc:
                    logger.warning("market_news_fallback_failed", extra={"provider": type(fb_provider).__name__, "reason": str(exc)})
                    news = []
        
        if news:
            self.cache.set(cache_key, news, ttl_seconds=self._get_cache_ttl(), source=source)
            return {"success": True, "news": news, "source": source, "data_status": "UNVERIFIED_FRESHNESS"}
        return {"success": False, "news": [], "source": source, "data_status": "UNAVAILABLE", "error": "No news was returned by the configured providers."}

    def get_technical_analysis(self, symbol: str, period: str = "6mo") -> Dict[str, Any]:
        history = self.get_history(symbol, period=period)
        if not history.get("success") or not history.get("data"):
            return {"success": False, "error": "Insufficient history for technical analysis"}
        
        df = pd.DataFrame(history["data"])
        return calculate_technical_indicators(df)

    def check_provider(self, symbol: str = "AAPL") -> Dict[str, Any]:
        """Perform an uncached provider check for the live health endpoint."""
        try:
            primary = self.provider.get_quote(symbol)
        except Exception as exc:
            primary = {"success": False, "error": str(exc)}
        if isinstance(primary, dict) and primary.get("success"):
            return primary
        for fb_provider in self.fallback_providers:
            try:
                fallback = fb_provider.get_quote(symbol)
            except Exception as exc:
                continue
            if isinstance(fallback, dict) and fallback.get("success"):
                return fallback
        return {"success": False, "error": "No market data provider is reachable"}

