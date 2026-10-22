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


def test_disagreement_engine_consensus_and_metrics():
    from app.forecasting.disagreement import DisagreementEngine

    # Simulate 5 tightly clustered models around +3% log-return
    model_predictions = {
        "historical_drift": 0.029,
        "ridge": 0.031,
        "random_forest": 0.028,
        "mlp_neural_net": 0.033,
        "hist_gradient_boosting": 0.030,
    }

    analysis = DisagreementEngine.evaluate_disagreement(
        model_predictions=model_predictions,
        reference_price=100.0,
        horizon=5,
        realized_volatility=0.015 * np.sqrt(5),
    )

    assert analysis["regime"] == "LOW_DISAGREEMENT"
    assert analysis["is_dependable_consensus"] is True
    assert analysis["spread_percent"] < 1.0
    assert analysis["bullish_count"] == 5
    assert len(analysis["outliers"]) == 0
    assert "strong" in analysis["explanation"].lower() or "candidate models" in analysis["explanation"].lower()


def test_disagreement_engine_outlier_detection():
    from app.forecasting.disagreement import DisagreementEngine

    # 4 models cluster near 0.0, 1 extreme outlier at 0.30
    model_predictions = {
        "m1": 0.005,
        "m2": -0.002,
        "m3": 0.002,
        "m4": 0.000,
        "m_outlier": 0.30,
    }

    analysis = DisagreementEngine.evaluate_disagreement(
        model_predictions=model_predictions,
        reference_price=100.0,
        horizon=5,
        realized_volatility=0.012 * np.sqrt(5),
    )

    assert len(analysis["outliers"]) >= 1
    outlier_ids = [o["model_id"] for o in analysis["outliers"]]
    assert "m_outlier" in outlier_ids


def test_conformal_interval_with_empirical_coverage():
    from app.forecasting.uncertainty import UncertaintyEngine

    rng = np.random.default_rng(42)
    # 50 holdout residuals with mean ~0, std ~0.02
    residuals = rng.normal(0, 0.02, size=50)

    interval = UncertaintyEngine.compute_conformal_interval(
        pred_return=0.03,
        current_price=100.0,
        residuals=residuals,
        confidence_level=0.80,
    )

    assert interval["lower_bound_price"] < 103.0 < interval["upper_bound_price"]
    assert interval["nominal_confidence_percent"] == 80.0
    # Coverage is descriptive because the interval and metric use the same residual sample.
    assert interval["empirical_coverage_percent"] is not None
    assert 65.0 <= interval["empirical_coverage_percent"] <= 95.0
    assert "same residual sample" in interval["calibration_verdict"] or "not independent calibration" in interval["calibration_verdict"]


def test_benchmark_models_honest_selection():
    from app.forecasting.feature_engineering import build_features_and_targets
    from app.forecasting.validation import ChronologicalWalkForwardValidator

    dates = pd.date_range("2026-06-01", periods=120, freq="B")
    prices = 100.0 + np.cumsum(np.random.default_rng(42).normal(0.1, 0.5, size=120))
    df = pd.DataFrame({
        "Date": dates,
        "Open": prices * 0.99,
        "High": prices * 1.01,
        "Low": prices * 0.98,
        "Close": prices,
        "Volume": 500000.0,
    })

    feat_res = build_features_and_targets(df, horizons=[5])
    X = feat_res["features"].iloc[45:].to_numpy()
    y = feat_res["targets"][5].iloc[45:].to_numpy()
    clean_dates = df["Date"].iloc[45:].tolist()

    validator = ChronologicalWalkForwardValidator(horizon=5, n_test_bars=15, min_train_bars=40)
    benchmark = validator.benchmark_models(
        X=X,
        y=y,
        dates=clean_dates,
        models_to_evaluate=["historical_drift", "naive_zero", "ridge"],
    )

    assert "selected_best_model" in benchmark
    assert "models" in benchmark
    assert "historical_drift" in benchmark["models"]
    assert "naive_zero" in benchmark["models"]
    assert "ridge" in benchmark["models"]

    # Verify that selected_best_model has the lowest valid MAE beating naive_zero
    best_id = benchmark["selected_best_model"]
    best_mae = benchmark["models"][best_id]["mae_percent"]
    for m_id, m_metrics in benchmark["models"].items():
        if m_id != "naive_zero" and m_metrics.get("mae_percent") is not None:
            assert m_metrics["mae_percent"] >= best_mae


def test_data_adapter_indian_currency_normalization():
    from app.forecasting.data_adapter import ForecastDataAdapter

    class DummyMarketService:
        def get_history(self, symbol, **kwargs):
            dates = pd.date_range("2026-06-01", periods=60, freq="B")
            prices = 1000.0 + np.cumsum(np.random.default_rng(42).normal(0.5, 2.0, size=60))
            return {
                "success": True,
                "data": [
                    {
                        "Date": str(d)[:10],
                        "Open": float(p * 0.99),
                        "High": float(p * 1.01),
                        "Low": float(p * 0.98),
                        "Close": float(p),
                        "Volume": 50000.0,
                    }
                    for d, p in zip(dates, prices)
                ],
                "last_bar_at": "2026-10-20T15:30:00+05:30",
                "retrieved_at": "2026-10-21T06:00:00Z",
                "data_status": "FRESH",
            }

    adapter = ForecastDataAdapter(market_service=DummyMarketService())
    res = adapter.fetch_normalized_market_data("RELIANCE.NS")
    assert res["success"] is True
    assert res["metadata"]["market"] == "india"
    assert res["metadata"]["currency"] == "INR"


def test_disagreement_engine_schema_keys():
    from app.forecasting.disagreement import DisagreementEngine

    analysis = DisagreementEngine.evaluate_disagreement(
        model_predictions={"m1": 0.01, "m2": 0.02, "m3": -0.01, "m4": 0.005},
        reference_price=100.0,
        horizon=5,
    )

    required_keys = [
        "regime", "label", "badge_color", "reliability_tag", "dispersion_percent",
        "spread_percent", "min_return_percent", "max_return_percent", "mean_return_percent",
        "median_return_percent", "directional_consensus", "bullish_count", "bearish_count",
        "neutral_count", "total_models", "outliers", "is_dependable_consensus", "explanation"
    ]
    for key in required_keys:
        assert key in analysis, f"Missing key: {key}"


def test_system_health_endpoint_diagnostics_structure():
    import asyncio
    from app.api.routes.forecast import get_system_health

    health_data = asyncio.run(get_system_health())
    assert health_data["success"] is True
    assert "system_profile" in health_data
    assert "diagnostics" in health_data
    assert "data_providers" in health_data
    assert "model_registry" in health_data

    sys_prof = health_data["system_profile"]
    assert "cpu_cores" in sys_prof
    assert "cpu_percent" in sys_prof
    assert "ram_total_gb" in sys_prof
    assert "ram_available_gb" in sys_prof
    assert "gpu_available" in sys_prof

    diag = health_data["diagnostics"]
    assert "healthy" in diag
    assert "engine_status" in diag

    models = health_data["model_registry"]
    expected_models = [
        "historical_drift", "naive_zero", "ridge", "hist_gradient_boosting",
        "random_forest", "mlp_neural_net", "exponential_smoothing", "custom_model"
    ]
    for m in expected_models:
        assert m in models
        assert "name" in models[m]
        assert "model_type" in models[m]
        assert "hardware_requirements" in models[m]
        assert "availability" in models[m]


def test_prompt_builder_institutional_forecast_directives():
    from app.analysis.prompt_builder import PromptBuilder

    builder = PromptBuilder()
    evidence = [
        "MARKET QUOTE (AAPL; provider=yfinance): price=230.50, change=+2.10 (+0.92%), timestamp=2026-10-21T15:30:00Z.",
        "VALIDATED PROBABILISTIC FORECAST (AAPL; horizon=5 sessions; current price=230.50 USD): expected_return=+2.4%, 80% interval=[225.0 – 236.0]",
    ]

    messages = builder.build(
        message="Analyze AAPL market and forecast outlook",
        history=[],
        context_sections=evidence,
        detail_instruction="Standard institutional analysis",
    )

    user_content = messages[-1]["content"]
    assert "Probabilistic Forecast & Multi-Model Outlook" in user_content
    assert "Market Snapshot" in user_content
    assert "Technical Trend & Momentum" in user_content


def test_custom_csv_upload_and_forecast_pipeline():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=130, freq="D")
    df = pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"),
        "Close": [100.0 + i * 0.4 + (i % 4) for i in range(130)],
    })
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    res = client.post(
        "/api/forecast/upload",
        files={"file": ("custom_asset.csv", csv_bytes, "text/csv")},
        data={"horizon": "5", "model": "auto", "confidence": "0.80"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "interval" in data
    assert data["interval"]["expected_price"] > 0
    assert "chart_data" in data
    assert len(data.get("history_bars", [])) > 0
    assert "benchmark_comparison" in data
