"""Calibrated prediction intervals and principled abstention logic."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("stockrag.forecasting.uncertainty")


class UncertaintyEngine:
    """Computes residual-based intervals and enforces abstention boundaries."""

    @staticmethod
    def compute_conformal_interval(
        pred_return: float,
        current_price: float,
        residuals: np.ndarray,
        confidence_level: float = 0.80,
    ) -> dict[str, Any]:
        """Compute a residual interval and report its calibration limits.

        Quantiles and empirical coverage use the same walk-forward residual sample,
        so coverage is descriptive and does not imply independent calibration.
        """
        residuals_arr = np.asarray(residuals, dtype=float)
        valid_residuals = residuals_arr[np.isfinite(residuals_arr)]
        n_res = len(valid_residuals)

        alpha = 1.0 - confidence_level

        if n_res >= 15:
            # Empirical quantiles of the walk-forward residuals.
            q_lower = float(np.percentile(valid_residuals, (alpha / 2.0) * 100.0))
            q_upper = float(np.percentile(valid_residuals, (1.0 - alpha / 2.0) * 100.0))
            method = "walk_forward_residual_quantiles"
        else:
            # Fallback to Student-t distribution with fat tails (df=4)
            std_res = float(np.std(valid_residuals, ddof=1)) if n_res > 2 else 0.03
            t_multiplier = 1.53 if confidence_level <= 0.80 else 2.13
            q_lower = -t_multiplier * std_res
            q_upper = t_multiplier * std_res
            method = "student_t_parametric_fallback"

        lower_return = pred_return + q_lower
        upper_return = pred_return + q_upper

        lower_price = current_price * np.exp(lower_return)
        upper_price = current_price * np.exp(upper_return)
        expected_price = current_price * np.exp(pred_return)

        interval_width_pct = ((upper_price - lower_price) / current_price) * 100.0

        expected_return_pct = ((expected_price - current_price) / current_price) * 100.0 if current_price > 0 else 0.0
        lower_return_pct = ((lower_price - current_price) / current_price) * 100.0 if current_price > 0 else 0.0
        upper_return_pct = ((upper_price - current_price) / current_price) * 100.0 if current_price > 0 else 0.0

        # Compute genuine empirical coverage across the holdout validation residuals
        if n_res > 0:
            covered_count = int(np.sum((valid_residuals >= q_lower) & (valid_residuals <= q_upper)))
            emp_cov_pct = round((covered_count / n_res) * 100.0, 1)
        else:
            covered_count = 0
            emp_cov_pct = round(confidence_level * 100.0, 1)

        cov_gap = round(emp_cov_pct - (confidence_level * 100.0), 1)
        if n_res < 15:
            cal_verdict = "Not assessed (fewer than 15 residual samples)"
        elif abs(cov_gap) <= 5.0:
            cal_verdict = "Descriptive in-sample coverage (not independent calibration)"
        elif cov_gap < -5.0:
            cal_verdict = "Descriptive undercoverage (same residual sample)"
        else:
            cal_verdict = "Descriptive overcoverage (same residual sample)"

        return {
            "confidence_level": confidence_level,
            "confidence_percent": int(confidence_level * 100),
            "nominal_confidence_percent": int(confidence_level * 100),
            "empirical_coverage_percent": emp_cov_pct,
            "empirical_covered_samples": covered_count,
            "residual_sample_size": n_res,
            "coverage_gap_percent": cov_gap,
            "calibration_verdict": cal_verdict,
            "method": method,
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

        # A market forecast is not reliable when its observation cutoff is stale
        # or unknown. Do not emit a numeric projection on unverifiable inputs.
        if freshness == "STALE":
            return {
                "should_abstain": True,
                "status": "stale_data",
                "reason": "The latest available market history is marked stale; a current forecast was withheld.",
                "severity": "high",
            }

        if freshness != "FRESH":
            return {
                "should_abstain": True,
                "status": "unknown_freshness",
                "reason": "Market observation freshness could not be verified; a current forecast was withheld.",
                "severity": "high",
            }

        if not val_metrics or not val_metrics.get("available") or len(val_metrics.get("residuals", [])) < 10:
            return {
                "should_abstain": True,
                "status": "insufficient_validation",
                "reason": "There are not enough valid out-of-sample residuals to support this forecast and its uncertainty interval.",
                "severity": "high",
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
