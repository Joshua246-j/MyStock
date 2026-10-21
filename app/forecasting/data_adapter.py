"""Market data adapter and quality verification for the forecasting engine."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from app.market.symbol_resolver import resolve_symbol

logger = logging.getLogger("stockrag.forecasting.data_adapter")


class DataQualityError(ValueError):
    """Raised when market data fails quality or integrity constraints."""
    pass


class ForecastDataAdapter:
    """Adapts, normalizes, and validates market bars and news for forecasting."""

    def __init__(self, market_service: Any = None):
        if market_service is None:
            from app.dependencies import market_service as default_service
            self.market_service = default_service
        else:
            self.market_service = market_service

    def fetch_normalized_market_data(
        self,
        symbol: str,
        period: str = "2y",
        interval: str = "1d",
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Fetch historical price bars, validate OHLCV integrity, and attach metadata."""
        resolved = resolve_symbol(symbol)
        if not resolved["valid"]:
            return {
                "success": False,
                "error": f"Invalid symbol format: {symbol}",
                "status": "invalid_symbol",
            }

        resolved_symbol = resolved["resolved_symbol"]
        history_result = self.market_service.get_history(
            resolved_symbol,
            period=period,
            interval=interval,
            refresh=refresh,
            auto_adjust=True,
        )

        if not history_result.get("success") or not history_result.get("data"):
            return {
                "success": False,
                "error": history_result.get("error", "No historical price data returned"),
                "status": "insufficient_data",
                "symbol": resolved_symbol,
            }

        raw_bars = history_result["data"]
        df = pd.DataFrame(raw_bars)

        try:
            clean_df = self.validate_and_normalize_ohlcv(df)
        except DataQualityError as exc:
            return {
                "success": False,
                "error": str(exc),
                "status": "data_quality_failure",
                "symbol": resolved_symbol,
            }

        last_bar_at = history_result.get("last_bar_at") or (
            str(clean_df["Date"].iloc[-1]) if "Date" in clean_df.columns else None
        )
        retrieved_at = history_result.get("retrieved_at") or datetime.now(timezone.utc).isoformat()

        # Compute data freshness
        freshness_status = "FRESH"
        if last_bar_at:
            try:
                last_dt = datetime.fromisoformat(str(last_bar_at).replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - last_dt).total_seconds() / 86400.0
                if age_days > 5.0:
                    freshness_status = "STALE"
            except Exception:
                freshness_status = "UNKNOWN"

        market_name = str(resolved.get("market", "us")).lower()
        metadata = {
            "symbol": resolved_symbol,
            "market": market_name,
            "source": history_result.get("source", "market_service"),
            "data_status": history_result.get("data_status", freshness_status),
            "freshness": freshness_status,
            "observation_timestamp": last_bar_at,
            "retrieved_at": retrieved_at,
            "bar_count": len(clean_df),
            "period": period,
            "interval": interval,
            "currency": resolved.get("currency") or ("INR" if market_name == "india" else "USD"),
        }

        return {
            "success": True,
            "data": clean_df,
            "metadata": metadata,
        }

    @staticmethod
    def validate_and_normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        """Enforce strict OHLCV integrity: sort, deduplicate, validate ranges.
        
        Flexible towards user-uploaded datasets with lowercase or alternative column names.
        """
        if df.empty:
            raise DataQualityError("Historical bars dataframe is empty.")

        clean = df.copy()
        
        # Case-insensitive column mapping
        col_map = {}
        for c in clean.columns:
            low = str(c).strip().casefold()
            if low in ("date", "datetime", "timestamp", "time"):
                col_map[c] = "Date"
            elif low in ("close", "price", "adj close", "adj_close", "last", "value"):
                col_map[c] = "Close"
            elif low in ("open", "open_price"):
                col_map[c] = "Open"
            elif low in ("high", "high_price", "max"):
                col_map[c] = "High"
            elif low in ("low", "low_price", "min"):
                col_map[c] = "Low"
            elif low in ("volume", "vol", "shares"):
                col_map[c] = "Volume"
        
        clean = clean.rename(columns=col_map)

        if "Date" not in clean.columns:
            # Check if index is a datetime index
            if isinstance(clean.index, pd.DatetimeIndex):
                clean["Date"] = clean.index
            else:
                raise DataQualityError("Missing required date or datetime column in dataset.")

        if "Close" not in clean.columns:
            raise DataQualityError("Missing required price column ('Close' or 'Price') in dataset.")

        # Synthesize missing Open, High, Low from Close if user uploaded single price series
        if "Open" not in clean.columns:
            clean["Open"] = clean["Close"]
        if "High" not in clean.columns:
            clean["High"] = clean["Close"]
        if "Low" not in clean.columns:
            clean["Low"] = clean["Close"]
        if "Volume" not in clean.columns:
            clean["Volume"] = 10000.0

        clean["Date"] = pd.to_datetime(clean["Date"], errors="coerce", utc=True)
        clean = clean.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")

        for col in ["Open", "High", "Low", "Close"]:
            clean[col] = pd.to_numeric(clean[col], errors="coerce")
            if clean[col].isna().any():
                clean[col] = clean[col].interpolate(method="linear").bfill().ffill()

        if (clean["Close"] <= 0).any() or (clean["Open"] <= 0).any():
            raise DataQualityError("Non-positive prices encountered in historical data.")

        # OHLC logic check
        clean["High"] = np.maximum(clean["High"], np.maximum(clean["Open"], clean["Close"]))
        clean["Low"] = np.minimum(clean["Low"], np.minimum(clean["Open"], clean["Close"]))
        clean["Volume"] = pd.to_numeric(clean["Volume"], errors="coerce").fillna(0.0).clip(lower=0.0)

        # Outlier unadjusted jump check
        log_returns = np.diff(np.log(clean["Close"].to_numpy()))
        if len(log_returns) > 0 and np.any(np.abs(log_returns) > 1.2):
            logger.warning("large_jump_detected", extra={"max_jump": float(np.max(np.abs(log_returns)))})

        return clean.reset_index(drop=True)

    def fetch_related_news(self, symbol: str, limit: int = 40) -> list[dict[str, Any]]:
        """Retrieve recent relevant news articles for symbol."""
        news_items: list[dict[str, Any]] = []
        try:
            res = self.market_service.get_news(symbol)
            if res and isinstance(res, list):
                news_items.extend(res)
        except Exception as exc:
            logger.info("service_news_fetch_failed", extra={"symbol": symbol, "error": str(exc)})

        try:
            from app.market.news_providers import fetch_all_provider_feeds
            resolved = resolve_symbol(symbol)
            market = str(resolved.get("market", "all")).lower()
            external_items = fetch_all_provider_feeds(market=market, max_workers=6, timeout=4.0)
            target = resolved["resolved_symbol"]
            bare = target.split(".")[0].casefold()
            for item in external_items:
                tickers = [t.casefold() for t in item.get("related_tickers", [])]
                t_single = (item.get("ticker") or "").casefold()
                if bare in tickers or target.casefold() in tickers or bare == t_single:
                    news_items.append(item)
        except Exception as exc:
            logger.debug("external_news_providers_failed", extra={"error": str(exc)})

        # Deduplicate by url or title
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for item in news_items:
            key = item.get("url") or item.get("title")
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped[:limit]

    def fetch_third_party_targets(
        self,
        symbol: str,
        ohlcv_df: pd.DataFrame | None = None,
        current_price: float = 0.0,
    ) -> dict[str, Any]:
        """Fetch free, authentic 3rd-party analyst price targets and compute algorithmic pivot levels.
        
        Zero fabrication: accurately labels free external sources, analyst opinion counts, and caveats.
        """
        targets: dict[str, Any] = {}

        # 1. Authentic Yahoo Finance Analyst Consensus (Free Public Feed)
        yahoo_target = None
        if symbol and not str(symbol).upper().startswith(("CUSTOM", "UPLOAD", "SYNTHETIC", "TEST")):
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                mean_target = info.get("targetMeanPrice")
                high_target = info.get("targetHighPrice")
                low_target = info.get("targetLowPrice")
                rec_key = info.get("recommendationKey")
                analyst_count = info.get("numberOfAnalystOpinions")

                if mean_target and float(mean_target) > 0 and current_price > 0:
                    mean_t = round(float(mean_target), 2)
                    implied_ret = round(((mean_t - current_price) / current_price) * 100.0, 2)
                    yahoo_target = {
                        "available": True,
                        "provider_name": "Yahoo Finance Analyst Consensus",
                        "provider_type": "Free Public Sell-Side Consensus Feed",
                        "target_price": mean_t,
                        "target_high": round(float(high_target), 2) if high_target else None,
                        "target_low": round(float(low_target), 2) if low_target else None,
                        "implied_return_percent": implied_ret,
                        "recommendation": str(rec_key).upper().replace("_", " ") if rec_key else "CONSENSUS",
                        "analyst_count": int(analyst_count) if analyst_count else None,
                        "reliability_level": "MODERATE_INFORMATIVE",
                        "reliability_badge": "External Consensus (Free Tier)",
                        "attribution": "Aggregated sell-side analyst price targets via Yahoo Finance public API.",
                        "disclaimer": "Analyst targets represent subjective external estimates subject to lagging revisions.",
                    }
            except Exception as exc:
                logger.info("third_party_yahoo_consensus_fetch_skipped", extra={"symbol": symbol, "reason": str(exc)})

        if yahoo_target:
            targets["analyst_consensus"] = yahoo_target
        else:
            targets["analyst_consensus"] = {
                "available": False,
                "provider_name": "Yahoo Finance Analyst Consensus",
                "reason": "No public sell-side analyst consensus targets published for this ticker.",
            }

        # 2. Algorithmic Pivot & Fibonacci Model (Open Quantitative Standard)
        if ohlcv_df is not None and not ohlcv_df.empty and current_price > 0 and len(ohlcv_df) >= 10:
            window = ohlcv_df.tail(20)
            high_20 = float(window["High"].max())
            low_20 = float(window["Low"].min())
            last_close = float(ohlcv_df["Close"].iloc[-1])
            pivot = (high_20 + low_20 + last_close) / 3.0
            r1 = (2.0 * pivot) - low_20
            s1 = (2.0 * pivot) - high_20
            fib_bull = last_close + (high_20 - low_20) * 0.618
            fib_bear = last_close - (high_20 - low_20) * 0.382

            implied_pivot_ret = round(((pivot - current_price) / current_price) * 100.0, 2)
            targets["algorithmic_pivot"] = {
                "available": True,
                "provider_name": "Classical Pivot & Fibonacci Projection",
                "provider_type": "Deterministic Technical Specification",
                "target_price": round(pivot, 2),
                "resistance_r1": round(r1, 2),
                "support_s1": round(s1, 2),
                "fib_bull_projection": round(fib_bull, 2),
                "fib_bear_projection": round(fib_bear, 2),
                "implied_return_percent": implied_pivot_ret,
                "reliability_level": "HIGH_CALCULATED",
                "reliability_badge": "Deterministic Formula",
                "attribution": "Calculated strictly from 20-session extreme price bounds and standard pivot geometry.",
                "disclaimer": "Mechanical support/resistance baseline with zero subjective bias.",
            }
        else:
            targets["algorithmic_pivot"] = {
                "available": False,
                "provider_name": "Classical Pivot & Fibonacci Projection",
                "reason": "Insufficient historical bars to compute 20-session envelope.",
            }

        return targets
