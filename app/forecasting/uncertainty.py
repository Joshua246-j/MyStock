"""Calibrated prediction intervals and principled abstention logic."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("stockrag.forecasting.uncertainty")


class UncertaintyEngine:
    """Computes calibrated prediction intervals and enforces abstention boundaries."""

    @staticmethod
    def compute_conformal_interval(
        pred_return: float,
        current_price: float,
        residuals: np.ndarray,
        confidence_level: float = 0.80,
    ) -> dict[str, Any]:
        """Compute conformal prediction interval from empirical out-of-sample residuals.

        Guarantees non-parametric, calibrated coverage reflecting the actual empirical
        error distribution rather than assuming Gaussian i.i.d. normality.
        """
        residuals_arr = np.asarray(residuals, dtype=float)
        valid_residuals = residuals_arr[np.isfinite(residuals_arr)]
        n_res = len(valid_residuals)

        alpha = 1.0 - confidence_level

        if n_res >= 15:
            # Empirical conformal quantiles
            q_lower = float(np.percentile(valid_residuals, (alpha / 2.0) * 100.0))
            q_upper = float(np.percentile(valid_residuals, (1.0 - alpha / 2.0) * 100.0))
            method = "empirical_conformal_quantiles"
        else:
            # Fallback to Student-t distribution with fat tails (df=4)
            std_res = float(np.std(valid_residuals, ddof=1)) if n_res > 2 else 0.03
            t_multiplier = 1.53 if confidence_level <= 0.80 else 2.13
            q_lower = -t_multiplier * std_res
            q_upper = t_multiplier * std_res
            method = "fat_tailed_t_distribution_fallback"

        lower_return = pred_return + q_lower
        upper_return = pred_return + q_upper

        lower_price = current_price * np.exp(lower_return)
        upper_price = current_price * np.exp(upper_return)
        expected_price = current_price * np.exp(pred_return)

        interval_width_pct = ((upper_price - lower_price) / current_price) * 100.0

        expected_return_pct = ((expected_price - current_price) / current_price) * 100.0 if current_price > 0 else 0.0
        lower_return_pct = ((lower_price - current_price) / current_price) * 100.0 if current_price > 0 else 0.0
        upper_return_pct = ((upper_price - current_price) / current_price) * 100.0 if current_price > 0 else 0.0

        return {
            "confidence_level": confidence_level,
            "confidence_percent": int(confidence_level * 100),
            "method": method,
            "residual_sample_size": n_res,
            "expected_return_percent": round(float(expected_return_pct), 3),
            "expected_price": round(float(expected_price), 4),
            "lower_bound_price": round(float(lower_price), 4),
            "upper_bound_price": round(float(upper_price), 4),
            "lower_bound_return": round(float(lower_return), 5),
            "upper_bound_return": round(float(upper_return), 5),
            "lower_bound_return_percent": round(float(lower_return_pct), 3),
            "upper_bound_return_percent": round(float(upper_return_pct), 3),
            "interval_width_percent": round(float(interval_width_pct), 2),
        }

    @staticmethod
    def evaluate_abstention(
        bar_count: int,
        horizon: int,
        freshness: str,
        val_metrics: dict[str, Any] | None,
        model_name: str,
    ) -> dict[str, Any]:
        """Check criteria for principled forecast abstention.

        Returns:
            dict with should_abstain, status_code, and explanatory reason.
        """
        # 1. Minimum historical data check
        min_required = {1: 65, 5: 110, 20: 170}.get(horizon, 110)
        if bar_count < min_required:
            return {
                "should_abstain": True,
                "status": "insufficient_data",
                "reason": (
                    f"Available historical bars ({bar_count}) is below the minimum required "
                    f"threshold ({min_required}) for reliable {horizon}-session forecasting."
                ),
                "severity": "high",
            }

        # 2. Extreme staleness check
        if freshness == "STALE":
            return {
                "should_abstain": False,
                "status": "stale_data_warning",
                "reason": "Market history appears stale (last bar >5 days old). Forecast uncertainty is elevated.",
                "severity": "medium",
            }

        # 3. Model reliability check
        if val_metrics and val_metrics.get("available"):
            beats = val_metrics.get("beats_naive_baseline", True)
            impr = val_metrics.get("improvement_vs_naive_percent", 0.0)

            # If model is more than 15% worse than naive zero return, flag unreliable
            if impr < -15.0:
                return {
                    "should_abstain": True,
                    "status": "unreliable_model",
                    "reason": (
                        f"Model {model_name} demonstrated out-of-sample error {abs(impr):.1f}% worse "
                        f"than the naive baseline. Model has been withheld in favor of baseline drift."
                    ),
                    "severity": "high",
                }

        return {
            "should_abstain": False,
            "status": "validated",
            "reason": "All data quality, horizon, and validation gates passed.",
            "severity": "low",
        }
