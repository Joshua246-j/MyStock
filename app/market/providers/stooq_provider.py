import pandas as pd
from typing import Dict, Any, List
from datetime import datetime
from app.market.providers.base import MarketDataProvider
import urllib.request
import io

class StooqProvider(MarketDataProvider):
    """Fallback provider using Stooq. Only implements basic quote and history."""
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        try:
            # Stooq daily csv download for latest quote
            url = f"https://stooq.com/q/l/?s={symbol.lower()}.us&f=sd2t2ohlcvn&h&e=csv"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=8)
            df = pd.read_csv(io.StringIO(response.read().decode('utf-8')))
            if df.empty or 'Close' not in df.columns or pd.isna(df['Close'].iloc[0]):
                return {"success": False, "error": "Invalid quote data from Stooq", "symbol": symbol, "status": "UNAVAILABLE", "source": "stooq"}
            
            price = float(df['Close'].iloc[0])
            history_url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
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
                "timestamp": datetime.now().isoformat(),
                "status": "DELAYED",
                "source": "stooq"
            }
        except Exception as e:
            return {"success": False, "error": str(e), "symbol": symbol, "status": "UNAVAILABLE", "source": "stooq"}

    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
        try:
            # Stooq doesn't map '1mo' directly easily without start/end, but we can fetch the whole daily and slice
            url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=8)
            df = pd.read_csv(io.StringIO(response.read().decode('utf-8')))
            if df.empty or 'Close' not in df.columns:
                return {"success": False, "error": "No historical data found", "source": "stooq"}
            
            rows_by_period = {"1mo": 23, "3mo": 66, "6mo": 132, "1y": 253, "2y": 506, "5y": 1265}
            df = df.tail(rows_by_period.get(period, 23))
            if interval == "1wk":
                df = df.assign(Date=pd.to_datetime(df["Date"])).set_index("Date").resample("W-FRI").agg({"Open":"first", "High":"max", "Low":"min", "Close":"last", "Volume":"sum"}).dropna().reset_index()
            elif interval == "1mo":
                df = df.assign(Date=pd.to_datetime(df["Date"])).set_index("Date").resample("ME").agg({"Open":"first", "High":"max", "Low":"min", "Close":"last", "Volume":"sum"}).dropna().reset_index()
            
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
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {"success": False, "error": str(e), "source": "stooq"}

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
