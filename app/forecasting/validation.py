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

    def __init__(self, horizon: int = 5, n_test_bars: int = 15, min_train_bars: int = 40):
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
        models_to_evaluate: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run standardized benchmark comparing candidate models using identical chronological splits.

        Zero fabrication guarantee: Every model reported as evaluated is genuinely fitted
        and evaluated out-of-sample across the exact same purged embargo test windows.
        Models not evaluated are explicitly marked 'unevaluated'.
        """
        model_factories = {
            "naive_zero": lambda: NaiveZeroForecaster(),
            "historical_drift": lambda: HistoricalDriftForecaster(),
            "exponential_smoothing": lambda: ExponentialSmoothingForecaster(),
            "ridge": lambda: RidgeReturnForecaster(alpha=10.0),
            "hist_gradient_boosting": lambda: HistGradientBoostingReturnForecaster(),
            "random_forest": lambda: RandomForestReturnForecaster(),
            "mlp_neural_net": lambda: MLPNeuralReturnForecaster(),
        }

        eval_set = set(models_to_evaluate) if models_to_evaluate is not None else set(model_factories.keys())
        eval_set.add("naive_zero")  # Always include the persistence hurdle

        results_models: dict[str, Any] = {}

        for m_key, factory in model_factories.items():
            if m_key in eval_set:
                try:
                    res = self.evaluate_model(factory, X, y, dates)
                    if res.get("available"):
                        res["status"] = "evaluated"
                    else:
                        res["status"] = "insufficient_evidence"
                    results_models[m_key] = res
                except Exception as exc:
                    results_models[m_key] = {
                        "available": False,
                        "status": "failed",
                        "reason": f"Evaluation error: {exc}",
                    }
            else:
                results_models[m_key] = {
                    "available": False,
                    "status": "unevaluated",
                    "reason": "Not included in evaluation request",
                }

        # Compare candidates to baseline
        naive_metrics = results_models.get("naive_zero", {})
        baseline_mae = naive_metrics.get("mae", float("inf")) if naive_metrics.get("available") else float("inf")

        for m_key, m_res in results_models.items():
            if m_key == "naive_zero":
                m_res["improvement_vs_naive_percent"] = 0.0
                m_res["beats_naive_baseline"] = False
                m_res["selection_status"] = "baseline_hurdle"
                continue

            if m_res.get("available") and np.isfinite(baseline_mae) and baseline_mae > 0:
                m_mae = m_res.get("mae", float("inf"))
                if np.isfinite(m_mae):
                    impr = ((baseline_mae - m_mae) / baseline_mae) * 100.0
                    m_res["improvement_vs_naive_percent"] = round(impr, 2)
                    m_res["beats_naive_baseline"] = m_mae < baseline_mae
                else:
                    m_res["improvement_vs_naive_percent"] = 0.0
                    m_res["beats_naive_baseline"] = False
            else:
                m_res["improvement_vs_naive_percent"] = 0.0
                m_res["beats_naive_baseline"] = False

        # Selection of best model by Min OOS MAE among evaluated models
        candidates = []
        for m_key, m_res in results_models.items():
            if m_res.get("available") and m_res.get("test_sample_size", 0) >= 10:
                mae = m_res.get("mae")
                if mae is not None and np.isfinite(mae) and mae > 0:
                    candidates.append((m_key, mae, m_res.get("beats_naive_baseline", False)))

        if candidates:
            candidates.sort(key=lambda item: item[1])
            best_key, best_mae, beats = candidates[0]
            selection_reason = (
                f"Lowest holdout MAE ({results_models[best_key].get('mae_percent')}%) "
                f"across {results_models[best_key].get('test_sample_size')} out-of-sample sessions"
            )
            if not beats and best_key != "naive_zero":
                selection_reason += " (underperforms zero-return baseline)"
        else:
            best_key = "historical_drift"
            selection_reason = "Default empirical drift baseline (insufficient evidence to rank ML)"

        for m_key, m_res in results_models.items():
            if m_key == best_key:
                m_res["selection_status"] = "selected_best"
            elif m_key == "naive_zero":
                m_res["selection_status"] = "baseline_hurdle"
            elif m_res.get("available"):
                m_res["selection_status"] = "evaluated"
            else:
                m_res["selection_status"] = m_res.get("status", "unavailable")

        return {
            "horizon_sessions": self.horizon,
            "test_bars": self.n_test_bars,
            "selection_metric": "Min OOS MAE",
            "selected_best_model": best_key,
            "selection_reason": selection_reason,
            "models": results_models,
        }
