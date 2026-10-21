"""Statistical model disagreement, ensemble dispersion, and outlier detection."""
from __future__ import annotations

import logging
from typing import Any
import numpy as np

logger = logging.getLogger("stockrag.forecasting.disagreement")


class DisagreementEngine:
    """Evaluates multi-model dispersion, outlier predictions, and consensus dependability."""

    @staticmethod
    def evaluate_disagreement(
        model_predictions: dict[str, float],
        reference_price: float,
        horizon: int,
        realized_volatility: float | None = None,
        model_names: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Compute statistical dispersion across model log-return predictions.

        Parameters:
            model_predictions: Mapping of model_id -> predicted forward log-return.
            reference_price: Current stock price at forecast origin.
            horizon: Forecast horizon sessions (1, 5, 20).
            realized_volatility: Horizon-scaled realized volatility (e.g. daily_vol * sqrt(h)).
            model_names: Optional human-readable names for models.
        """
        names = model_names or {}
        valid_models = {
            k: float(v) for k, v in model_predictions.items()
            if np.isfinite(v) and k not in ("analyst_consensus", "algorithmic_pivot")
        }

        if len(valid_models) < 2:
            return {
                "regime": "INSUFFICIENT_MODELS",
                "label": "Single Model Only",
                "dispersion_percent": 0.0,
                "spread_percent": 0.0,
                "directional_consensus": "Single Model",
                "is_dependable_consensus": False,
                "bullish_count": 1 if any(v > 0 for v in valid_models.values()) else 0,
                "bearish_count": 1 if any(v < 0 for v in valid_models.values()) else 0,
                "neutral_count": 0,
                "total_models": len(valid_models),
                "outliers": [],
                "explanation": "Insufficient candidate models evaluated to measure ensemble disagreement.",
            }

        returns = np.array(list(valid_models.values()), dtype=float)
        ret_pcts = (np.exp(returns) - 1.0) * 100.0

        min_ret = float(np.min(ret_pcts))
        max_ret = float(np.max(ret_pcts))
        spread_pct = round(max_ret - min_ret, 2)
        mean_ret = float(np.mean(ret_pcts))
        median_ret = float(np.median(ret_pcts))
        dispersion_std = float(np.std(ret_pcts, ddof=1)) if len(ret_pcts) > 1 else 0.0

        # Benchmark against horizon volatility
        # Typical daily volatility is ~1.5% - 2.0%
        expected_h_vol_pct = (realized_volatility * 100.0) if (realized_volatility and realized_volatility > 0) else (1.5 * np.sqrt(horizon))
        dispersion_ratio = dispersion_std / max(0.5, expected_h_vol_pct)

        # Classify disagreement regime
        if dispersion_ratio < 0.45 and spread_pct < (expected_h_vol_pct * 1.2):
            regime = "LOW_DISAGREEMENT"
            regime_label = "Strong Model Consensus"
            regime_color = "emerald"
            reliability_tag = "High Agreement"
        elif dispersion_ratio < 1.1 and spread_pct < (expected_h_vol_pct * 2.5):
            regime = "MODERATE_DISAGREEMENT"
            regime_label = "Moderate Divergence"
            regime_color = "amber"
            reliability_tag = "Normal Uncertainty"
        else:
            regime = "HIGH_DISAGREEMENT"
            regime_label = "Wide Disagreement (High Uncertainty)"
            regime_color = "rose"
            reliability_tag = "Elevated Uncertainty"

        # Directional vote (> +0.3% return is bullish, < -0.3% is bearish)
        threshold_pct = 0.3 * np.sqrt(horizon / 5.0)
        bullish = [k for k, v in valid_models.items() if (np.exp(v) - 1.0) * 100.0 > threshold_pct]
        bearish = [k for k, v in valid_models.items() if (np.exp(v) - 1.0) * 100.0 < -threshold_pct]
        neutral = [k for k, v in valid_models.items() if abs((np.exp(v) - 1.0) * 100.0) <= threshold_pct]

        n_total = len(valid_models)
        b_count = len(bullish)
        bear_count = len(bearish)
        neut_count = len(neutral)

        if b_count >= n_total * 0.65:
            consensus_label = f"Strong Bullish Consensus ({b_count}/{n_total} Models)"
        elif b_count > bear_count and b_count >= n_total * 0.5:
            consensus_label = f"Moderate Bullish Tilt ({b_count}/{n_total} Models)"
        elif bear_count >= n_total * 0.65:
            consensus_label = f"Strong Bearish Consensus ({bear_count}/{n_total} Models)"
        elif bear_count > b_count and bear_count >= n_total * 0.5:
            consensus_label = f"Moderate Bearish Tilt ({bear_count}/{n_total} Models)"
        elif neut_count >= n_total * 0.5:
            consensus_label = f"Neutral / Range-Bound Consensus ({neut_count}/{n_total} Models)"
        else:
            consensus_label = f"Conflicted Direction ({b_count} Bullish vs {bear_count} Bearish)"

        # Outlier detection using Median Absolute Deviation (MAD)
        q75, q25 = np.percentile(ret_pcts, [75, 25])
        iqr = q75 - q25
        mad = float(np.median(np.abs(ret_pcts - median_ret))) or (dispersion_std * 0.6745)

        outliers = []
        for k, v in valid_models.items():
            r_pct = (np.exp(v) - 1.0) * 100.0
            dev = abs(r_pct - median_ret)
            is_outlier = False
            if mad > 0.05 and dev > max(2.5 * mad, 1.5 * iqr, 2.0):
                is_outlier = True
            elif dispersion_std > 0 and abs(r_pct - mean_ret) > (2.2 * dispersion_std):
                is_outlier = True

            if is_outlier:
                outliers.append({
                    "model_id": k,
                    "model_name": names.get(k, k),
                    "predicted_return_percent": round(r_pct, 2),
                    "deviation_from_median_percent": round(r_pct - median_ret, 2),
                    "direction": "higher" if r_pct > median_ret else "lower",
                })

        # Consensus dependability rule:
        # Require >= 4 valid models, low or moderate disagreement, no 50/50 split
        is_dependable = (
            n_total >= 4 and
            regime != "HIGH_DISAGREEMENT" and
            not ("Conflicted" in consensus_label and regime == "MODERATE_DISAGREEMENT")
        )

        # Formulate grounded explanation
        explanation_parts = []
        explanation_parts.append(
            f"Across {n_total} candidate models for the {horizon}-session horizon, predictions range from "
            f"{min_ret:+.2f}% to {max_ret:+.2f}% (spread of {spread_pct:.2f}%). "
            f"Ensemble median return is {median_ret:+.2f}% with a directional vote of "
            f"{b_count} Bullish, {bear_count} Bearish, and {neut_count} Neutral."
        )

        if regime == "HIGH_DISAGREEMENT":
            explanation_parts.append(
                "NOTICE: Model disagreement is high relative to normal asset volatility. Linear trend models "
                "and non-linear tree/neural architectures project diverging paths. This forecast should be "
                "treated with elevated uncertainty rather than high confidence."
            )
        elif regime == "MODERATE_DISAGREEMENT":
            explanation_parts.append(
                "Model dispersion is within typical bounds for this horizon. Moderate divergence reflects differences "
                "in feature weighting between short-term momentum and longer-term moving average trend signals."
            )
        else:
            explanation_parts.append(
                "Models exhibit strong directional and numerical agreement, clustering tightly around the empirical baseline."
            )

        if outliers:
            outlier_names = ", ".join(f"{o['model_name']} ({o['predicted_return_percent']:+.1f}%)" for o in outliers)
            explanation_parts.append(f"Statistical outlier detected: {outlier_names} diverged materially from the group median.")

        return {
            "regime": regime,
            "label": regime_label,
            "badge_color": regime_color,
            "reliability_tag": reliability_tag,
            "dispersion_percent": round(dispersion_std, 2),
            "spread_percent": spread_pct,
            "min_return_percent": round(min_ret, 2),
            "max_return_percent": round(max_ret, 2),
            "mean_return_percent": round(mean_ret, 2),
            "median_return_percent": round(median_ret, 2),
            "directional_consensus": consensus_label,
            "bullish_count": b_count,
            "bearish_count": bear_count,
            "neutral_count": neut_count,
            "total_models": n_total,
            "outliers": outliers,
            "is_dependable_consensus": is_dependable,
            "explanation": " ".join(explanation_parts),
        }
