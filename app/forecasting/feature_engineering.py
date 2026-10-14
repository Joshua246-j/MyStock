"""Leak-free feature engineering and target generation for financial forecasting."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from app.forecasting.sentiment import aggregate_point_in_time_sentiment

logger = logging.getLogger("stockrag.forecasting.feature_engineering")


def build_features_and_targets(
    df: pd.DataFrame,
    news_items: list[dict[str, Any]] | None = None,
    horizons: list[int] = [1, 5, 20],
) -> dict[str, Any]:
    """Generate point-in-time features and horizon forward return targets.

    Zero-leakage guarantee:
    - Feature calculations at index t use only data up to index t.
    - News aggregation for row t uses only articles published <= timestamp t.
    - Target for row t and horizon h is log(Close[t+h] / Close[t]).
    """
    if len(df) < 55:
        return {
            "success": False,
            "error": "At least 55 historical bars are required to compute features.",
            "min_required": 55,
            "actual_bars": len(df),
        }

    frame = df.copy().sort_values("Date").reset_index(drop=True)
    close = pd.to_numeric(frame["Close"], errors="coerce")
    open_p = pd.to_numeric(frame["Open"], errors="coerce")
    high = pd.to_numeric(frame["High"], errors="coerce")
    low = pd.to_numeric(frame["Low"], errors="coerce")
    vol = pd.to_numeric(frame["Volume"], errors="coerce").fillna(0.0)

    # 1. Log returns
    log_close = np.log(close)
    r1 = log_close.diff(1)
    r2 = log_close.diff(2)
    r5 = log_close.diff(5)
    r10 = log_close.diff(10)
    r20 = log_close.diff(20)

    # 2. Rolling realized volatilities
    vol5 = r1.rolling(5, min_periods=5).std(ddof=1)
    vol20 = r1.rolling(20, min_periods=20).std(ddof=1)

    # 3. Moving averages and trends
    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    dist_sma20 = (close - sma20) / sma20
    dist_sma50 = (close - sma50) / sma50

    # 4. RSI (14-period, Wilders/EWM)
    delta = close.diff(1)
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = gain / (loss + 1e-12)
    rsi14 = 100 - (100 / (1 + rs))

    # 5. MACD normalized by price
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = (ema12 - ema26) / close
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_diff = macd_line - macd_signal

    # 6. ATR % and Intraday range
    prior_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prior_close).abs(),
        (low - prior_close).abs()
    ], axis=1).max(axis=1)
    atr14_pct = (tr.rolling(14, min_periods=14).mean()) / close
    intraday_range = (high - low) / close
    gap = (open_p - prior_close) / prior_close

    # 7. Volume dynamics
    vol_mean20 = vol.rolling(20, min_periods=20).mean()
    vol_ratio = (vol / (vol_mean20 + 1e-6)).clip(upper=10.0)

    features_dict = {
        "return_1d": r1,
        "return_2d": r2,
        "return_5d": r5,
        "return_10d": r10,
        "return_20d": r20,
        "volatility_5d": vol5,
        "volatility_20d": vol20,
        "dist_sma20": dist_sma20,
        "dist_sma50": dist_sma50,
        "rsi14": (rsi14 - 50.0) / 50.0,  # centered around 0
        "macd_line": macd_line,
        "macd_diff": macd_diff,
        "atr14_pct": atr14_pct,
        "intraday_range": intraday_range,
        "gap": gap,
        "volume_ratio": vol_ratio,
        "vol_regime": (vol5 / (vol20 + 1e-6)).clip(upper=5.0),
    }

    # 8. Point-in-time news features if available
    news_sentiment_series = [0.0] * len(frame)
    news_count_series = [0.0] * len(frame)

    if news_items:
        # Map news up to each bar timestamp
        dates = frame["Date"].tolist()
        for i, bar_dt in enumerate(dates):
            pit_sent = aggregate_point_in_time_sentiment(bar_dt, news_items, lookback_days=7)
            news_sentiment_series[i] = pit_sent["sentiment_score"]
            news_count_series[i] = float(pit_sent["news_count"])

    features_dict["news_sentiment"] = pd.Series(news_sentiment_series, index=frame.index)
    features_dict["news_count"] = pd.Series(news_count_series, index=frame.index)

    features_df = pd.DataFrame(features_dict)

    # Targets for each horizon
    targets_dict: dict[int, pd.Series] = {}
    for h in horizons:
        # Future forward cumulative return: log(Close[t+h] / Close[t])
        fwd_return = log_close.shift(-h) - log_close
        targets_dict[h] = fwd_return

    # Warmup cutoff: first 50 bars have NaNs due to rolling 50
    warmup_idx = 50

    return {
        "success": True,
        "features": features_df,
        "targets": targets_dict,
        "dates": frame["Date"],
        "closes": close,
        "warmup_idx": warmup_idx,
        "feature_names": list(features_df.columns),
    }
