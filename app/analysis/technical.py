"""Transparent price-derived indicators and a clearly-labelled scenario estimate."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def calculate_technical_indicators(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty or "Close" not in df.columns:
        return {"success": False, "error": "Historical prices are unavailable for this analysis."}
    try:
        frame = df.copy()
        if "Date" in frame.columns:
            frame = frame.sort_values("Date")
        close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
        if len(close) < 2 or (close <= 0).any():
            return {"success": False, "error": "At least two positive closing prices are required."}
        returns = close.pct_change().dropna()
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        ema20 = close.ewm(span=20, adjust=False).mean()
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        loss = -delta.clip(upper=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.mask((loss == 0) & (gain > 0), 100).mask((gain == 0) & (loss > 0), 0)
        ema12, ema26 = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        std20 = close.rolling(20).std(ddof=0)
        rolling_peak = close.cummax()
        drawdown = close / rolling_peak - 1
        annualized_vol = returns.tail(252).std(ddof=1) * np.sqrt(252) if len(returns) > 1 else np.nan

        atr = None
        if {"High", "Low"}.issubset(frame.columns):
            high = pd.to_numeric(frame["High"], errors="coerce")
            low = pd.to_numeric(frame["Low"], errors="coerce")
            prior = pd.to_numeric(frame["Close"], errors="coerce").shift(1)
            true_range = pd.concat([(high - low), (high - prior).abs(), (low - prior).abs()], axis=1).max(axis=1)
            atr = true_range.rolling(14, min_periods=14).mean().iloc[-1]

        def number(value: Any) -> float | None:
            if value is None or pd.isna(value) or not np.isfinite(value):
                return None
            return float(value)

        current = float(close.iloc[-1])
        horizon = 20
        sample = np.log(close / close.shift(1)).dropna().tail(252)
        mu = float(sample.mean()) if not sample.empty else 0.0
        sigma = float(sample.std(ddof=1)) if len(sample) > 1 else 0.0
        z80 = 1.2815515655446004
        center = current * float(np.exp(mu * horizon))
        lower = current * float(np.exp(mu * horizon - z80 * sigma * np.sqrt(horizon)))
        upper = current * float(np.exp(mu * horizon + z80 * sigma * np.sqrt(horizon)))
        # Out-of-sample persistence baseline: predict the last known close over a 20-bar holdout.
        holdout = min(20, max(0, len(close) - 2))
        baseline_mae = float((close.iloc[-holdout:] - close.iloc[-holdout - 1]).abs().mean()) if holdout else None

        metrics = {
            "SMA_20": number(sma20.iloc[-1]), "SMA_50": number(sma50.iloc[-1]),
            "EMA_20": number(ema20.iloc[-1]), "RSI_14": number(rsi.iloc[-1]),
            "MACD": number(macd.iloc[-1]), "MACD_Signal": number(macd_signal.iloc[-1]),
            "Bollinger_Upper_20_2SD": number((sma20 + 2 * std20).iloc[-1]),
            "Bollinger_Middle_20": number(sma20.iloc[-1]),
            "Bollinger_Lower_20_2SD": number((sma20 - 2 * std20).iloc[-1]),
            "ATR_14": number(atr), "Annualized_Volatility_252d": number(annualized_vol),
            "Max_Drawdown_Period": number(drawdown.min()),
            "Return_1d": number(returns.iloc[-1] * 100),
            "Return_1mo_approx": number((close.iloc[-1] / close.iloc[-min(22, len(close))] - 1) * 100),
        }
        return {
            "success": True,
            "metrics": metrics,
            "scenario_estimate": {
                "method": "historical log-return drift and volatility; lognormal 80% interval",
                "horizon_trading_days": horizon,
                "central_estimate": center,
                "lower_80_percent": lower,
                "upper_80_percent": upper,
                "historical_daily_volatility": number(sigma),
                "persistence_baseline_holdout_mae": baseline_mae,
                "holdout_observations": holdout,
                "limitations": "Illustrative statistical scenario, not a validated investment forecast. Assumes historical return distribution persists; excludes fees, corporate actions, regime changes, and market events.",
            },
            "data": {"observations": int(len(close)), "latest_close": current},
        }
    except Exception as exc:
        return {"success": False, "error": f"Unable to calculate technical metrics: {exc}"}
