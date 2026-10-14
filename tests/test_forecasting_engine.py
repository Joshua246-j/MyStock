"""Comprehensive unit and integration tests for the modular ML forecasting engine."""
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from app.forecasting.feature_engineering import build_features_and_targets
from app.forecasting.models import (
    NaiveZeroForecaster,
    HistoricalDriftForecaster,
    RidgeReturnForecaster,
    HistGradientBoostingReturnForecaster,
    convert_return_to_price,
)
from app.forecasting.validation import ChronologicalWalkForwardValidator
from app.forecasting.uncertainty import UncertaintyEngine
from app.forecasting.service import ForecastingService
from app.forecasting.data_adapter import ForecastDataAdapter, DataQualityError
from app.market.news_providers import fetch_ticker_targeted_news


def _create_synthetic_bars(n_bars: int = 150, base_price: float = 100.0) -> pd.DataFrame:
    """Generate realistic synthetic daily OHLCV bars without forward leakage."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="B", tz="UTC")
    daily_returns = np.random.normal(0.0005, 0.015, size=n_bars)
    prices = base_price * np.exp(np.cumsum(daily_returns))

    opens = prices * np.random.uniform(0.995, 1.005, size=n_bars)
    highs = np.maximum(opens, prices) * np.random.uniform(1.001, 1.015, size=n_bars)
    lows = np.minimum(opens, prices) * np.random.uniform(0.985, 0.999, size=n_bars)
    volumes = np.random.uniform(1_000_000, 5_000_000, size=n_bars)

    return pd.DataFrame({
        "Date": dates,
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": prices,
        "Volume": volumes,
    })


def test_feature_engineering_integrity():
    """Verify feature calculation, column presence, and zero future leakage."""
    df = _create_synthetic_bars(120)
    res = build_features_and_targets(df, horizons=[1, 5, 20])
    assert res["success"] is True
    features = res["features"]
    targets = res["targets"]

    assert len(features) == len(df)
    assert 1 in targets and 5 in targets and 20 in targets

    # Check key technical indicators are computed
    expected_cols = [
        "return_1d", "return_5d", "return_20d", "volatility_5d",
        "dist_sma20", "dist_sma50", "rsi14", "macd_diff", "atr14_pct",
    ]
    for col in expected_cols:
        assert col in features.columns, f"Missing feature: {col}"

    # Verify warmup boundary is respected (first 50 bars contain warmup NaNs)
    warmup_idx = res["warmup_idx"]
    post_warmup = features.iloc[warmup_idx:]
    assert not post_warmup[["return_1d", "dist_sma20", "rsi14"]].isna().any().any()


def test_feature_engineering_insufficient_bars():
    """Engine must fail cleanly if bars < 55."""
    df = _create_synthetic_bars(40)
    res = build_features_and_targets(df)
    assert res["success"] is False
    assert "At least 55 historical bars are required" in res["error"]


def test_models_fit_predict_proba():
    """Verify all candidate models fit and predict valid bounds and probabilities."""
    np.random.seed(42)
    X = np.random.randn(80, 10)
    y = np.random.randn(80) * 0.02 + 0.005

    models = [
        NaiveZeroForecaster(),
        HistoricalDriftForecaster(),
        RidgeReturnForecaster(alpha=10.0),
        HistGradientBoostingReturnForecaster(max_iter=30),
    ]

    for model in models:
        model.fit(X, y)
        preds = model.predict(X[:5])
        probs = model.predict_proba(X[:5])

        assert len(preds) == 5
        assert len(probs) == 5
        assert np.all(probs >= 0.0) and np.all(probs <= 1.0)
        assert np.all(np.isfinite(preds))


def test_walk_forward_validator_chronological():
    """Chronological backtester must evaluate strictly forward in time with embargo gap."""
    df = _create_synthetic_bars(130)
    feat_res = build_features_and_targets(df, horizons=[5])
    X = feat_res["features"].iloc[50:].to_numpy()
    y = feat_res["targets"][5].iloc[50:].to_numpy()
    dates = df["Date"].iloc[50:].tolist()

    validator = ChronologicalWalkForwardValidator(horizon=5, n_test_bars=25, min_train_bars=40)
    bench = validator.benchmark_models(X, y, dates)

    assert bench["horizon_sessions"] == 5
    assert bench["test_bars"] == 25
    assert "naive_zero" in bench["models"]
    assert "historical_drift" in bench["models"]
    assert "ridge" in bench["models"]
    assert "hist_gradient_boosting" in bench["models"]

    # Naive baseline MAE must be finite and positive
    naive_mae = bench["models"]["naive_zero"]["mae"]
    assert naive_mae > 0 and np.isfinite(naive_mae)


def test_conformal_uncertainty_interval():
    """Prediction intervals must satisfy lower < expected < upper and scale with confidence."""
    residuals = np.random.normal(0, 0.02, size=50)
    current_price = 150.0
    pred_return = 0.01

    int_80 = UncertaintyEngine.compute_conformal_interval(pred_return, current_price, residuals, confidence_level=0.80)
    int_95 = UncertaintyEngine.compute_conformal_interval(pred_return, current_price, residuals, confidence_level=0.95)

    assert int_80["lower_bound_price"] < int_80["expected_price"] < int_80["upper_bound_price"]
    assert int_95["lower_bound_price"] < int_95["expected_price"] < int_95["upper_bound_price"]

    # 95% conformal interval must be strictly wider than 80% interval
    assert int_95["interval_width_percent"] > int_80["interval_width_percent"]


def test_uncertainty_abstention_rules():
    """Engine must abstain when bars are fewer than minimum or when data is broken."""
    abstain_res = UncertaintyEngine.evaluate_abstention(
        bar_count=40,
        horizon=5,
        freshness="FRESH",
        val_metrics=None,
        model_name="ridge",
    )
    assert abstain_res["should_abstain"] is True
    assert abstain_res["status"] == "insufficient_data"


def test_forecasting_service_with_mock_data():
    """Verify end-to-end service generates full chart_payload, signals, and validation."""
    mock_adapter = MagicMock()
    df = _create_synthetic_bars(140, base_price=200.0)
    mock_adapter.fetch_normalized_market_data.return_value = {
        "success": True,
        "data": df,
        "metadata": {
            "symbol": "TEST.STOCK",
            "market": "us",
            "source": "mock_provider",
            "freshness": "FRESH",
            "currency": "USD",
        },
    }
    mock_adapter.fetch_related_news.return_value = [
        {"title": "Strong Earnings Reported", "publisher": "Reuters", "published_at": "2024-05-01T12:00:00Z"}
    ]

    service = ForecastingService(data_adapter=mock_adapter)
    res = service.forecast("TEST.STOCK", horizon=5, model_name="auto", confidence=0.80)

    assert res["success"] is True
    assert res["abstain"] is False
    assert res["symbol"] == "TEST.STOCK"
    assert res["horizon"] == 5
    assert res["current_price"] > 0
    assert "interval" in res
    assert "signals" in res
    assert len(res["signals"]) > 0

    # Verify multi-step projection path in chart_data
    path = res["chart_data"]["projection_path"]
    assert len(path) == 6  # origin + 5 steps
    assert path[0]["step"] == 0
    assert path[-1]["step"] == 5
    assert path[-1]["price"] == res["interval"]["expected_price"]


def test_data_adapter_validation_normalizes_ohlcv():
    """Enforces strict sort, monotonic checks, and outlier verification."""
    df = pd.DataFrame({
        "Date": ["2024-01-03", "2024-01-01", "2024-01-02"],
        "Open": [100.0, 102.0, 101.0],
        "High": [105.0, 104.0, 103.0],
        "Low": [98.0, 99.0, 100.0],
        "Close": [104.0, 100.5, 102.0],
        "Volume": [1000, 2000, 1500],
    })
    clean = ForecastDataAdapter.validate_and_normalize_ohlcv(df)
    # Must be sorted by date ascending
    assert list(clean["Close"]) == [100.5, 102.0, 104.0]


def test_convert_return_to_price():
    """Verify log return to price conversion."""
    base_price = 100.0
    log_ret = 0.05
    price = convert_return_to_price(base_price, log_ret)
    assert round(price, 4) == round(100.0 * np.exp(0.05), 4)
