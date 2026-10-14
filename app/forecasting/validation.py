"""Chronological walk-forward backtesting with purged gaps and baseline comparisons."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app.forecasting.models import (
    BaseForecaster,
    ExponentialSmoothingForecaster,
    HistoricalDriftForecaster,
    HistGradientBoostingReturnForecaster,
    MLPNeuralReturnForecaster,
    NaiveZeroForecaster,
    RandomForestReturnForecaster,
    RidgeReturnForecaster,
)

logger = logging.getLogger("stockrag.forecasting.validation")


class ChronologicalWalkForwardValidator:
    """Walk-forward backtester that enforces temporal ordering and purged embargo gaps."""

    def __init__(self, horizon: int = 5, n_test_bars: int = 30, min_train_bars: int = 50):
        self.horizon = horizon
        self.n_test_bars = n_test_bars
        self.min_train_bars = min_train_bars

    def evaluate_model(
        self,
        model_factory: Any,
        X: np.ndarray,
        y: np.ndarray,
        dates: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Perform expanding-window chronological walk-forward evaluation.

        Purged embargo gap:
        For a test observation at index t, training samples must have realized labels
        before t, meaning training index i satisfies i + horizon <= t.
        """
        valid_mask = np.isfinite(y)
        indices = np.where(valid_mask)[0]

        total_obs = len(indices)
        if total_obs < self.min_train_bars + self.n_test_bars:
            return {
                "available": False,
                "reason": (
                    f"Insufficient observations ({total_obs}) for walk-forward validation "
                    f"with horizon {self.horizon}. Require at least {self.min_train_bars + self.n_test_bars}."
                ),
            }

        split_start = total_obs - self.n_test_bars
        test_indices = indices[split_start:]

        preds: list[float] = []
        actuals: list[float] = []
        prob_preds: list[float] = []
        eval_dates: list[str] = []

        for t_idx in test_indices:
            # Purge gap: train on samples where target has realized before t_idx
            train_mask = indices <= (t_idx - self.horizon)
            train_idx = indices[train_mask]

            if len(train_idx) < self.min_train_bars:
                continue

            X_train = X[train_idx]
            y_train = y[train_idx]
            X_test = X[t_idx : t_idx + 1]
            y_actual = y[t_idx]

            model: BaseForecaster = model_factory()
            model.fit(X_train, y_train)

            pred_return = float(model.predict(X_test)[0])
            pred_prob = float(model.predict_proba(X_test)[0])

            preds.append(pred_return)
            actuals.append(float(y_actual))
            prob_preds.append(pred_prob)
            if dates is not None and t_idx < len(dates):
                eval_dates.append(str(dates[t_idx])[:10])

        if len(actuals) < 10:
            return {
                "available": False,
                "reason": "Fewer than 10 test evaluations survived purged embargo splitting.",
            }

        preds_arr = np.asarray(preds, dtype=float)
        actuals_arr = np.asarray(actuals, dtype=float)
        probs_arr = np.asarray(prob_preds, dtype=float)

        residuals = actuals_arr - preds_arr
        mae = float(np.mean(np.abs(residuals)))
        rmse = float(np.sqrt(np.mean(residuals ** 2)))

        # Directional accuracy: sign agreement
        direction_pred = preds_arr > 0
        direction_actual = actuals_arr > 0
        directional_acc = float(np.mean(direction_pred == direction_actual))

        # Brier score for directional probabilities
        brier_score = float(np.mean((probs_arr - direction_actual.astype(float)) ** 2))

        return {
            "available": True,
            "test_sample_size": len(actuals),
            "mae": round(mae, 5),
            "mae_percent": round(mae * 100.0, 3),
            "rmse": round(rmse, 5),
            "rmse_percent": round(rmse * 100.0, 3),
            "directional_accuracy_percent": round(directional_acc * 100.0, 1),
            "brier_score": round(brier_score, 4),
            "residuals": [round(float(r), 6) for r in residuals.tolist()],
            "predictions": [round(float(p), 6) for p in preds_arr.tolist()],
            "actuals": [round(float(a), 6) for a in actuals_arr.tolist()],
            "eval_dates": eval_dates,
        }

    def benchmark_models(
        self,
        X: np.ndarray,
        y: np.ndarray,
        dates: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Run standardized benchmark comparing candidates against Naive Zero and Historical Drift baselines."""
        naive_metrics = self.evaluate_model(lambda: NaiveZeroForecaster(), X, y, dates)
        drift_metrics = self.evaluate_model(lambda: HistoricalDriftForecaster(), X, y, dates)
        ridge_metrics = self.evaluate_model(lambda: RidgeReturnForecaster(alpha=10.0), X, y, dates)
        hgb_metrics = self.evaluate_model(lambda: HistGradientBoostingReturnForecaster(), X, y, dates)
        rf_metrics = self.evaluate_model(lambda: RandomForestReturnForecaster(), X, y, dates)
        mlp_metrics = self.evaluate_model(lambda: MLPNeuralReturnForecaster(), X, y, dates)
        exp_metrics = self.evaluate_model(lambda: ExponentialSmoothingForecaster(), X, y, dates)

        results: dict[str, Any] = {
            "horizon_sessions": self.horizon,
            "test_bars": self.n_test_bars,
            "models": {
                "historical_drift": drift_metrics,
                "naive_zero": naive_metrics,
                "ridge": ridge_metrics,
                "hist_gradient_boosting": hgb_metrics,
                "random_forest": rf_metrics,
                "mlp_neural_net": mlp_metrics,
                "exponential_smoothing": exp_metrics,
            },
        }

        # Compare candidates to baseline
        baseline_mae = naive_metrics.get("mae", float("inf")) if naive_metrics.get("available") else float("inf")

        for m_name in ["historical_drift", "ridge", "hist_gradient_boosting", "random_forest", "mlp_neural_net", "exponential_smoothing"]:
            m_res = results["models"].get(m_name, {})
            if m_res.get("available") and np.isfinite(baseline_mae) and baseline_mae > 0:
                m_mae = m_res["mae"]
                impr = ((baseline_mae - m_mae) / baseline_mae) * 100.0
                m_res["improvement_vs_naive_percent"] = round(impr, 2)
                m_res["beats_naive_baseline"] = m_mae < baseline_mae
            else:
                m_res["improvement_vs_naive_percent"] = 0.0
                m_res["beats_naive_baseline"] = False

        return results
