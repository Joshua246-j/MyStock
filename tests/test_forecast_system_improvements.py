"""Unit and integration tests for hardware-aware model registry, system diagnostics, and audit persistence."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.db.database import SessionLocal, init_db
from app.db.models import ForecastRecord
from app.forecasting.hardware import evaluate_model_availability, get_hardware_profile
from app.forecasting.models import CustomQuantitativeForecaster, HistoricalDriftForecaster, NaiveZeroForecaster
from app.forecasting.service import ForecastingService, MODEL_METADATA


def test_hardware_profiling_integrity():
    hw = get_hardware_profile()
    assert "cpu" in hw
    assert "memory" in hw
    assert "gpu" in hw
    assert "runtime" in hw
    assert hw["cpu"]["logical_cores"] >= 1
    assert hw["memory"]["total_gb"] > 0
    assert hw["memory"]["available_gb"] >= 0
    assert isinstance(hw["gpu"]["available"], bool)
    assert hw["health_state"] in ("HEALTHY", "RESOURCE_CONSTRAINED")
    assert hw["runtime"]["dependencies"]["numpy"] is True
    assert hw["runtime"]["dependencies"]["pandas"] is True


def test_model_availability_states():
    # 1. Ready state with adequate bars
    res_ready = evaluate_model_availability("historical_drift", bar_count=120, freshness="FRESH")
    assert res_ready["state"] == "Ready"
    assert res_ready["is_executable"] is True

    # 2. Insufficient data state (<55 bars)
    res_sparse = evaluate_model_availability("historical_drift", bar_count=30, freshness="FRESH")
    assert res_sparse["state"] == "Insufficient Data"
    assert res_sparse["is_executable"] is False

    # 3. Stale data state
    res_stale = evaluate_model_availability("historical_drift", bar_count=120, freshness="STALE")
    assert res_stale["state"] == "Stale"
    assert res_stale["is_executable"] is True


def test_custom_quantitative_forecaster():
    custom = CustomQuantitativeForecaster(
        name="custom_momentum",
        momentum_weight=0.8,
        mean_reversion_weight=0.3,
        l2_penalty=5.0,
    )
    rng = np.random.default_rng(42)
    X = rng.normal(size=(40, 5))
    y = 0.05 * X[:, 0] - 0.02 * X[:, 1] + rng.normal(scale=0.01, size=40)

    custom.fit(X, y)
    assert custom.is_fitted is True

    preds = custom.predict(X[:5])
    assert len(preds) == 5
    assert np.all(np.isfinite(preds))


def test_forecast_persistence_and_realized_outcome():
    init_db()
    # Create synthetic price bars
    dates = pd.date_range("2026-08-01", periods=80, freq="B")
    prices = 100.0 + np.cumsum(np.random.default_rng(42).normal(0.2, 1.0, size=len(dates)))
    df = pd.DataFrame({
        "Date": dates,
        "Open": prices * 0.99,
        "High": prices * 1.01,
        "Low": prices * 0.98,
        "Close": prices,
        "Volume": 1000000.0,
    })

    service = ForecastingService()
    # Test persistence helper directly
    outcomes = service._sync_and_persist_forecast_records(
        symbol="TEST_PERSIST",
        horizon=5,
        model_name="historical_drift",
        current_price=150.0,
        last_date_str="2026-10-14",
        target_date_str="2026-10-21",
        expected_price=153.0,
        expected_return_pct=2.0,
        lower_price=148.0,
        upper_price=158.0,
        confidence=0.80,
        directional_prob=0.62,
        val_metrics={"mae_percent": 1.5, "rmse_percent": 2.0, "test_sample_size": 30},
        df_history=df,
    )

    with SessionLocal() as db:
        rec = db.query(ForecastRecord).filter(ForecastRecord.symbol == "TEST_PERSIST").first()
        assert rec is not None
        assert rec.expected_price == 153.0
        assert rec.horizon == 5
        assert rec.status == "pending"

        # Clean up test record
        db.delete(rec)
        db.commit()


def test_model_metadata_completeness():
    assert "historical_drift" in MODEL_METADATA
    assert "naive_zero" in MODEL_METADATA
    assert "ridge" in MODEL_METADATA
    assert "hist_gradient_boosting" in MODEL_METADATA
    assert "custom_model" in MODEL_METADATA

    drift = MODEL_METADATA["historical_drift"]
    assert drift["is_default"] is True
    assert "formula" in drift
    assert "methodology" in drift
    assert "strengths" in drift
    assert "limitations" in drift
    assert "hardware_profile" in drift
