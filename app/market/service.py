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
from app.analysis.technical import calculate_technical_indicators, calculate_indicator_series
from app.market.validation import validate_ohlcv_rows
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
        self.fallback_providers = fallback_providers if fallback_providers is not None else [FinnhubProvider(), YahooApiProvider(), StooqProvider(), FinvizProvider()]
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

    def _get_with_cache(self, key_prefix: str, symbol: str, fetch_func_name: str, force_refresh: bool = False, **kwargs):
        res = resolve_symbol(symbol)
        if not res["valid"]:
            return {"success": False, "error": "Invalid symbol format"}
            
        resolved_symbol = res["resolved_symbol"]
        cache_key = f"{key_prefix}_{resolved_symbol}_{str(kwargs)}"
        
        cached_data = None if force_refresh else self.cache.get(cache_key)
        if cached_data:
            cached_data["status"] = "CACHED"
            return cached_data
            
        ttl = self._get_cache_ttl()
        
        errors = []
        used_local_stale_history = False
        
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

        if fetch_func_name == "get_history" and isinstance(data, dict) and not data.get("success"):
            try:
                from app.market.storage import read_price_bars
                stale = read_price_bars(resolved_symbol, kwargs.get("interval", "1d"), kwargs.get("period", "1mo"))
                if stale.get("success"):
                    stale.update({"exchange": res["exchange"], "market": res["market"], "status": "STALE"})
                    data = stale
                    used_local_stale_history = True
            except Exception:
                logger.exception("stored_history_read_failed", extra={"symbol": resolved_symbol})

        if fetch_func_name == "get_history" and isinstance(data, dict) and data.get("success") and not used_local_stale_history:
            raw_data = data.get("data")
            if isinstance(raw_data, list):
                cleaned_data = []
                for b in raw_data:
                    if isinstance(b, dict):
                        o = b.get("Open") if "Open" in b else b.get("open")
                        h = b.get("High") if "High" in b else b.get("high")
                        l = b.get("Low") if "Low" in b else b.get("low")
                        c = b.get("Close") if "Close" in b else b.get("close")
                        if None not in (o, h, l, c):
                            cleaned_data.append(b)
                data["data"] = cleaned_data
            rows, validation_error = validate_ohlcv_rows(data.get("data"))
            if validation_error:
                logger.error("market_history_validation_failed", extra={"symbol": resolved_symbol, "provider": data.get("source", "unknown"), "reason": validation_error})
                return {"success": False, "error": f"Historical data was rejected: {validation_error}", "source": data.get("source", "unknown"), "status": "INVALID_DATA"}
            try:
                from app.market.storage import store_price_bars
                store_price_bars(
                    resolved_symbol,
                    kwargs.get("interval", "1d"),
                    str(data.get("source", "unknown")),
                    str(data.get("data_status", "UNKNOWN")),
                    rows,
                )
            except Exception:
                logger.exception("market_history_persistence_failed", extra={"symbol": resolved_symbol, "source": data.get("source", "unknown")})
                return {"success": False, "error": "Validated historical data could not be saved to the local database.", "source": data.get("source", "unknown"), "status": "STORAGE_UNAVAILABLE"}

        if fetch_func_name == "get_financials" and isinstance(data, dict):
            from app.market.storage import read_fundamentals, store_fundamentals
            if data.get("success") and data.get("metrics"):
                try:
                    store_fundamentals(resolved_symbol, str(data.get("source", "unknown")), data["metrics"], str(data.get("data_status", "UNVERIFIED_FRESHNESS")))
                except Exception:
                    logger.exception("fundamentals_persistence_failed", extra={"symbol": resolved_symbol})
                    return {"success": False, "error": "Fundamentals could not be saved to the local database.", "source": data.get("source", "unknown")}
            elif not data.get("success"):
                try:
                    stored = read_fundamentals(resolved_symbol)
                    if stored.get("success"):
                        stored["exchange"], stored["market"] = res["exchange"], res["market"]
                        return stored
                except Exception:
                    logger.exception("stored_fundamentals_read_failed", extra={"symbol": resolved_symbol})

        if used_local_stale_history:
            return data

        if (isinstance(data, dict) and data.get("success")) or (isinstance(data, list) and data):
            if isinstance(data, dict):
                data["exchange"] = res["exchange"]
                data["market"] = res["market"]
                if data.get("success") and not data.get("status") and data.get("data_status"):
                    data["status"] = data["data_status"]
            self.cache.set(cache_key, data, ttl_seconds=ttl, source=data.get("source", "unknown") if isinstance(data, dict) else "unknown")
        return data

    def get_quote(self, symbol: str, refresh: bool = False) -> Dict[str, Any]:
        return self._get_with_cache("quote", symbol, "get_quote", force_refresh=refresh)

    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d", refresh: bool = False, auto_adjust: bool = True) -> Dict[str, Any]:
        result = self._get_with_cache("history", symbol, "get_history", force_refresh=refresh, period=period, interval=interval, auto_adjust=auto_adjust)
        if isinstance(result, dict) and result.get("success") and result.get("data"):
            result["indicators"] = calculate_indicator_series(pd.DataFrame(result["data"]))
        return result

    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        return self._get_with_cache("profile", symbol, "get_company_profile")

    def get_financials(self, symbol: str, refresh: bool = False) -> Dict[str, Any]:
        return self._get_with_cache("financials", symbol, "get_financials", force_refresh=refresh)

    def get_news(self, symbol: str) -> List[Dict[str, Any]]:
        result = self.get_news_result(symbol)
        return result.get("news", [])

    def get_news_result(self, symbol: str, refresh: bool = False) -> Dict[str, Any]:
        # News returns a list, handled slightly differently
        res = resolve_symbol(symbol)
        if not res["valid"]:
            return {"success": False, "news": [], "error": "Invalid symbol format", "data_status": "UNAVAILABLE"}
        resolved_symbol = res["resolved_symbol"]
        cache_key = f"news_v2_{resolved_symbol}"
        
        cached_data = None if refresh else self.cache.get(cache_key)
        if cached_data:
            try:
                from app.market.storage import normalize_news_items, store_news
                cached_data = normalize_news_items(cached_data)
                cached_data = [item for item in cached_data
                               if resolved_symbol in {str(value).strip().upper() for value in item.get("related_tickers", [])}]
                store_news(resolved_symbol, cached_data)
            except Exception:
                logger.exception("cached_news_persistence_failed", extra={"symbol": resolved_symbol})
            if cached_data:
                return {"success": True, "news": cached_data, "source": "cached", "data_status": "CACHED"}
            
        try:
            news = self.provider.get_news(resolved_symbol) if getattr(self.provider, "supports_company_news", True) else []
        except Exception as exc:
            logger.warning("market_news_provider_failed", extra={"provider": type(self.provider).__name__, "reason": str(exc)})
            news = []
        source = type(self.provider).__name__
        if not news:
            for fb_provider in self.fallback_providers:
                if not getattr(fb_provider, "supports_company_news", True):
                    continue
                try:
                    news = fb_provider.get_news(resolved_symbol)
                    if news:
                        source = type(fb_provider).__name__
                        break
                except Exception as exc:
                    logger.warning("market_news_fallback_failed", extra={"provider": type(fb_provider).__name__, "reason": str(exc)})
                    news = []

        if not news and getattr(self, "enable_rss_fallback", True):
            provider_mod = getattr(self.provider, "__module__", "")
            if provider_mod.startswith("app.market"):
                try:
                    from app.market.news_providers import fetch_ticker_targeted_news
                    targeted_news = fetch_ticker_targeted_news(resolved_symbol, limit=25)
                    if targeted_news:
                        news = targeted_news
                        source = "MultiSourceRSS"
                except Exception as exc:
                    logger.info("market_news_targeted_rss_failed", extra={"symbol": resolved_symbol, "reason": str(exc)})

        try:
            from app.market.storage import normalize_news_items
            news = normalize_news_items(news)
        except Exception:
            logger.exception("news_normalization_failed", extra={"symbol": resolved_symbol, "source": source})
            news = []
        if news:
            try:
                from app.market.storage import store_news
                store_news(resolved_symbol, news)
            except Exception:
                logger.exception("news_persistence_failed", extra={"symbol": resolved_symbol, "source": source})
            self.cache.set(cache_key, news, ttl_seconds=self._get_cache_ttl(), source=source)
            return {"success": True, "news": news, "source": source, "data_status": "UNVERIFIED_FRESHNESS"}
        try:
            from app.market.storage import read_news
            stored_news = read_news(resolved_symbol)
            if stored_news:
                return {"success": True, "news": stored_news, "source": "sqlite", "data_status": "STALE"}
        except Exception:
            logger.exception("stored_news_read_failed", extra={"symbol": resolved_symbol})
        return {"success": False, "news": [], "source": source, "data_status": "UNAVAILABLE", "error": "No news was returned by the configured providers."}

    def get_technical_analysis(self, symbol: str, period: str = "6mo", interval: str = "1d", refresh: bool = False, auto_adjust: bool = True) -> Dict[str, Any]:
        history = self.get_history(symbol, period=period, interval=interval, refresh=refresh, auto_adjust=auto_adjust)
        if not history.get("success") or not history.get("data"):
            return {"success": False, "error": "Insufficient history for technical analysis"}
        
        df = pd.DataFrame(history["data"])
        result = calculate_technical_indicators(df, interval=interval)
        if not result.get("success"):
            return result
        model = result.get("ml_analysis") or {}
        if not model.get("available"):
            # Keep visible-window indicators tied to the chart, while giving
            # the time-ordered model enough same-interval bars to evaluate.
            model_period = {"1d": "1y", "1wk": "2y", "1mo": "5y"}.get(interval, "1y")
            model_history = self.get_history(symbol, period=model_period, interval=interval, refresh=refresh, auto_adjust=auto_adjust)
            model_rows = model_history.get("data") if model_history.get("success") else None
            if model_rows:
                model_result = calculate_technical_indicators(pd.DataFrame(model_rows), interval=interval)
                candidate = model_result.get("ml_analysis") or {}
                if candidate.get("available"):
                    candidate["training_period"] = model_period
                    candidate["training_last_bar_at"] = model_history.get("last_bar_at")
                    candidate["training_source"] = model_history.get("source", "unknown")
                    result["ml_analysis"] = candidate
        result.update({
            "symbol": resolve_symbol(symbol)["resolved_symbol"],
            "source": history.get("source", "unknown"),
            "data_status": history.get("data_status", history.get("status", "UNKNOWN")),
            "last_bar_at": history.get("last_bar_at"),
            "retrieved_at": history.get("timestamp") or history.get("retrieved_at"),
            "period": period,
            "interval": interval,
        })
        return result

    def check_provider(self, symbol: str = "AAPL") -> Dict[str, Any]:
        """Perform a provider check for the live health endpoint using the cache to prevent rate limits."""
        return self._get_with_cache("market_health", symbol, "get_quote", force_refresh=False)
