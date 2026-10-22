import pandas as pd
from typing import Dict, Any, List
from datetime import datetime
from app.market.providers.base import MarketDataProvider
import urllib.request
import io
import re
import logging

logger = logging.getLogger("stockrag.market.stooq")

class StooqProvider(MarketDataProvider):
    """Fallback provider using Stooq. Only implements basic quote and history."""

    @staticmethod
    def _symbol(symbol: str):
        # This adapter only knows Stooq's US ticker suffix convention. Never
        # silently append .us to a foreign-exchange ticker.
        normalized = symbol.strip().lower()
        if normalized.endswith((".ns", ".bo", ".l", ".to", ".ax")):
            return None
        if not re.fullmatch(r"[a-z0-9.-]+", normalized):
            return None
        return normalized.replace(".", "-") + ".us"
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        try:
            provider_symbol = self._symbol(symbol)
            if not provider_symbol:
                return {"success": False, "error": "Stooq fallback currently supports US listings only.", "symbol": symbol, "status": "UNAVAILABLE", "source": "stooq"}
            # Stooq daily csv download for latest quote
            url = f"https://stooq.com/q/l/?s={provider_symbol}&f=sd2t2ohlcvn&h&e=csv"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=8)
            df = pd.read_csv(io.StringIO(response.read().decode('utf-8')))
            if df.empty or 'Close' not in df.columns or pd.isna(df['Close'].iloc[0]) or float(df['Close'].iloc[0]) <= 0:
                return {"success": False, "error": "Invalid quote data from Stooq", "symbol": symbol, "status": "UNAVAILABLE", "source": "stooq"}
            
            price = float(df['Close'].iloc[0])
            history_url = f"https://stooq.com/q/d/l/?s={provider_symbol}&i=d"
            history_req = urllib.request.Request(history_url, headers={'User-Agent': 'Mozilla/5.0'})
            history_response = urllib.request.urlopen(history_req, timeout=8)
            history = pd.read_csv(io.StringIO(history_response.read().decode('utf-8')))
            closes = history['Close'].dropna().tolist() if 'Close' in history else []
            previous_close = float(closes[-2]) if len(closes) > 1 else None
            change = price - previous_close if previous_close else None
            change_percent = (change / previous_close * 100) if previous_close and change is not None else None
            
            return {
                "success": True,
                "symbol": symbol,
                "price": price,
                "change": change,
                "change_percent": change_percent,
                "volume": float(df['Volume'].iloc[0]) if 'Volume' in df.columns else 0,
                "previous_close": previous_close,
                "market_cap": 0,
                "currency": "USD",
                "timestamp": datetime.now().astimezone().isoformat(),
                "last_bar_at": f"{df['Date'].iloc[0]} {df['Time'].iloc[0]}" if 'Date' in df.columns and 'Time' in df.columns else str(df['Date'].iloc[0]) if 'Date' in df.columns else None,
                "data_status": "DELAYED_OR_END_OF_DAY",
                "status": "DELAYED",
                "source": "stooq"
            }
        except Exception as e:
            logger.warning("stooq_quote_failed", extra={"symbol": symbol, "reason": str(e)})
            return {"success": False, "error": "Stooq could not retrieve this quote. Check provider connectivity and ticker support.", "symbol": symbol, "status": "UNAVAILABLE", "source": "stooq"}

    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
        try:
            provider_symbol = self._symbol(symbol)
            if not provider_symbol:
                return {"success": False, "error": "Stooq fallback currently supports US listings only.", "symbol": symbol, "status": "UNAVAILABLE", "source": "stooq"}
            # Stooq doesn't map '1mo' directly easily without start/end, but we can fetch the whole daily and slice
            url = f"https://stooq.com/q/d/l/?s={provider_symbol}&i=d"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=8)
            df = pd.read_csv(io.StringIO(response.read().decode('utf-8')))
            if df.empty or 'Close' not in df.columns or not len(df):
                return {"success": False, "error": "No historical data found", "source": "stooq"}
            
            rows_by_period = {"1mo": 23, "3mo": 66, "6mo": 132, "1y": 253, "2y": 506, "5y": 1265}
            df = df.tail(rows_by_period.get(period, 23))
            if interval == "1wk":
                df = df.assign(Date=pd.to_datetime(df["Date"])).set_index("Date").resample("W-FRI").agg({"Open":"first", "High":"max", "Low":"min", "Close":"last", "Volume":"sum"}).dropna().reset_index()
            elif interval == "1mo":
                df = df.assign(Date=pd.to_datetime(df["Date"])).set_index("Date").resample("ME").agg({"Open":"first", "High":"max", "Low":"min", "Close":"last", "Volume":"sum"}).dropna().reset_index()
            
            df = df.dropna(subset=[col for col in ['Open', 'High', 'Low', 'Close'] if col in df.columns])
            for col in ['Open', 'High', 'Low', 'Close']:
                if col in df.columns:
                    df = df[pd.to_numeric(df[col], errors='coerce') > 0]
            if df.empty:
                return {"success": False, "error": "No valid historical data found", "source": "stooq"}

            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            
            df = df.where(pd.notnull(df), None)
            data = df.to_dict(orient='records')
            
            return {
                "success": True,
                "symbol": symbol,
                "period": period,
                "interval": interval,
                "data": data,
                "source": "stooq",
                "timestamp": datetime.now().astimezone().isoformat(),
                "data_status": "HISTORICAL_DELAYED",
                "last_bar_at": data[-1].get("Date") if data else None
            }
        except Exception as e:
            logger.warning("stooq_history_failed", extra={"symbol": symbol, "period": period, "interval": interval, "reason": str(e)})
            return {"success": False, "error": "Stooq could not retrieve historical prices. Check provider connectivity and ticker support.", "source": "stooq"}

    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported by fallback provider", "source": "stooq"}

    def get_financials(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported by fallback provider", "source": "stooq"}

    def get_balance_sheet(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported by fallback provider", "source": "stooq"}

    def get_cash_flow(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported by fallback provider", "source": "stooq"}

    def get_news(self, symbol: str) -> List[Dict[str, Any]]:
        return []

    def get_dividends(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported", "source": "stooq"}

    def get_splits(self, symbol: str) -> Dict[str, Any]:
        return {"success": False, "error": "Not supported", "source": "stooq"}
