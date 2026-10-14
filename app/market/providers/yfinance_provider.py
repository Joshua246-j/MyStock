import yfinance as yf
from typing import Dict, Any, List
from datetime import datetime, timezone
from app.market.providers.base import MarketDataProvider
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential
import random
import logging

logger = logging.getLogger("stockrag.market.yfinance")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
]

class YFinanceProvider(MarketDataProvider):
    # Yahoo ticker search can include loosely tagged market-wide headlines.
    # Company-news feeds are served by the verified/tag-filtered fallback.
    supports_company_news = False

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
            logger.warning("yfinance_request_failed", extra={"symbol": symbol, "reason": str(e)})
            return {"success": False, "error": "Yahoo Finance could not provide this data. Check provider connectivity, ticker support, or rate limits.", "symbol": symbol, "source": "yfinance", "status": "UNAVAILABLE"}

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

            # Extract exact exchange metadata and release timestamp
            metadata = {}
            try:
                metadata = info._get_exchange_metadata() or {}
            except Exception:
                pass

            regular_market_time = metadata.get("regularMarketTime")
            market_time_iso = None
            if regular_market_time is not None:
                if hasattr(regular_market_time, "isoformat"):
                    market_time_iso = regular_market_time.isoformat()
                else:
                    try:
                        market_time_iso = pd.to_datetime(regular_market_time, unit="s", utc=True).isoformat()
                    except Exception:
                        market_time_iso = str(regular_market_time)

            exchange_name = metadata.get("fullExchangeName") or metadata.get("exchangeName") or getattr(info, "exchange", "US Exchange")
            exchange_tz = metadata.get("exchangeTimezoneName") or metadata.get("timezone") or getattr(info, "timezone", "UTC")

            # Determine genuine session state
            now_utc = datetime.now(timezone.utc)
            is_market_open = False
            trading_period = metadata.get("currentTradingPeriod", {})
            if isinstance(trading_period, dict):
                reg_period = trading_period.get("regular", {})
                if isinstance(reg_period, dict) and reg_period.get("start") and reg_period.get("end"):
                    try:
                        p_start = reg_period["start"].to_pydatetime() if hasattr(reg_period["start"], "to_pydatetime") else reg_period["start"]
                        p_end = reg_period["end"].to_pydatetime() if hasattr(reg_period["end"], "to_pydatetime") else reg_period["end"]
                        if p_start.tzinfo is None:
                            p_start = p_start.replace(tzinfo=timezone.utc)
                        if p_end.tzinfo is None:
                            p_end = p_end.replace(tzinfo=timezone.utc)
                        is_market_open = p_start <= now_utc <= p_end
                    except Exception:
                        pass

            market_session = "REGULAR_MARKET_OPEN" if is_market_open else "MARKET_CLOSED"
            data_status = "REALTIME_QUOTE" if is_market_open else "OFFICIAL_CLOSE"

            return {
                "success": True,
                "symbol": symbol,
                "price": price,
                "change": change,
                "change_percent": change_percent,
                "previous_close": prev_close,
                "open": getattr(info, "open", None),
                "day_high": getattr(info, "day_high", None) or metadata.get("regularMarketDayHigh"),
                "day_low": getattr(info, "day_low", None) or metadata.get("regularMarketDayLow"),
                "year_high": getattr(info, "year_high", None) or metadata.get("fiftyTwoWeekHigh"),
                "year_low": getattr(info, "year_low", None) or metadata.get("fiftyTwoWeekLow"),
                "fifty_day_average": getattr(info, "fifty_day_average", None),
                "two_hundred_day_average": getattr(info, "two_hundred_day_average", None),
                "volume": getattr(info, "last_volume", 0),
                "market_cap": getattr(info, "market_cap", 0),
                "currency": getattr(info, "currency", "USD"),
                "exchange": exchange_name,
                "exchange_timezone": exchange_tz,
                "market_time": market_time_iso,
                "market_session": market_session,
                "retrieved_at": datetime.now().astimezone().isoformat(),
                "data_status": data_status,
                "status": data_status,
                "source": f"Yahoo Finance ({exchange_name})"
            }
        return self._safe_execute(symbol, _fetch)

    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d", auto_adjust: bool = True) -> Dict[str, Any]:
        def _fetch():
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval, auto_adjust=auto_adjust)
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
                "timestamp": datetime.now().astimezone().isoformat(),
                "data_status": "HISTORICAL",
                "last_bar_at": str(data[-1].get("Date") or data[-1].get("Datetime") or "") if data else None
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
                content = item.get("content") or {}
                if not isinstance(content, dict):
                    content = {}
                thumbnail = item.get("thumbnail") or content.get("thumbnail") or {}
                if not isinstance(thumbnail, dict):
                    thumbnail = {}
                resolutions = thumbnail.get("resolutions") or []
                image = next((entry.get("url") for entry in resolutions if entry.get("url")), None)
                if not image and isinstance(content.get("thumbnail"), dict):
                    image = content["thumbnail"].get("originalUrl")
                canonical = content.get("canonicalUrl") or {}
                provider = content.get("provider") or {}
                if not isinstance(canonical, dict):
                    canonical = {}
                if not isinstance(provider, dict):
                    provider = {}
                published = item.get("providerPublishTime")
                if not published and isinstance(content.get("pubDate"), (int, float)):
                    published = content.get("pubDate")
                formatted_news.append({
                    "title": item.get("title") or content.get("title", ""),
                    "url": item.get("link") or canonical.get("url", ""),
                    "publisher": item.get("publisher") or provider.get("displayName", ""),
                    "published_at": datetime.fromtimestamp(published, timezone.utc).isoformat() if isinstance(published, (int, float)) and published else None,
                    "summary": content.get("summary", ""),
                    "image": image,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
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
