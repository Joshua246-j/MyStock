"""Read-only Indian exchange market data via Upstox's free Analytics Token."""
from __future__ import annotations

import gzip
import json
import logging
import os
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import PROJECT_ROOT, UPSTOX_ACCESS_TOKEN
from app.market.providers.base import MarketDataProvider

logger = logging.getLogger("stockrag.market.upstox")
IST = ZoneInfo("Asia/Kolkata")
INSTRUMENTS_URLS = {
    "NSE": "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
    "BSE": "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz",
}
INDEX_KEYS = {
    "^NSEI": "NSE_INDEX|Nifty 50",
    "^NSEBANK": "NSE_INDEX|Nifty Bank",
    "^BSESN": "BSE_INDEX|SENSEX",
}
PERIOD_DAYS = {"1mo": 31, "3mo": 93, "6mo": 186, "1y": 366, "2y": 731, "5y": 1827}


class UpstoxProvider(MarketDataProvider):
    """Exchange quote and candle provider; never places or modifies orders."""

    name = "Upstox Analytics API"

    def __init__(self, access_token: str | None = None, timeout: float = 12.0):
        self.access_token = (access_token if access_token is not None else UPSTOX_ACCESS_TOKEN).strip()
        self.timeout = timeout
        self._instrument_lock = threading.Lock()
        self._instrument_cache: dict[str, list[dict[str, Any]]] = {}

    @property
    def configured(self) -> bool:
        return bool(self.access_token)

    def _get_json(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("Upstox is not configured. Set UPSTOX_ACCESS_TOKEN in the local .env file.")
        try:
            response = httpx.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"},
                timeout=self.timeout,
                follow_redirects=True,
            )
            if response.status_code == 401:
                raise RuntimeError("Upstox rejected the Analytics Token; check expiry and regenerate it if needed.")
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Upstox did not respond before the market-data timeout.") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Upstox market-data API returned HTTP {exc.response.status_code}.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("Upstox market data could not be reached or decoded.") from exc
        if not isinstance(payload, dict) or payload.get("status") == "error":
            raise RuntimeError("Upstox returned an unsuccessful market-data response.")
        return payload

    def _load_instruments(self, exchange: str) -> list[dict[str, Any]]:
        with self._instrument_lock:
            cached = self._instrument_cache.get(exchange)
            if cached is not None:
                return cached
            cache_dir = Path(PROJECT_ROOT) / "data" / "instruments"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / f"upstox_{exchange.lower()}.json"
            if cache_path.exists() and datetime.now().timestamp() - cache_path.stat().st_mtime < 86400:
                try:
                    records = json.loads(cache_path.read_text(encoding="utf-8"))
                    if isinstance(records, list) and records:
                        self._instrument_cache[exchange] = records
                        return records
                except (OSError, json.JSONDecodeError):
                    logger.warning("upstox_instrument_cache_invalid", extra={"exchange": exchange})
            try:
                response = httpx.get(INSTRUMENTS_URLS[exchange], timeout=self.timeout, follow_redirects=True)
                response.raise_for_status()
                raw = response.content
                if raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                records = json.loads(raw)
                if not isinstance(records, list) or not records:
                    raise ValueError("Instrument master was empty or not a list")
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=cache_dir, delete=False) as temp:
                    json.dump(records, temp)
                    temp_path = Path(temp.name)
                temp_path.replace(cache_path)
                self._instrument_cache[exchange] = records
                return records
            except (httpx.HTTPError, OSError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Upstox {exchange} instrument master is unavailable.") from exc

    @staticmethod
    def _symbol_exchange(symbol: str) -> tuple[str, str]:
        normalized = symbol.strip().upper()
        if normalized in INDEX_KEYS:
            key = INDEX_KEYS[normalized]
            return ("NSE" if key.startswith("NSE_") else "BSE", key)
        if normalized.endswith(".NS"):
            return "NSE", normalized[:-3]
        if normalized.endswith(".BO"):
            return "BSE", normalized[:-3]
        raise ValueError("Upstox provider supports Indian NSE/BSE listings only.")

    def _instrument_key(self, symbol: str) -> tuple[str, str, dict[str, Any]]:
        exchange, requested = self._symbol_exchange(symbol)
        if "|" in requested:
            key = requested
            segment, name = key.split("|", 1)
            return exchange, key, {"segment": segment, "trading_symbol": name, "name": name}
        records = self._load_instruments(exchange)
        for record in records:
            if (record.get("exchange") == exchange and record.get("instrument_type") == "EQ"
                    and record.get("trading_symbol", "").upper() == requested):
                return exchange, str(record["instrument_key"]), record
        raise ValueError(f"{symbol} was not found in the Upstox {exchange} equity instrument master.")

    @staticmethod
    def _quote_record(data: dict[str, Any], record: dict[str, Any], instrument_key: str) -> dict[str, Any]:
        segment = str(record.get("segment") or instrument_key.split("|", 1)[0])
        trading_symbol = str(record.get("trading_symbol") or instrument_key.split("|", 1)[-1])
        return data.get(f"{segment}:{trading_symbol}") or data.get(instrument_key.replace("|", ":")) or next(iter(data.values()), {})

    @staticmethod
    def _freshness(last_trade_time: Any) -> tuple[str, str | None, float | None]:
        try:
            timestamp = datetime.fromtimestamp(int(str(last_trade_time)) / 1000, tz=timezone.utc)
            age_seconds = max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds())
            local_now = datetime.now(IST)
            session_open = local_now.weekday() < 5 and (local_now.hour, local_now.minute) >= (9, 15) and (local_now.hour, local_now.minute) <= (15, 30)
            status = "LIVE" if session_open and age_seconds <= 180 else "LAST_TRADE"
            return status, timestamp.astimezone(IST).isoformat(), age_seconds
        except (TypeError, ValueError, OSError, OverflowError):
            return "FRESHNESS_UNKNOWN", None, None

    def get_quote(self, symbol: str) -> dict[str, Any]:
        try:
            exchange, instrument_key, record = self._instrument_key(symbol)
            payload = self._get_json("https://api.upstox.com/v3/market-quote/quotes", params={"instrument_key": instrument_key})
            quote = self._quote_record(payload.get("data", {}), record, instrument_key)
            price = quote.get("last_price")
            if price is None:
                return {"success": False, "error": "Upstox quote response did not contain a last price.", "source": self.name}
            status, last_trade_at, age = self._freshness(quote.get("last_trade_time"))
            previous_close = quote.get("prev_close_price")
            change = float(price) - float(previous_close) if previous_close not in (None, 0) else quote.get("net_change")
            change_percent = change / float(previous_close) * 100 if previous_close not in (None, 0) and change is not None else None
            return {
                "success": True, "symbol": symbol, "price": float(price), "change": change,
                "change_percent": change_percent, "previous_close": previous_close,
                "open": (quote.get("ohlc") or {}).get("open"), "high": (quote.get("ohlc") or {}).get("high"),
                "low": (quote.get("ohlc") or {}).get("low"), "volume": quote.get("volume"),
                "market_cap": None, "currency": "INR", "exchange": exchange,
                "retrieved_at": quote.get("timestamp") or datetime.now(IST).isoformat(),
                "last_trade_at": last_trade_at, "age_seconds": age,
                "data_status": "EXCHANGE_SNAPSHOT", "status": status,
                "source": self.name, "instrument_key": instrument_key,
            }
        except Exception as exc:
            logger.warning("upstox_quote_failed", extra={"symbol": symbol, "reason": str(exc)})
            return {"success": False, "error": str(exc), "symbol": symbol, "status": "UNAVAILABLE", "source": self.name}

    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> dict[str, Any]:
        try:
            exchange, instrument_key, _ = self._instrument_key(symbol)
            unit, unit_interval = {"1d": ("days", "1"), "1wk": ("weeks", "1"), "1mo": ("months", "1")}.get(interval, ("days", "1"))
            to_date = date.today()
            from_date = to_date - timedelta(days=PERIOD_DAYS.get(period, 31))
            url = f"https://api.upstox.com/v3/historical-candle/{instrument_key}/{unit}/{unit_interval}/{to_date.isoformat()}/{from_date.isoformat()}"
            payload = self._get_json(url)
            candles = payload.get("data", {}).get("candles", [])
            rows = []
            for candle in candles:
                if not isinstance(candle, list) or len(candle) < 6:
                    continue
                timestamp = str(candle[0])
                rows.append({
                    "Date": timestamp[:10], "Datetime": timestamp,
                    "Open": float(candle[1]), "High": float(candle[2]), "Low": float(candle[3]),
                    "Close": float(candle[4]), "Volume": int(candle[5] or 0),
                    **({"Open Interest": float(candle[6])} if len(candle) > 6 and candle[6] is not None else {}),
                })
            rows.sort(key=lambda item: item["Datetime"])
            if not rows:
                return {"success": False, "error": "Upstox returned no historical candles for the requested period.", "source": self.name}
            last_bar = rows[-1]
            return {
                "success": True, "symbol": symbol, "period": period, "interval": interval,
                "data": rows, "source": self.name, "timestamp": datetime.now(IST).isoformat(),
                "data_status": "HISTORICAL_EXCHANGE_DATA", "last_bar_at": last_bar["Datetime"],
                "exchange": exchange, "instrument_key": instrument_key,
            }
        except Exception as exc:
            logger.warning("upstox_history_failed", extra={"symbol": symbol, "period": period, "interval": interval, "reason": str(exc)})
            return {"success": False, "error": str(exc), "source": self.name, "status": "UNAVAILABLE"}

    def get_company_profile(self, symbol: str) -> dict[str, Any]:
        return {"success": False, "error": "Company profile is not supplied by the Upstox quote adapter.", "source": self.name}

    def get_financials(self, symbol: str) -> dict[str, Any]:
        return {"success": False, "error": "Fundamentals are not supplied by the Upstox quote adapter.", "source": self.name}

    def get_balance_sheet(self, symbol: str) -> dict[str, Any]:
        return {"success": False, "error": "Balance sheets are not supplied by the Upstox quote adapter.", "source": self.name}

    def get_cash_flow(self, symbol: str) -> dict[str, Any]:
        return {"success": False, "error": "Cash flow statements are not supplied by the Upstox quote adapter.", "source": self.name}

    def get_news(self, symbol: str) -> list[dict[str, Any]]:
        return []

    def get_dividends(self, symbol: str) -> dict[str, Any]:
        return {"success": False, "error": "Corporate action data is not supplied by the Upstox quote adapter.", "source": self.name}

    def get_splits(self, symbol: str) -> dict[str, Any]:
        return {"success": False, "error": "Corporate action data is not supplied by the Upstox quote adapter.", "source": self.name}
