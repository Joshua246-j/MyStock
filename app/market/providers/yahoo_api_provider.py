import urllib.request
import json
import logging
import re
from typing import Dict, Any, List
from datetime import datetime, timezone
from app.market.providers.base import MarketDataProvider
import time

logger = logging.getLogger("stockrag.market.yahooapi")

class YahooApiProvider(MarketDataProvider):
    supports_company_news = True

    """
    Directly hits Yahoo Finance JSON API endpoints as a lightweight fallback 
    when the yfinance library fails or gets rate-limited.
    """
    def __init__(self):
        self.base_url_v8 = "https://query1.finance.yahoo.com/v8/finance"
        self.base_url_v10 = "https://query1.finance.yahoo.com/v10/finance"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }

    def _fetch(self, url: str) -> Dict[str, Any]:
        req = urllib.request.Request(url, headers=self.headers)
        try:
            response = urllib.request.urlopen(req, timeout=10)
            data = json.loads(response.read().decode('utf-8'))
            return data
        except Exception as e:
            logger.warning("yahooapi_request_failed", extra={"url": url, "reason": str(e)})
            raise

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        try:
            url = f"{self.base_url_v8}/chart/{symbol}?interval=1d&range=1d"
            data = self._fetch(url)
            meta = data['chart']['result'][0]['meta']
            
            price = meta.get('regularMarketPrice')
            prev_close = meta.get('previousClose')
            change = price - prev_close if price and prev_close else 0
            change_percent = (change / prev_close * 100) if prev_close else 0

            rmt = meta.get('regularMarketTime')
            market_time_iso = datetime.fromtimestamp(rmt, timezone.utc).isoformat() if rmt else None
            exchange_name = meta.get('exchangeName') or 'US'
            tz_name = meta.get('timezone') or meta.get('exchangeTimezoneName') or 'UTC'

            now_utc = datetime.now(timezone.utc)
            is_market_open = False
            tp = meta.get('currentTradingPeriod', {})
            if isinstance(tp, dict):
                reg = tp.get('regular', {})
                if isinstance(reg, dict) and reg.get('start') and reg.get('end'):
                    try:
                        s_dt = datetime.fromtimestamp(reg['start'], timezone.utc)
                        e_dt = datetime.fromtimestamp(reg['end'], timezone.utc)
                        is_market_open = s_dt <= now_utc <= e_dt
                    except Exception:
                        pass

            market_session = "REGULAR_MARKET_OPEN" if is_market_open else "MARKET_CLOSED"
            # Do not imply real-time delivery or an official exchange close.
            data_status = "PROVIDER_QUOTE" if is_market_open else "PROVIDER_CLOSE"

            return {
                "success": True,
                "symbol": symbol,
                "price": price,
                "change": change,
                "change_percent": change_percent,
                "previous_close": prev_close,
                "open": meta.get('regularMarketOpen'),
                "day_high": meta.get('regularMarketDayHigh'),
                "day_low": meta.get('regularMarketDayLow'),
                "volume": meta.get('regularMarketVolume', 0),
                "currency": meta.get('currency', 'USD'),
                "exchange": exchange_name,
                "exchange_timezone": tz_name,
                "market_time": market_time_iso,
                "market_session": market_session,
                "retrieved_at": datetime.now().astimezone().isoformat(),
                "timestamp": datetime.now().astimezone().isoformat(),
                "data_status": data_status,
                "status": data_status,
                "source": f"Yahoo Finance ({exchange_name})"
            }
        except Exception as e:
            return {"success": False, "error": str(e), "source": "yahooapi"}

    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
        # Map period format
        if period == "1y": period = "1y"
        # etc.
        try:
            url = f"{self.base_url_v8}/chart/{symbol}?interval={interval}&range={period}"
            data = self._fetch(url)
            result = data['chart']['result'][0]
            timestamps = result.get('timestamp', [])
            indicators = result['indicators']['quote'][0]
            
            opens = indicators.get('open', [])
            highs = indicators.get('high', [])
            lows = indicators.get('low', [])
            closes = indicators.get('close', [])
            volumes = indicators.get('volume', [])
            
            history = []
            for i in range(len(timestamps)):
                if opens[i] is None or highs[i] is None or lows[i] is None or closes[i] is None:
                    continue
                if min(opens[i], highs[i], lows[i], closes[i]) <= 0:
                    continue
                dt = datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d')
                history.append({
                    "Date": dt,
                    "Open": opens[i],
                    "High": highs[i],
                    "Low": lows[i],
                    "Close": closes[i],
                    "Volume": volumes[i]
                })
            
            return {
                "success": True,
                "symbol": symbol,
                "period": period,
                "interval": interval,
                "data": history,
                "source": "yahooapi",
                "timestamp": datetime.now().astimezone().isoformat(),
                "data_status": "HISTORICAL"
            }
        except Exception as e:
            return {"success": False, "error": str(e), "source": "yahooapi"}

    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        try:
            url = f"{self.base_url_v10}/quoteSummary/{symbol}?modules=assetProfile,price"
            data = self._fetch(url)
            result = data['quoteSummary']['result'][0]
            profile = result.get('assetProfile', {})
            price_info = result.get('price', {})
            
            return {
                "success": True,
                "symbol": symbol,
                "name": price_info.get('shortName', symbol),
                "sector": profile.get('sector', 'Unknown'),
                "industry": profile.get('industry', 'Unknown'),
                "description": profile.get('longBusinessSummary', 'No description available.'),
                "website": profile.get('website', ''),
                "country": profile.get('country', ''),
                "source": "yahooapi"
            }
        except Exception as e:
            return {"success": False, "error": str(e), "source": "yahooapi"}

    def get_financials(self, symbol: str) -> Dict[str, Any]:
        try:
            url = f"{self.base_url_v10}/quoteSummary/{symbol}?modules=financialData,defaultKeyStatistics"
            data = self._fetch(url)
            result = data['quoteSummary']['result'][0]
            fin = result.get('financialData', {})
            stats = result.get('defaultKeyStatistics', {})
            
            metrics = {
                "trailingPE": fin.get('currentPrice', {}).get('raw') / stats.get('trailingEps', {}).get('raw') if fin.get('currentPrice', {}).get('raw') and stats.get('trailingEps', {}).get('raw') else None,
                "forwardPE": stats.get('forwardPE', {}).get('raw'),
                "priceToBook": stats.get('priceToBook', {}).get('raw'),
                "returnOnEquity": fin.get('returnOnEquity', {}).get('raw'),
                "debtToEquity": fin.get('debtToEquity', {}).get('raw'),
                "revenueGrowth": fin.get('revenueGrowth', {}).get('raw'),
                "ebitda": fin.get('ebitda', {}).get('raw'),
                "freeCashflow": fin.get('freeCashflow', {}).get('raw'),
                "grossMargins": fin.get('grossMargins', {}).get('raw'),
                "operatingMargins": fin.get('operatingMargins', {}).get('raw'),
                "profitMargins": fin.get('profitMargins', {}).get('raw')
            }
            metrics = {k: v for k, v in metrics.items() if v is not None}
            
            return {
                "success": True,
                "symbol": symbol,
                "metrics": metrics,
                "source": "yahooapi",
                "retrieved_at": datetime.now().isoformat()
            }
        except Exception as e:
            return {"success": False, "error": str(e), "source": "yahooapi"}

    def get_balance_sheet(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported", "source": "yahooapi"}

    def get_cash_flow(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported", "source": "yahooapi"}

    def get_news(self, symbol: str) -> List[Dict[str, Any]]:
        # Yahoo's symbol search mixes company coverage with market-wide stories.
        # Keep only items explicitly tagged to this symbol and whose headline or
        # excerpt also names the company/ticker, so a broad tag alone cannot
        # mislabel unrelated articles as company news.
        try:
            url = f"https://query2.finance.yahoo.com/v1/finance/search?q={symbol}&newsCount=10"
            data = self._fetch(url)
            news_items = data.get('news', [])
            normalized_symbol = str(symbol).strip().upper()
            quote = next((
                item for item in data.get("quotes", [])
                if str(item.get("symbol", "")).upper() == normalized_symbol
            ), {})
            company = str(quote.get("longname") or quote.get("shortname") or "").strip()
            company = re.sub(r"\b(?:incorporated|corporation|company|limited|inc|corp|co|ltd)\.?$", "", company, flags=re.I).strip()
            base_symbol = normalized_symbol.split(".", 1)[0].lstrip("^")

            def mentions_target(text: str) -> bool:
                if re.search(rf"(?<![A-Z0-9]){re.escape(normalized_symbol)}(?![A-Z0-9])", text, re.I):
                    return True
                if base_symbol and base_symbol != normalized_symbol and re.search(rf"(?<![A-Z0-9]){re.escape(base_symbol)}(?![A-Z0-9])", text, re.I):
                    return True
                return bool(company and re.search(rf"(?<!\w){re.escape(company)}(?!\w)", text, re.I))

            formatted_news = []
            for item in news_items:
                related = item.get("relatedTickers") or []
                related_symbols = {str(value).strip().upper() for value in related if value}
                title = str(item.get("title") or "").strip()
                summary = str(item.get("summary") or "").strip()
                if normalized_symbol not in related_symbols or not mentions_target(f"{title} {summary}"):
                    continue
                published = item.get("providerPublishTime")
                formatted_news.append({
                    "title": title,
                    "url": item.get('link', ''),
                    "publisher": item.get('publisher', 'Yahoo Finance'),
                    "published_at": datetime.fromtimestamp(published, timezone.utc).isoformat() if isinstance(published, (int, float)) and published else None,
                    "summary": summary,
                    "image": next((entry.get('url') for entry in (item.get('thumbnail') or {}).get('resolutions', []) if entry.get('url')), None),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "ticker": normalized_symbol,
                    "related_tickers": sorted(related_symbols),
                })
            return formatted_news
        except Exception as e:
            return []

    def get_dividends(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported", "source": "yahooapi"}

    def get_splits(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported", "source": "yahooapi"}
