"""High-level forecasting service integrating data, features, validation, explainability, and persistence."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from app.db.database import SessionLocal
from app.db.models import ForecastRecord
from app.forecasting.data_adapter import ForecastDataAdapter
from app.forecasting.feature_engineering import build_features_and_targets
from app.forecasting.hardware import evaluate_model_availability, get_hardware_profile, get_model_suitability_specs
from app.forecasting.models import (
    CustomQuantitativeForecaster,
    ExponentialSmoothingForecaster,
    HistoricalDriftForecaster,
    HistGradientBoostingReturnForecaster,
    MLPNeuralReturnForecaster,
    NaiveZeroForecaster,
    RandomForestReturnForecaster,
    RidgeReturnForecaster,
    convert_return_to_price,
)
from app.forecasting.uncertainty import UncertaintyEngine
from app.forecasting.validation import ChronologicalWalkForwardValidator

logger = logging.getLogger("stockrag.forecasting.service")

MODEL_METADATA: dict[str, dict[str, Any]] = {
    "historical_drift": {
        "id": "historical_drift",
        "name": "StockAI Empirical Drift Baseline",
        "short_name": "Empirical Drift",
        "category": "Historical Drift Statistical Baseline",
        "badge": "Recommended Default",
        "badge_color": "emerald",
        "is_default": True,
        "description": "Standard in-house statistical baseline projecting the rolling sample mean log-return of historical observations without parameter overfitting.",
        "methodology": "Sample mean expected drift over historical lookback window. Provides an honest empirical hurdle rate before deploying parameterized ML.",
        "formula": "E[r_{t+h}] = h * mu_drift = h * (1/T) sum_{t=1}^T r_t",
        "assumptions": "Past empirical drift persists as the expected trajectory in absence of regime shifts.",
        "strengths": "Zero hyperparameter overfitting, completely transparent, deterministic, instant computation (<1ms).",
        "weaknesses": "Cannot model non-linear price patterns, volatility clustering, or multi-factor cross-correlations.",
        "limitations": "Subject to historical lookback bias; cannot predict unexpected macroeconomic regime changes.",
        "hardware_profile": "Vectorized rolling window · <1ms inference · <2MB RAM footprint",
        "validation_protocol": "Chronological Walk-Forward Backtesting with 5-session embargo gap",
        "data_requirements": "Requires minimum 55 historical trading bars.",
        "supported_horizons": [1, 5, 20],
        "model_version": "2.4.0-stable",
    },
    "naive_zero": {
        "id": "naive_zero",
        "name": "StockAI Persistence Baseline (Zero-Return)",
        "short_name": "Zero-Return",
        "category": "Martingale Random Walk Baseline",
        "badge": "Random Walk",
        "badge_color": "gray",
        "is_default": False,
        "description": "Efficient-market martingale persistence baseline predicting zero excess forward return. The primary statistical hurdle rate for all ML forecasters.",
        "methodology": "Price persistence: expected future price equals current reference close price.",
        "formula": "E[r_{t+h}] = 0 ==> E[P_{t+h}] = P_t",
        "assumptions": "Market prices follow a martingale random walk where future price increments are unpredictable white noise.",
        "strengths": "Unbeatable in highly efficient regimes; zero risk of overfitting or parameter degradation.",
        "weaknesses": "Produces a horizontal forecast line with no directional sensitivity.",
        "limitations": "Ignores all momentum, trend, sentiment, and fundamental valuation drivers.",
        "hardware_profile": "Zero-computation identity · 0ms latency · 0MB overhead",
        "validation_protocol": "Chronological Walk-Forward Backtesting (Standard benchmark hurdle)",
        "data_requirements": "Requires at least 1 historical close price.",
        "supported_horizons": [1, 5, 20],
        "model_version": "2.4.0-stable",
    },
    "ridge": {
        "id": "ridge",
        "name": "StockAI Regularized Ridge-L2",
        "short_name": "Ridge L2",
        "category": "Penalized Linear Multi-Factor",
        "badge": "L2 Regularized",
        "badge_color": "sky",
        "is_default": False,
        "description": "Tikhonov L2-penalized multi-factor regression with strictly out-of-sample standard scaling and outlier clipping.",
        "methodology": "Linear multi-factor model mapping technical, momentum, volatility, and point-in-time sentiment signals to forward log-returns.",
        "formula": "w* = argmin_w ( ||y - Xw||_2^2 + alpha ||w||_2^2 )",
        "assumptions": "Linear additive relationship between standardized factors and forward returns, with Gaussian noise.",
        "strengths": "Shrinkage penalty prevents variance explosion from collinear indicators (RSI, Moving Averages, MACD).",
        "weaknesses": "Cannot natively capture non-linear factor interactions or asymmetric tail risk.",
        "limitations": "Coefficients represent average linear sensitivity and can dilute during sudden volatility spikes.",
        "hardware_profile": "Analytical closed-form CPU solver · <5ms inference · <10MB RAM footprint",
        "validation_protocol": "Chronological Walk-Forward Backtesting with 5-session embargo gap (Zero lookahead leakage)",
        "data_requirements": "Requires minimum 55 historical trading bars.",
        "supported_horizons": [1, 5, 20],
        "model_version": "2.4.0-stable",
    },
    "hist_gradient_boosting": {
        "id": "hist_gradient_boosting",
        "name": "StockAI Ensemble Gradient Forest (HistGBM)",
        "short_name": "HistGBM Forest",
        "category": "Non-linear Boosting Ensemble",
        "badge": "Ensemble ML",
        "badge_color": "indigo",
        "is_default": False,
        "description": "Histogram-binned gradient decision tree ensemble with L2 shrinkage and early stopping for non-linear market feature interactions.",
        "methodology": "Iterative residual boosting over 256 integer-binned feature splits with strict depth constraints (depth <= 3).",
        "formula": "F_M(x) = sum_{m=1}^M gamma_m h_m(x) with leaf shrinkage & early stopping",
        "assumptions": "Complex non-linear interactions between volatility regime, trend momentum, and news tone carry predictive signal.",
        "strengths": "Detects regime shifts and feature interactions without requiring manual polynomial feature expansion.",
        "weaknesses": "Higher variance than linear regression; requires careful regularization to avoid noise memorization.",
        "limitations": "Tree models do not extrapolate beyond historical minimum and maximum return envelopes.",
        "hardware_profile": "Vectorized CPU integer binning · ~12ms inference · <35MB RAM footprint",
        "validation_protocol": "Chronological Walk-Forward Backtesting with 5-session embargo gap (Zero lookahead leakage)",
        "data_requirements": "Requires minimum 55 historical trading bars.",
        "supported_horizons": [1, 5, 20],
        "model_version": "2.4.0-stable",
    },
    "custom_model": {
        "id": "custom_model",
        "name": "StockAI Custom Quantitative Model",
        "short_name": "Custom Model",
        "category": "User-Configured Multi-Factor",
        "badge": "User Configured",
        "badge_color": "purple",
        "is_default": False,
        "description": "User-parameterized quantitative model allowing custom regularizer alpha, momentum lookback, and mean-reversion weights.",
        "methodology": "Custom factor weighting with live chronological walk-forward benchmark evaluation against baselines.",
        "formula": "y_pred = X_custom * w(alpha, momentum, mean_reversion)",
        "assumptions": "User-supplied parameterization accurately reflects asset-specific market dynamics.",
        "strengths": "Allows quantitative hypothesis testing and custom strategy backtesting with zero lookahead bias.",
        "weaknesses": "Performance depends heavily on chosen parameter values and market regime.",
        "limitations": "Subject to user configuration risk; must be validated against empirical baseline.",
        "hardware_profile": "Vectorized CPU solver · <8ms inference · <15MB RAM footprint",
        "validation_protocol": "Chronological Walk-Forward Backtesting against Persistence & Drift baselines",
        "data_requirements": "Requires minimum 55 historical trading bars.",
        "supported_horizons": [1, 5, 20],
        "model_version": "1.0.0-user",
    },
    "random_forest": {
        "id": "random_forest",
        "name": "StockAI Multi-Factor Random Forest",
        "short_name": "Random Forest",
        "category": "Multi-Tree Bagging Ensemble",
        "badge": "Tree Bagging",
        "badge_color": "purple",
        "is_default": False,
        "description": "Ensemble of 45 randomized decision trees with bootstrap aggregation, variance reduction, and non-linear factor interactions.",
        "methodology": "Bootstrap aggregation over randomized feature subsets to capture high-order indicator non-linearities without overfitting single outliers.",
        "formula": "F_B(x) = (1/B) * sum_{b=1}^B T_b(x; Theta_b) with max_depth=5",
        "assumptions": "Averaging decorrelated decision trees reduces forecast variance and insulates against extreme single-bar price anomalies.",
        "strengths": "Exceptional stability; naturally handles collinear momentum and volatility interactions without scaling distortion.",
        "weaknesses": "Slower inference than Ridge; cannot extrapolate outside historical return boundaries.",
        "limitations": "Requires multi-core CPU for optimal parallelized execution; memory scales with tree count.",
        "hardware_profile": "Multi-Core CPU Parallelized · ~22ms latency · ~80MB RAM footprint",
        "validation_protocol": "Chronological Walk-Forward Backtesting with 5-session embargo gap",
        "data_requirements": "Requires minimum 55 historical trading bars.",
        "supported_horizons": [1, 5, 20],
        "model_version": "2.4.0-stable",
    },
    "mlp_neural_net": {
        "id": "mlp_neural_net",
        "name": "StockAI Deep Neural Perceptron (MLP)",
        "short_name": "Neural Perceptron",
        "category": "Deep Multi-Layer Perceptron",
        "badge": "Deep Neural Net",
        "badge_color": "amber",
        "is_default": False,
        "description": "High-capacity deep feedforward neural network with multi-layer non-linear transformations (32, 16 neurons), ReLU activations, and Adam gradient descent.",
        "methodology": "Supervised multi-layer forward propagation with early stopping, backpropagation, and L2 regularization to discover complex multi-scale patterns.",
        "formula": "z^{(l)} = W^{(l)} a^{(l-1)} + b^{(l)}; a^{(l)} = ReLU(z^{(l)}); y = W^{(out)} a^{(L)} + b^{(out)}",
        "assumptions": "Deep non-linear compositions of technical and momentum factors provide superior representation capacity for subtle regime transitions.",
        "strengths": "Highest capacity to model complex cross-factor interactions and multi-timeframe non-linear patterns.",
        "weaknesses": "Most compute-intensive model; susceptible to noisy financial signal overfit if training iterations are unconstrained.",
        "limitations": "Requires at least 2 CPU cores and >400MB available RAM; early stopping actively enforced.",
        "hardware_profile": "High Capacity CPU Neural · ~38ms latency · ~180MB RAM footprint",
        "validation_protocol": "Chronological Walk-Forward Backtesting with 5-session embargo gap",
        "data_requirements": "Requires minimum 65 historical trading bars.",
        "supported_horizons": [1, 5, 20],
        "model_version": "2.4.0-stable",
    },
    "exponential_smoothing": {
        "id": "exponential_smoothing",
        "name": "StockAI Holt-Winters Exponential Smoothing",
        "short_name": "Holt-Winters",
        "category": "Adaptive Econometric Model",
        "badge": "Damped Trend",
        "badge_color": "teal",
        "is_default": False,
        "description": "Double exponential smoothing with trend dampening (phi=0.90) weighting recent market observations exponentially over distant historical noise.",
        "methodology": "Recursive level and trend updates with dampening factor preventing unrealistic drift compounding.",
        "formula": "l_t = alpha*y_t + (1-alpha)(l_{t-1} + phi*b_{t-1}); b_t = beta(l_t - l_{t-1}) + (1-beta)*phi*b_{t-1}",
        "assumptions": "Recent price momentum carries exponentially greater predictive information than distant historical observations.",
        "strengths": "Ultra-fast execution (<2ms); dynamic adaptation to trend inflection points without parameter bloat.",
        "weaknesses": "Univariate return series only; does not incorporate cross-sectional volume or news sentiment signals.",
        "limitations": "Can lag during sudden sharp V-shaped market reversals.",
        "hardware_profile": "Pure Vector SIMD · <2ms latency · <5MB RAM footprint",
        "validation_protocol": "Chronological Walk-Forward Backtesting with 5-session embargo gap",
        "data_requirements": "Requires minimum 30 historical trading bars.",
        "supported_horizons": [1, 5, 20],
        "model_version": "2.4.0-stable",
    },
}


class ForecastingService:
    """End-to-end forecasting service providing approximate, evidence-grounded forecasts."""

    def __init__(self, data_adapter: ForecastDataAdapter | None = None):
        self.data_adapter = data_adapter or ForecastDataAdapter()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_ttl_seconds = 180.0  # 3 minutes

    def forecast(
        self,
        symbol: str,
        horizon: int = 5,
        model_name: str = "historical_drift",
        confidence: float = 0.80,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Generate a validated probabilistic forecast with explicit uncertainty."""
        horizon = int(horizon) if int(horizon) in (1, 5, 20) else 5
        confidence = float(confidence) if confidence in (0.80, 0.90, 0.95) else 0.80
        model_name = (model_name or "historical_drift").casefold()
        start_time = time.perf_counter()

        cache_key = f"{symbol.upper()}:{horizon}:{model_name}:{confidence}"
        now_ts = datetime.now(timezone.utc).timestamp()
        if not refresh and cache_key in self._cache:
            ts, cached_res = self._cache[cache_key]
            if now_ts - ts < self._cache_ttl_seconds:
                cached_res_copy = dict(cached_res)
                cached_res_copy["is_cached"] = True
                cached_res_copy["cached_at"] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                return cached_res_copy

        # 1. Fetch & normalize market data
        period = "2y" if horizon <= 5 else "5y"
        data_res = self.data_adapter.fetch_normalized_market_data(
            symbol, period=period, interval="1d", refresh=refresh
        )
        if not data_res.get("success"):
            return {
                "success": False,
                "status": data_res.get("status", "insufficient_data"),
                "symbol": symbol,
                "error": data_res.get("error", "Failed to retrieve market history"),
                "abstain": True,
            }

        df: pd.DataFrame = data_res["data"]
        metadata: dict[str, Any] = data_res["metadata"]
        current_price = float(df["Close"].iloc[-1])
        last_date = df["Date"].iloc[-1]
        last_date_str = str(last_date)[:10]

        # 2. Gather recent news
        news_items = self.data_adapter.fetch_related_news(symbol, limit=25)

        # 3. Build features & targets
        features_res = build_features_and_targets(df, news_items=news_items, horizons=[1, 5, 20])
        if not features_res.get("success"):
            return {
                "success": False,
                "status": "insufficient_data",
                "symbol": metadata["symbol"],
                "error": features_res.get("error", "Insufficient observations for features"),
                "abstain": True,
            }

        features_df: pd.DataFrame = features_res["features"]
        targets_dict: dict[int, pd.Series] = features_res["targets"]
        warmup_idx: int = features_res["warmup_idx"]
        feature_names: list[str] = features_res["feature_names"]

        # 4. Chronological Walk-Forward Backtesting
        X_all = features_df.to_numpy(dtype=float)
        y_target = targets_dict[horizon].to_numpy(dtype=float)

        # Slice after warmup
        X_eval = X_all[warmup_idx:]
        y_eval = y_target[warmup_idx:]
        dates_eval = df["Date"].iloc[warmup_idx:].tolist()

        validator = ChronologicalWalkForwardValidator(horizon=horizon, n_test_bars=30, min_train_bars=50)
        benchmark_results = validator.benchmark_models(X_eval, y_eval, dates_eval)

        # 5. Model Selection
        selected_model_key = model_name
        models_bench = benchmark_results.get("models", {})

        if model_name == "auto":
            hgb_mae = models_bench.get("hist_gradient_boosting", {}).get("mae", float("inf"))
            ridge_mae = models_bench.get("ridge", {}).get("mae", float("inf"))
            drift_mae = models_bench.get("historical_drift", {}).get("mae", float("inf"))
            naive_mae = models_bench.get("naive_zero", {}).get("mae", float("inf"))
            rf_mae = models_bench.get("random_forest", {}).get("mae", float("inf"))
            mlp_mae = models_bench.get("mlp_neural_net", {}).get("mae", float("inf"))
            exp_mae = models_bench.get("exponential_smoothing", {}).get("mae", float("inf"))

            candidates = [
                ("historical_drift", drift_mae),
                ("ridge", ridge_mae),
                ("hist_gradient_boosting", hgb_mae),
                ("random_forest", rf_mae),
                ("mlp_neural_net", mlp_mae),
                ("exponential_smoothing", exp_mae),
                ("naive_zero", naive_mae),
            ]
            valid_candidates = [c for c in candidates if np.isfinite(c[1]) and c[1] > 0]
            if valid_candidates:
                best_model, _ = min(valid_candidates, key=lambda item: item[1])
                selected_model_key = best_model
            else:
                selected_model_key = "historical_drift"

        # Model instance mapping
        def create_model(key: str):
            if key == "hist_gradient_boosting":
                return HistGradientBoostingReturnForecaster()
            elif key == "ridge":
                return RidgeReturnForecaster(alpha=10.0)
            elif key == "random_forest":
                return RandomForestReturnForecaster()
            elif key == "mlp_neural_net":
                return MLPNeuralReturnForecaster()
            elif key == "exponential_smoothing":
                return ExponentialSmoothingForecaster()
            elif key == "custom_model":
                return CustomQuantitativeForecaster()
            elif key == "naive_zero":
                return NaiveZeroForecaster()
            return HistoricalDriftForecaster()

        active_model = create_model(selected_model_key)
        val_metrics = models_bench.get(selected_model_key, {})

        # 6. Abstention Check
        abstention = UncertaintyEngine.evaluate_abstention(
            bar_count=len(df),
            horizon=horizon,
            freshness=metadata.get("freshness", "FRESH"),
            val_metrics=val_metrics,
            model_name=selected_model_key,
        )

        if abstention["should_abstain"]:
            return {
                "success": False,
                "status": abstention["status"],
                "symbol": metadata["symbol"],
                "error": abstention["reason"],
                "abstain": True,
                "metadata": metadata,
            }

        # 7. Fit active model on all labeled observations & Predict next horizon
        labeled_mask = np.isfinite(y_target) & np.isfinite(X_all).all(axis=1)
        X_train_final = X_all[labeled_mask]
        y_train_final = y_target[labeled_mask]

        active_model.fit(X_train_final, y_train_final)

        # Latest feature vector at forecast origin
        latest_X = X_all[-1:]
        predicted_return = float(active_model.predict(latest_X)[0])
        val_residuals = val_metrics.get("residuals", [])
        res_std = float(np.std(val_residuals)) if len(val_residuals) > 2 else 0.025
        directional_prob = float(active_model.predict_proba(latest_X, residual_std=res_std)[0])

        # 8. Calibrated Prediction Intervals
        residuals = val_metrics.get("residuals", np.array([]))
        interval_data = UncertaintyEngine.compute_conformal_interval(
            pred_return=predicted_return,
            current_price=current_price,
            residuals=residuals,
            confidence_level=confidence,
        )

        # 9. Signal drivers, exact cutoff values & feature explanations
        latest_row = features_df.iloc[-1]
        feature_labels = {
            "return_1d": "1-Day Prior Return",
            "return_2d": "2-Day Cumulative Return",
            "return_5d": "5-Day Cumulative Return",
            "return_10d": "10-Day Cumulative Return",
            "return_20d": "20-Day Cumulative Return",
            "volatility_5d": "5-Day Realized Volatility",
            "volatility_20d": "20-Day Realized Volatility",
            "dist_sma20": "Distance to 20-Day SMA",
            "dist_sma50": "Distance to 50-Day SMA",
            "rsi14": "14-Day Relative Strength Index (RSI)",
            "macd_line": "MACD Normalized Line",
            "macd_diff": "MACD Histogram Divergence",
            "atr14_pct": "14-Day ATR (% of Price)",
            "intraday_range": "Intraday High-Low Range",
            "gap": "Overnight Opening Gap",
            "volume_ratio": "Volume vs 20-Day Mean",
            "vol_regime": "Volatility Regime Ratio (5D/20D)",
            "news_sentiment": "Point-in-Time News Sentiment",
            "news_count": "Recent Financial News Volume",
        }

        raw_importances = active_model.get_feature_importances(feature_names)
        enriched_signals = []
        if raw_importances:
            for item in raw_importances:
                name = item["feature"]
                val = float(latest_row.get(name, 0.0))
                enriched_signals.append({
                    "feature": name,
                    "label": feature_labels.get(name, name.replace("_", " ").title()),
                    "value": round(val, 4),
                    "importance": item.get("importance", round(abs(val), 4)),
                    "direction": item.get("direction", "positive" if val >= 0 else "negative"),
                })
        else:
            for name in feature_names:
                val = float(latest_row.get(name, 0.0))
                enriched_signals.append({
                    "feature": name,
                    "label": feature_labels.get(name, name.replace("_", " ").title()),
                    "value": round(val, 4),
                    "importance": round(abs(val), 4),
                    "direction": "positive" if val >= 0 else "negative",
                })
            enriched_signals.sort(key=lambda s: s["importance"], reverse=True)

        # 10. Projections & Multi-Model Trajectories
        step_dates = []
        curr_dt = pd.to_datetime(last_date)
        while len(step_dates) < horizon:
            curr_dt += pd.Timedelta(days=1)
            if curr_dt.weekday() < 5:  # Mon-Fri
                step_dates.append(curr_dt.strftime("%Y-%m-%d"))

        projected_date_str = step_dates[-1] if step_dates else str(last_date + pd.Timedelta(days=int(horizon * 1.45 + 1)))[:10]
        expected_price = interval_data["expected_price"]
        lower_price = interval_data["lower_bound_price"]
        upper_price = interval_data["upper_bound_price"]

        q_lower_ret = interval_data.get("lower_bound_return", predicted_return - 0.03)
        q_upper_ret = interval_data.get("upper_bound_return", predicted_return + 0.03)

        projection_path = [
            {
                "date": last_date_str,
                "price": current_price,
                "lower": current_price,
                "upper": current_price,
                "step": 0,
            }
        ]
        for step_idx, step_date in enumerate(step_dates, start=1):
            fraction = step_idx / horizon
            cone_scale = np.sqrt(fraction)
            step_return = predicted_return * fraction
            step_price = round(float(current_price * np.exp(step_return)), 4)
            step_lower = round(float(current_price * np.exp(step_return + (q_lower_ret - predicted_return) * cone_scale)), 4)
            step_upper = round(float(current_price * np.exp(step_return + (q_upper_ret - predicted_return) * cone_scale)), 4)
            projection_path.append({
                "date": step_date,
                "price": step_price,
                "lower": step_lower,
                "upper": step_upper,
                "step": step_idx,
            })

        # Multi-model forward projection trajectories for interactive chart toggling
        multi_model_projections: dict[str, Any] = {
            "selected": {
                "id": selected_model_key,
                "name": MODEL_METADATA.get(selected_model_key, {}).get("name", selected_model_key),
                "target_price": expected_price,
                "return_pct": interval_data["expected_return_percent"],
                "path": projection_path,
            }
        }

        candidate_instances = {
            "historical_drift": HistoricalDriftForecaster(),
            "naive_zero": NaiveZeroForecaster(),
            "exponential_smoothing": ExponentialSmoothingForecaster(),
            "ridge": RidgeReturnForecaster(alpha=10.0),
            "hist_gradient_boosting": HistGradientBoostingReturnForecaster(),
            "random_forest": RandomForestReturnForecaster(),
            "mlp_neural_net": MLPNeuralReturnForecaster(),
        }
        for cand_key, cand_model in candidate_instances.items():
            try:
                cand_model.fit(X_train_final, y_train_final)
                cand_pred = float(cand_model.predict(latest_X)[0])
                c_target = round(float(current_price * np.exp(cand_pred)), 4)
                c_ret_pct = round(((c_target - current_price) / current_price) * 100.0, 2)
                c_path = [{"date": last_date_str, "price": current_price, "step": 0}]
                for s_idx, s_dt in enumerate(step_dates, start=1):
                    frac = s_idx / horizon
                    c_path.append({
                        "date": s_dt,
                        "price": round(float(current_price * np.exp(cand_pred * frac)), 4),
                        "step": s_idx,
                    })
                multi_model_projections[cand_key] = {
                    "id": cand_key,
                    "name": MODEL_METADATA.get(cand_key, {}).get("name", cand_key),
                    "short_name": MODEL_METADATA.get(cand_key, {}).get("short_name", cand_key),
                    "target_price": c_target,
                    "return_pct": c_ret_pct,
                    "path": c_path,
                }
            except Exception:
                pass

        # 3rd-party analyst consensus & deterministic pivot baseline
        third_party_data = self.data_adapter.fetch_third_party_targets(
            metadata["symbol"],
            ohlcv_df=df,
            current_price=current_price,
        )

        analyst_t = third_party_data.get("analyst_consensus", {})
        if analyst_t.get("available") and analyst_t.get("target_price"):
            t_price = float(analyst_t["target_price"])
            a_path = [{"date": last_date_str, "price": current_price, "step": 0}]
            for s_idx, s_dt in enumerate(step_dates, start=1):
                frac = s_idx / horizon
                a_path.append({
                    "date": s_dt,
                    "price": round(current_price + (t_price - current_price) * frac, 4),
                    "step": s_idx,
                })
            multi_model_projections["analyst_consensus"] = {
                "id": "analyst_consensus",
                "name": "Wall Street Analyst Consensus",
                "short_name": "Analyst Target",
                "target_price": t_price,
                "return_pct": analyst_t.get("implied_return_percent", 0.0),
                "path": a_path,
                "source": "Yahoo Finance (Free Public Tier)",
            }

        pivot_t = third_party_data.get("algorithmic_pivot", {})
        if pivot_t.get("available") and pivot_t.get("target_price"):
            p_price = float(pivot_t["target_price"])
            p_path = [{"date": last_date_str, "price": current_price, "step": 0}]
            for s_idx, s_dt in enumerate(step_dates, start=1):
                frac = s_idx / horizon
                p_path.append({
                    "date": s_dt,
                    "price": round(current_price + (p_price - current_price) * frac, 4),
                    "step": s_idx,
                })
            multi_model_projections["algorithmic_pivot"] = {
                "id": "algorithmic_pivot",
                "name": "Classical Pivot & Fibonacci Projection",
                "short_name": "Pivot Baseline",
                "target_price": p_price,
                "return_pct": pivot_t.get("implied_return_percent", 0.0),
                "path": p_path,
                "source": "Open Quantitative Specification",
            }

        chart_payload = {
            "origin": {
                "date": last_date_str,
                "price": current_price,
            },
            "horizon_sessions": horizon,
            "target_date": projected_date_str,
            "expected_price": expected_price,
            "lower_price": lower_price,
            "upper_price": upper_price,
            "projection_path": projection_path,
            "model_projections": multi_model_projections,
        }

        # 11. Factor Categories Allocation
        factor_allocations = {
            "Technical Momentum": 0.0,
            "Volatility & Risk": 0.0,
            "Volume & Gap": 0.0,
            "News & Sentiment": 0.0,
        }
        for item in enriched_signals:
            feat = item["feature"]
            imp = item["importance"]
            if feat in ("return_1d", "return_2d", "return_5d", "return_10d", "return_20d", "macd_line", "macd_diff", "dist_sma20", "dist_sma50"):
                factor_allocations["Technical Momentum"] += imp
            elif feat in ("volatility_5d", "volatility_20d", "atr14_pct", "intraday_range", "vol_regime"):
                factor_allocations["Volatility & Risk"] += imp
            elif feat in ("gap", "volume_ratio"):
                factor_allocations["Volume & Gap"] += imp
            else:
                factor_allocations["News & Sentiment"] += imp

        tot_imp = sum(factor_allocations.values()) or 1.0
        pie_factors = [
            {"name": k, "percentage": round((v / tot_imp) * 100.0, 1), "weight": round(v, 4)}
            for k, v in factor_allocations.items()
        ]

        # 12. Past Walk-Forward Evaluation History
        eval_dates = val_metrics.get("eval_dates", [])
        m_preds = val_metrics.get("predictions", [])
        m_actuals = val_metrics.get("actuals", [])
        m_resids = val_metrics.get("residuals", [])
        backtest_history = []
        n_eval = len(eval_dates)
        start_eval_idx = max(0, n_eval - 10)
        for i in range(start_eval_idx, n_eval):
            p = float(m_preds[i]) if i < len(m_preds) else 0.0
            a = float(m_actuals[i]) if i < len(m_actuals) else 0.0
            r = float(m_resids[i]) if i < len(m_resids) else 0.0
            dt = eval_dates[i]
            hit = (p * a > 0) or (abs(p) < 0.003 and abs(a) < 0.005)
            backtest_history.append({
                "date": dt,
                "predicted_return_pct": round(p * 100.0, 2),
                "actual_return_pct": round(a * 100.0, 2),
                "residual_error_pct": round(abs(r) * 100.0, 2),
                "hit": bool(hit),
                "direction": "UP" if a >= 0 else "DOWN",
            })

        # 13. System Hardware & Engine Health
        hw_profile = get_hardware_profile()
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 1)

        # Evaluate availability status for each model in registry
        model_availability_catalog = {}
        for m_id, m_meta in MODEL_METADATA.items():
            avail = evaluate_model_availability(m_id, len(df), metadata.get("freshness", "FRESH"), hw_profile)
            model_availability_catalog[m_id] = {
                **m_meta,
                "availability": avail,
            }

        active_availability = model_availability_catalog.get(selected_model_key, {}).get("availability", {})

        system_health = {
            "status": hw_profile.get("health_state", "HEALTHY"),
            "latency_ms": latency_ms,
            "hardware": hw_profile,
            "model_availability": active_availability.get("state", "Ready"),
            "model_availability_reason": active_availability.get("reason", "Model verified."),
            "data_freshness": metadata.get("freshness", "FRESH"),
            "data_source": metadata.get("source", "market_service"),
            "observation_timestamp": metadata.get("observation_timestamp"),
            "retrieved_at": metadata.get("retrieved_at"),
            "revalidation_strategy": "Auto-revalidated upon bar or parameter refresh",
        }

        # 14. Database Persistence and Realized Error Evaluation
        persisted_records = self._sync_and_persist_forecast_records(
            symbol=metadata["symbol"],
            horizon=horizon,
            model_name=selected_model_key,
            current_price=current_price,
            last_date_str=last_date_str,
            target_date_str=projected_date_str,
            expected_price=expected_price,
            expected_return_pct=interval_data["expected_return_percent"],
            lower_price=lower_price,
            upper_price=upper_price,
            confidence=confidence,
            directional_prob=directional_prob,
            val_metrics=val_metrics,
            df_history=df,
        )

        # 15. Structured LLM / Explainability Payload
        llm_payload = {
            "symbol": metadata["symbol"],
            "current_price": current_price,
            "currency": metadata.get("currency", "USD"),
            "as_of_date": last_date_str,
            "horizon_sessions": horizon,
            "projected_target_date": projected_date_str,
            "selected_model": selected_model_key,
            "model_name": MODEL_METADATA.get(selected_model_key, {}).get("name", selected_model_key),
            "expected_return_percent": interval_data["expected_return_percent"],
            "expected_price": expected_price,
            "confidence_level_percent": interval_data["confidence_percent"],
            "lower_bound_price": lower_price,
            "upper_bound_price": upper_price,
            "directional_probability_bullish_percent": round(directional_prob * 100.0, 1),
            "walk_forward_metrics": {
                "sample_size": val_metrics.get("test_sample_size", 0),
                "mae_percent": val_metrics.get("mae_percent", 0.0),
                "rmse_percent": val_metrics.get("rmse_percent", 0.0),
                "directional_accuracy_percent": val_metrics.get("directional_accuracy_percent", 50.0),
                "beats_naive_baseline": val_metrics.get("beats_naive_baseline", False),
                "improvement_vs_naive_percent": val_metrics.get("improvement_vs_naive_percent", 0.0),
            },
            "top_signals": enriched_signals[:6],
            "third_party_summary": {
                "analyst_consensus": third_party_data.get("analyst_consensus", {}),
                "algorithmic_pivot": third_party_data.get("algorithmic_pivot", {}),
            },
            "recent_news_evidence": [
                {
                    "title": item.get("title"),
                    "publisher": item.get("publisher"),
                    "published_at": item.get("published_at"),
                }
                for item in news_items[:3]
            ],
            "limitations_and_disclaimer": (
                "FORECAST DISCLAIMER: This is a probabilistic, empirical estimate generated by a "
                "lightweight mathematical model. Stock returns are inherently noisy and uncertain. "
                "This output does not constitute investment advice, a recommendation to buy or sell, "
                "or a guarantee of future performance."
            ),
        }

        result = {
            "success": True,
            "status": "success",
            "abstain": False,
            "is_cached": False,
            "symbol": metadata["symbol"],
            "horizon": horizon,
            "selected_model": selected_model_key,
            "model_name": MODEL_METADATA.get(selected_model_key, {}).get("name", selected_model_key),
            "model_metadata": model_availability_catalog,
            "current_price": current_price,
            "currency": metadata.get("currency", "USD"),
            "last_bar_at": last_date_str,
            "retrieved_at": metadata.get("retrieved_at"),
            "data_source": metadata.get("source"),
            "freshness": metadata.get("freshness"),
            "interval": interval_data,
            "directional_probability": round(directional_prob, 4),
            "directional_label": "BULLISH" if directional_prob > 0.52 else ("BEARISH" if directional_prob < 0.48 else "NEUTRAL"),
            "chart_data": chart_payload,
            "validation": val_metrics,
            "benchmark_comparison": benchmark_results,
            "signals": enriched_signals[:8],
            "factor_breakdown": pie_factors,
            "backtest_history": backtest_history,
            "realized_outcomes": persisted_records,
            "third_party_forecasts": third_party_data,
            "system_health": system_health,
            "llm_payload": llm_payload,
            "suitability_specs": get_model_suitability_specs(hw_profile),
            "disclaimer": llm_payload["limitations_and_disclaimer"],
        }

        self._cache[cache_key] = (now_ts, result)
        return result

    def _sync_and_persist_forecast_records(
        self,
        symbol: str,
        horizon: int,
        model_name: str,
        current_price: float,
        last_date_str: str,
        target_date_str: str,
        expected_price: float,
        expected_return_pct: float,
        lower_price: float,
        upper_price: float,
        confidence: float,
        directional_prob: float,
        val_metrics: dict[str, Any],
        df_history: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """Persist current forecast and evaluate realized outcomes of older pending forecasts."""
        realized_list = []
        try:
            with SessionLocal() as db:
                # 1. Check pending forecasts for this symbol that have now reached their target date
                date_price_map = {}
                if not df_history.empty and "Date" in df_history.columns and "Close" in df_history.columns:
                    for _, row in df_history.iterrows():
                        d_str = str(row["Date"])[:10]
                        date_price_map[d_str] = float(row["Close"])

                pending = (
                    db.query(ForecastRecord)
                    .filter(
                        ForecastRecord.symbol == symbol,
                        ForecastRecord.status == "pending",
                        ForecastRecord.target_date <= last_date_str,
                    )
                    .all()
                )

                for rec in pending:
                    # Find actual price on or immediately after target date
                    actual_p = date_price_map.get(rec.target_date)
                    if actual_p is None:
                        # Find closest available date in history
                        matching_dates = [d for d in date_price_map.keys() if d >= rec.target_date]
                        if matching_dates:
                            actual_p = date_price_map[min(matching_dates)]

                    if actual_p and actual_p > 0:
                        rec.realized_price = actual_p
                        rec.realized_error = round(actual_p - rec.expected_price, 4)
                        rec.realized_error_percent = round(((actual_p - rec.expected_price) / rec.reference_price) * 100.0, 2)
                        rec.status = "evaluated"

                # 2. Check if identical forecast record was already logged today
                existing = (
                    db.query(ForecastRecord)
                    .filter(
                        ForecastRecord.symbol == symbol,
                        ForecastRecord.horizon == horizon,
                        ForecastRecord.model_name == model_name,
                        ForecastRecord.reference_date == last_date_str,
                    )
                    .first()
                )

                if not existing:
                    new_rec = ForecastRecord(
                        symbol=symbol,
                        horizon=horizon,
                        model_name=model_name,
                        reference_price=current_price,
                        reference_date=last_date_str,
                        target_date=target_date_str,
                        expected_price=expected_price,
                        expected_return_percent=expected_return_pct,
                        lower_bound_price=lower_price,
                        upper_bound_price=upper_price,
                        confidence_percent=int(confidence * 100),
                        directional_prob=round(directional_prob, 4),
                        directional_label="BULLISH" if directional_prob > 0.52 else ("BEARISH" if directional_prob < 0.48 else "NEUTRAL"),
                        val_mae_percent=val_metrics.get("mae_percent"),
                        val_rmse_percent=val_metrics.get("rmse_percent"),
                        val_sample_size=val_metrics.get("test_sample_size"),
                        status="pending",
                        metadata_json={"created_at_utc": datetime.now(timezone.utc).isoformat()},
                    )
                    db.add(new_rec)

                db.commit()

                # 3. Retrieve past evaluated records for transparency
                evaluated_records = (
                    db.query(ForecastRecord)
                    .filter(ForecastRecord.symbol == symbol, ForecastRecord.status == "evaluated")
                    .order_by(ForecastRecord.target_date.desc())
                    .limit(8)
                    .all()
                )

                for r in evaluated_records:
                    hit = bool((r.expected_return_percent * (r.realized_price - r.reference_price) > 0) or abs(r.realized_error_percent or 0) < 1.0)
                    realized_list.append({
                        "id": r.id,
                        "model_name": MODEL_METADATA.get(r.model_name, {}).get("short_name", r.model_name),
                        "horizon": r.horizon,
                        "reference_date": r.reference_date,
                        "target_date": r.target_date,
                        "reference_price": r.reference_price,
                        "expected_price": r.expected_price,
                        "realized_price": r.realized_price,
                        "realized_error_percent": r.realized_error_percent,
                        "directional_hit": hit,
                    })
        except Exception as exc:
            logger.debug("forecast_record_persistence_failed", extra={"symbol": symbol, "error": str(exc)})

        return realized_list

    def evaluate_custom_model(
        self,
        symbol: str,
        horizon: int = 5,
        momentum_weight: float = 0.5,
        mean_reversion_weight: float = 0.2,
        l2_penalty: float = 8.0,
    ) -> dict[str, Any]:
        """Perform verified walk-forward evaluation on user-configured custom model."""
        horizon = int(horizon) if int(horizon) in (1, 5, 20) else 5
        data_res = self.data_adapter.fetch_normalized_market_data(symbol, period="2y", interval="1d")
        if not data_res.get("success"):
            return {"success": False, "error": data_res.get("error", "Failed to retrieve history")}

        df: pd.DataFrame = data_res["data"]
        features_res = build_features_and_targets(df, horizons=[horizon])
        if not features_res.get("success"):
            return {"success": False, "error": features_res.get("error", "Insufficient bars")}

        features_df: pd.DataFrame = features_res["features"]
        targets_dict: dict[int, pd.Series] = features_res["targets"]
        warmup_idx: int = features_res["warmup_idx"]

        X_all = features_df.to_numpy(dtype=float)
        y_target = targets_dict[horizon].to_numpy(dtype=float)

        X_eval = X_all[warmup_idx:]
        y_eval = y_target[warmup_idx:]
        dates_eval = df["Date"].iloc[warmup_idx:].tolist()

        validator = ChronologicalWalkForwardValidator(horizon=horizon, n_test_bars=30, min_train_bars=50)

        # Baseline evaluation
        baseline_res = validator.evaluate_model(lambda: HistoricalDriftForecaster(), X_eval, y_eval, dates_eval)
        naive_res = validator.evaluate_model(lambda: NaiveZeroForecaster(), X_eval, y_eval, dates_eval)

        # Custom model evaluation
        custom_res = validator.evaluate_model(
            lambda: CustomQuantitativeForecaster(
                momentum_weight=momentum_weight,
                mean_reversion_weight=mean_reversion_weight,
                l2_penalty=l2_penalty,
            ),
            X_eval,
            y_eval,
            dates_eval,
        )

        b_mae = baseline_res.get("mae", float("inf"))
        c_mae = custom_res.get("mae", float("inf"))
        edge = ((b_mae - c_mae) / b_mae) * 100.0 if np.isfinite(b_mae) and b_mae > 0 else 0.0

        return {
            "success": True,
            "symbol": symbol,
            "horizon": horizon,
            "parameters": {
                "momentum_weight": momentum_weight,
                "mean_reversion_weight": mean_reversion_weight,
                "l2_penalty": l2_penalty,
            },
            "custom_metrics": custom_res,
            "drift_baseline_metrics": baseline_res,
            "naive_baseline_metrics": naive_res,
            "edge_vs_baseline_percent": round(edge, 2),
            "beats_baseline": c_mae < b_mae,
        }

    def clear_cache(self) -> int:
        """Clear the in-memory forecast cache."""
        count = len(self._cache)
        self._cache.clear()
        return count
