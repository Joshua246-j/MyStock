"""Transparent price-derived indicators and a clearly-labelled scenario estimate."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def walk_forward_return_model(close: pd.Series, interval: str = "1d") -> dict[str, Any]:
    """Small ridge regression with an expanding, time-ordered evaluation window."""
    values = pd.to_numeric(close, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < 65 or np.any(values <= 0):
        bar_name = {"1d": "daily", "1wk": "weekly", "1mo": "monthly"}.get(interval, "daily")
        return {"available": False, "reason": f"At least 65 {bar_name} closes are required for a time-ordered evaluation."}
    log_returns = np.diff(np.log(values))
    features, labels = [], []
    # Features at t use information through t; label is the next bar return.
    for t in range(20, len(log_returns) - 1):
        window = log_returns[t - 19:t + 1]
        features.append([log_returns[t], window[-5:].sum(), window.sum(), window.std(ddof=1)])
        labels.append(log_returns[t + 1])
    x, y = np.asarray(features, dtype=float), np.asarray(labels, dtype=float)
    holdout = min(20, max(1, len(y) // 5))
    split = len(y) - holdout
    if split < 30:
        return {"available": False, "reason": "Not enough observations remain after the holdout split."}

    def fit_predict(train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray) -> np.ndarray:
        mean = train_x.mean(axis=0)
        scale = train_x.std(axis=0)
        scale[scale < 1e-12] = 1.0
        normalized = (train_x - mean) / scale
        normalized_test = (test_x - mean) / scale
        design = np.column_stack([np.ones(len(normalized)), normalized])
        test_design = np.column_stack([np.ones(len(normalized_test)), normalized_test])
        penalty = np.eye(design.shape[1]) * 1.0
        penalty[0, 0] = 0.0
        return test_design @ np.linalg.solve(design.T @ design + penalty, design.T @ train_y)

    # Walk forward so each holdout prediction only sees earlier labels.
    predictions = []
    for index in range(split, len(y)):
        predictions.append(float(fit_predict(x[:index], y[:index], x[index:index + 1])[0]))
    predictions_array = np.asarray(predictions)
    actual = y[split:]
    baseline = float(np.mean(y[:split]))
    model_mae = float(np.mean(np.abs(predictions_array - actual)))
    baseline_mae = float(np.mean(np.abs(baseline - actual)))
    latest_window = log_returns[-20:]
    latest_features = np.asarray([[log_returns[-1], latest_window[-5:].sum(), latest_window.sum(), latest_window.std(ddof=1)]])
    latest_prediction = float(fit_predict(x, y, latest_features)[0])
    result = {
        "available": True,
        "model": "ridge regression on 1-bar, 5-bar, 20-bar momentum and 20-bar volatility",
        "latest_next_bar_return_percent": latest_prediction * 100,
        "bar_interval": interval,
        "walk_forward_holdout_bars": holdout,
        "walk_forward_mae_percent": model_mae * 100,
        "historical_mean_baseline_mae_percent": baseline_mae * 100,
        "beats_baseline_mae": model_mae < baseline_mae,
        "limitations": "Experimental price-only model with a small historical sample. Walk-forward metrics describe this holdout only; the next-bar estimate is not a validated forecast or investment recommendation.",
    }
    if interval == "1d":
        result["latest_next_session_return_percent"] = result["latest_next_bar_return_percent"]
        result["walk_forward_holdout_sessions"] = holdout
    return result


def calculate_indicator_series(df: pd.DataFrame) -> dict[str, Any]:
    """Calculate chart-ready indicator values from validated historical bars."""
    if df.empty or "Close" not in df.columns or not ("Date" in df.columns or "Datetime" in df.columns):
        return {"success": False, "error": "Timestamped historical prices are required for chart indicators."}
    frame = df.copy().sort_values("Date" if "Date" in df.columns else "Datetime")
    close = pd.to_numeric(frame["Close"], errors="coerce")
    sma20 = close.rolling(20, min_periods=1).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    std20 = close.rolling(20, min_periods=1).std(ddof=0)
    upper, lower = sma20 + 2 * std20, sma20 - 2 * std20
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    relative_strength = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + relative_strength))
    rsi = rsi.mask((loss == 0) & (gain > 0), 100).mask((gain == 0) & (loss > 0), 0)
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    atr = None
    if {"High", "Low"}.issubset(frame.columns):
        high = pd.to_numeric(frame["High"], errors="coerce")
        low = pd.to_numeric(frame["Low"], errors="coerce")
        prior_close = close.shift(1)
        true_range = pd.concat([(high - low), (high - prior_close).abs(), (low - prior_close).abs()], axis=1).max(axis=1)
        atr = true_range.rolling(14, min_periods=1).mean()
    timestamps = frame["Date" if "Date" in frame.columns else "Datetime"].astype(str).tolist()
    volume = pd.to_numeric(frame["Volume"], errors="coerce") if "Volume" in frame.columns else pd.Series([np.nan] * len(frame))

    def optional(value):
        return float(value) if pd.notna(value) and np.isfinite(value) else None

    rows = []
    for index, stamp in enumerate(timestamps):
        rows.append({
            "time": stamp[:10] if len(stamp) >= 10 else stamp,
            "sma20": optional(sma20.iloc[index]),
            "ema20": optional(ema20.iloc[index]),
            "bollinger_upper": optional(upper.iloc[index]),
            "bollinger_lower": optional(lower.iloc[index]),
            "rsi14": optional(rsi.iloc[index]),
            "macd": optional(macd.iloc[index]),
            "macd_signal": optional(macd_signal.iloc[index]),
            "macd_hist": optional((macd - macd_signal).iloc[index]),
            "atr14": optional(atr.iloc[index]) if atr is not None else None,
            "volume": optional(volume.iloc[index]),
            "close": optional(close.iloc[index]),
        })
    return {"success": True, "data": rows}


def calculate_technical_indicators(df: pd.DataFrame, interval: str = "1d") -> dict[str, Any]:
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
        bars_per_year = {"1d": 252, "1wk": 52, "1mo": 12}.get(interval, 252)
        annualized_vol = returns.tail(bars_per_year).std(ddof=1) * np.sqrt(bars_per_year) if len(returns) > 1 else np.nan

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
        horizon_bars = {"1d": 20, "1wk": 4, "1mo": 1}.get(interval, 20)
        sample = np.log(close / close.shift(1)).dropna().tail(bars_per_year)
        mu = float(sample.mean()) if not sample.empty else 0.0
        sigma = float(sample.std(ddof=1)) if len(sample) > 1 else 0.0
        z80 = 1.2815515655446004
        center = current * float(np.exp(mu * horizon_bars))
        lower = current * float(np.exp(mu * horizon_bars - z80 * sigma * np.sqrt(horizon_bars)))
        upper = current * float(np.exp(mu * horizon_bars + z80 * sigma * np.sqrt(horizon_bars)))
        # Out-of-sample persistence baseline over a horizon matching this bar interval.
        holdout = min(horizon_bars, max(0, len(close) - 2))
        baseline_mae = float((close.iloc[-holdout:] - close.iloc[-holdout - 1]).abs().mean()) if holdout else None

        metrics = {
            "SMA_20": number(sma20.iloc[-1]), "SMA_50": number(sma50.iloc[-1]),
            "EMA_20": number(ema20.iloc[-1]), "RSI_14": number(rsi.iloc[-1]),
            "MACD": number(macd.iloc[-1]), "MACD_Signal": number(macd_signal.iloc[-1]),
            "Bollinger_Upper_20_2SD": number((sma20 + 2 * std20).iloc[-1]),
            "Bollinger_Middle_20": number(sma20.iloc[-1]),
            "Bollinger_Lower_20_2SD": number((sma20 - 2 * std20).iloc[-1]),
            "ATR_14": number(atr), "Annualized_Volatility": number(annualized_vol),
            "Max_Drawdown_Period": number(drawdown.min()),
            {"1d": "Return_1d", "1wk": "Return_1wk", "1mo": "Return_1mo_bar"}.get(interval, "Return_1d"): number(returns.iloc[-1] * 100),
            "Return_1mo_approx": number((close.iloc[-1] / close.iloc[-min({"1d": 22, "1wk": 4, "1mo": 2}.get(interval, 22), len(close))] - 1) * 100),
        }
        return {
            "success": True,
            "metrics": metrics,
            "scenario_estimate": {
                "method": "historical log-return drift and volatility; lognormal 80% interval",
                "horizon_bars": horizon_bars,
                "bar_interval": interval,
                **({"horizon_trading_days": horizon_bars} if interval == "1d" else {}),
                "central_estimate": center,
                "lower_80_percent": lower,
                "upper_80_percent": upper,
                "historical_bar_volatility": number(sigma),
                **({"historical_daily_volatility": number(sigma)} if interval == "1d" else {}),
                "persistence_baseline_holdout_mae": baseline_mae,
                "holdout_observations": holdout,
                "limitations": "Illustrative statistical scenario, not a validated investment forecast. Assumes historical return distribution persists; excludes fees, corporate actions, regime changes, and market events.",
            },
            "ml_analysis": walk_forward_return_model(close, interval=interval),
            "data": {"observations": int(len(close)), "latest_close": current},
        }
    except Exception as exc:
        return {"success": False, "error": f"Unable to calculate technical metrics: {exc}"}
