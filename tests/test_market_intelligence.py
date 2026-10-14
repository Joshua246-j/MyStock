import numpy as np
import pandas as pd

from app.analysis.technical import calculate_technical_indicators, walk_forward_return_model
from app.market.service import MarketDataService


def test_walk_forward_model_reports_holdout_and_baseline_without_overstating_results():
    random = np.random.default_rng(17)
    returns = random.normal(0.0003, 0.012, 180)
    close = pd.Series(100 * np.exp(np.cumsum(returns)))

    result = walk_forward_return_model(close)

    assert result["available"] is True
    assert result["model"].startswith("ridge regression")
    assert result["walk_forward_holdout_sessions"] == 20
    assert np.isfinite(result["latest_next_session_return_percent"])
    assert np.isfinite(result["walk_forward_mae_percent"])
    assert np.isfinite(result["historical_mean_baseline_mae_percent"])
    assert isinstance(result["beats_baseline_mae"], bool)
    assert "not a validated forecast" in result["limitations"]


def test_technical_endpoint_includes_experimental_model_when_history_is_long_enough():
    close = 100 * np.exp(np.cumsum(np.random.default_rng(3).normal(0.0001, 0.01, 150)))
    frame = pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=len(close)),
        "Close": close,
        "High": close * 1.01,
        "Low": close * 0.99,
    })

    result = calculate_technical_indicators(frame)

    assert result["success"] is True
    assert result["ml_analysis"]["available"] is True
    assert result["ml_analysis"]["walk_forward_holdout_sessions"] > 0


def test_walk_forward_model_cleanly_reports_insufficient_history():
    result = walk_forward_return_model(pd.Series(np.linspace(100, 120, 40)))

    assert result["available"] is False
    assert "65 daily closes" in result["reason"]


def test_weekly_analysis_uses_weekly_bars_and_does_not_label_them_daily_sessions():
    close = 100 * np.exp(np.cumsum(np.random.default_rng(19).normal(0.001, 0.015, 100)))
    frame = pd.DataFrame({
        "Date": pd.date_range("2024-01-05", periods=len(close), freq="W-FRI"),
        "Close": close,
        "High": close * 1.02,
        "Low": close * 0.98,
    })

    result = calculate_technical_indicators(frame, interval="1wk")

    assert result["success"] is True
    assert result["scenario_estimate"]["horizon_bars"] == 4
    assert "horizon_trading_days" not in result["scenario_estimate"]
    assert result["ml_analysis"]["bar_interval"] == "1wk"
    assert "latest_next_session_return_percent" not in result["ml_analysis"]


def test_market_analysis_keeps_chart_metrics_visible_window_and_extends_only_ml_lookback():
    service = MarketDataService(provider=object(), fallback_providers=[], cache=object(), settings_provider=lambda: {})
    requests = []

    def history(_symbol, period, interval, refresh=False, **kwargs):
        requests.append((period, interval))
        count = 23 if period == "1mo" else 150
        close = 100 * np.exp(np.cumsum(np.random.default_rng(count).normal(0.0002, 0.01, count)))
        rows = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=count),
            "Close": close,
            "High": close * 1.01,
            "Low": close * 0.99,
        }).to_dict("records")
        return {"success": True, "data": rows, "source": "fixture", "last_bar_at": rows[-1]["Date"].isoformat()}

    service.get_history = history
    result = service.get_technical_analysis("AAPL", period="1mo", interval="1d")

    assert requests == [("1mo", "1d"), ("1y", "1d")]
    assert result["data"]["observations"] == 23
    assert result["ml_analysis"]["available"] is True
    assert result["ml_analysis"]["training_period"] == "1y"
