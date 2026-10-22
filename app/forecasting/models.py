"""CPU-efficient forecasting models: Naive baseline, Drift, Ridge, and HistGradientBoosting."""
from __future__ import annotations

import abc
import logging
import math
from typing import Any

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier, RandomForestRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("stockrag.forecasting.models")


class BaseForecaster(abc.ABC):
    """Abstract base class for horizon-specific return forecasters."""

    def __init__(self, name: str):
        self.name = name
        self.is_fitted = False

    @abc.abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> "BaseForecaster":
        pass

    @abc.abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict forward log-returns."""
        pass

    def predict_proba(self, X: np.ndarray, residual_std: float | None = None) -> np.ndarray:
        """Return a model-implied directional score, not a calibrated probability.
        
        Uses standard normal CDF on z-score = pred / max(residual_std, 0.015),
        bounded conservatively within [0.15, 0.85] to reflect financial market uncertainty.
        """
        preds = self.predict(X)
        scale = max(float(residual_std), 0.015) if residual_std is not None and np.isfinite(residual_std) else 0.025
        # z-score standard normal CDF approximation via error function
        import math
        z = preds / scale
        probs = np.array([
            0.5 * (1.0 + math.erf(float(val) / math.sqrt(2.0)))
            for val in z
        ], dtype=float)
        # Bounded within 15% to 85% to prevent overconfident fabrication
        return np.clip(probs, 0.15, 0.85)

    def get_feature_importances(self, feature_names: list[str]) -> list[dict[str, Any]]:
        return []


class NaiveZeroForecaster(BaseForecaster):
    """Baseline predicting zero forward return (random walk martingale persistence)."""

    def __init__(self):
        super().__init__("naive_zero")

    def fit(self, X: np.ndarray, y: np.ndarray) -> "NaiveZeroForecaster":
        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.zeros(len(X), dtype=float)

    def predict_proba(self, X: np.ndarray, residual_std: float | None = None) -> np.ndarray:
        return np.full(len(X), 0.5, dtype=float)


class HistoricalDriftForecaster(BaseForecaster):
    """Baseline predicting the historical mean return of the training window."""

    def __init__(self):
        super().__init__("historical_drift")
        self.mean_return_ = 0.0
        self.positive_ratio_ = 0.5

    def fit(self, X: np.ndarray, y: np.ndarray) -> "HistoricalDriftForecaster":
        valid = y[np.isfinite(y)]
        self.mean_return_ = float(np.mean(valid)) if len(valid) > 0 else 0.0
        self.positive_ratio_ = float(np.mean(valid > 0)) if len(valid) > 0 else 0.5
        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.full(len(X), self.mean_return_, dtype=float)

    def predict_proba(self, X: np.ndarray, residual_std: float | None = None) -> np.ndarray:
        return np.full(len(X), np.clip(self.positive_ratio_, 0.25, 0.75), dtype=float)


class RidgeReturnForecaster(BaseForecaster):
    """L2-regularized Ridge regression with standard scaler fitted strictly on train data."""

    def __init__(self, alpha: float = 12.0):
        super().__init__("ridge_regression")
        self.alpha = alpha
        self.scaler = StandardScaler()
        self.model = Ridge(alpha=self.alpha, fit_intercept=True)
        self.coefficients_: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RidgeReturnForecaster":
        valid_mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
        x_clean = X[valid_mask]
        y_clean = y[valid_mask]

        if len(x_clean) < 10:
            self.coefficients_ = np.zeros(X.shape[1])
            self.is_fitted = True
            return self

        # Clip extreme outliers to 4 standard deviations to prevent leverage point distortion
        x_scaled = self.scaler.fit_transform(x_clean)
        x_clipped = np.clip(x_scaled, -4.0, 4.0)
        self.model.fit(x_clipped, y_clean)
        self.coefficients_ = self.model.coef_
        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Model is not fitted.")
        x_clean = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        x_scaled = self.scaler.transform(x_clean)
        x_clipped = np.clip(x_scaled, -4.0, 4.0)
        return self.model.predict(x_clipped)

    def get_feature_importances(self, feature_names: list[str]) -> list[dict[str, Any]]:
        if self.coefficients_ is None:
            return []
        importances = []
        for name, coef in zip(feature_names, self.coefficients_):
            importances.append({
                "feature": name,
                "importance": round(float(abs(coef)), 5),
                "coefficient": round(float(coef), 5),
                "direction": "positive" if coef > 0 else "negative",
            })
        return sorted(importances, key=lambda item: item["importance"], reverse=True)


class HistGradientBoostingReturnForecaster(BaseForecaster):
    """Fast, low-memory Histogram Gradient Boosting Regressor optimized for CPU."""

    def __init__(
        self,
        max_iter: int = 50,
        max_depth: int = 3,
        min_samples_leaf: int = 8,
        learning_rate: float = 0.04,
        l2_regularization: float = 2.5,
        random_state: int = 42,
    ):
        super().__init__("hist_gradient_boosting")
        self.max_iter = max_iter
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.learning_rate = learning_rate
        self.l2_regularization = l2_regularization
        self.random_state = random_state
        self.model = HistGradientBoostingRegressor(
            max_iter=self.max_iter,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            learning_rate=self.learning_rate,
            l2_regularization=self.l2_regularization,
            early_stopping=True,
            n_iter_no_change=5,
            random_state=self.random_state,
        )

    def fit(self, X: np.ndarray, y: np.ndarray) -> "HistGradientBoostingReturnForecaster":
        valid_mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
        x_clean = X[valid_mask]
        y_clean = y[valid_mask]

        if len(x_clean) < self.min_samples_leaf * 2:
            self.is_fitted = False
            return self

        self.model.fit(x_clean, y_clean)
        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.zeros(len(X), dtype=float)
        x_clean = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        return self.model.predict(x_clean)


class CustomQuantitativeForecaster(BaseForecaster):
    """User-configurable quantitative forecaster supporting custom parameterization & walk-forward testing."""

    def __init__(
        self,
        name: str = "custom_model",
        momentum_weight: float = 0.5,
        mean_reversion_weight: float = 0.2,
        l2_penalty: float = 8.0,
    ):
        super().__init__(name)
        self.momentum_weight = momentum_weight
        self.mean_reversion_weight = mean_reversion_weight
        self.l2_penalty = l2_penalty
        self.scaler = StandardScaler()
        self.ridge = Ridge(alpha=max(0.1, l2_penalty), fit_intercept=True)
        self.weights_: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "CustomQuantitativeForecaster":
        valid = np.isfinite(X).all(axis=1) & np.isfinite(y)
        x_clean = X[valid]
        y_clean = y[valid]
        if len(x_clean) < 10:
            self.weights_ = np.zeros(X.shape[1])
            self.is_fitted = True
            return self

        x_scaled = self.scaler.fit_transform(x_clean)
        self.ridge.fit(x_scaled, y_clean)
        self.weights_ = self.ridge.coef_
        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.zeros(len(X), dtype=float)
        x_clean = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        x_scaled = self.scaler.transform(x_clean)
        return self.ridge.predict(x_scaled)


class RandomForestReturnForecaster(BaseForecaster):
    """Multi-factor Random Forest ensemble with bagging and variance reduction."""

    def __init__(
        self,
        n_estimators: int = 15,
        max_depth: int = 4,
        min_samples_leaf: int = 5,
        random_state: int = 42,
    ):
        super().__init__("random_forest")
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state
        self.model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            random_state=self.random_state,
            n_jobs=1,
        )

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RandomForestReturnForecaster":
        valid_mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
        x_clean = X[valid_mask]
        y_clean = y[valid_mask]

        if len(x_clean) < self.min_samples_leaf * 2:
            self.is_fitted = False
            return self

        self.model.fit(x_clean, y_clean)
        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.zeros(len(X), dtype=float)
        x_clean = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        return self.model.predict(x_clean)


class MLPNeuralReturnForecaster(BaseForecaster):
    """Multi-Layer Perceptron Neural Network for high-capacity non-linear pattern representation."""

    def __init__(
        self,
        hidden_layer_sizes: tuple[int, ...] = (16, 8),
        alpha: float = 2.0,
        max_iter: int = 160,
        random_state: int = 42,
    ):
        super().__init__("mlp_neural_net")
        self.hidden_layer_sizes = hidden_layer_sizes
        self.alpha = alpha
        self.max_iter = max_iter
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.model = MLPRegressor(
            hidden_layer_sizes=self.hidden_layer_sizes,
            activation="relu",
            solver="adam",
            alpha=self.alpha,
            learning_rate_init=0.015,
            max_iter=self.max_iter,
            early_stopping=True,
            n_iter_no_change=5,
            tol=1e-3,
            random_state=self.random_state,
        )

    def fit(self, X: np.ndarray, y: np.ndarray) -> "MLPNeuralReturnForecaster":
        import warnings
        from sklearn.exceptions import ConvergenceWarning

        valid_mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
        x_clean = X[valid_mask]
        y_clean = y[valid_mask]

        if len(x_clean) < 20:
            self.is_fitted = False
            return self

        x_scaled = self.scaler.fit_transform(x_clean)
        x_clipped = np.clip(x_scaled, -3.0, 3.0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=ConvergenceWarning)
            self.model.fit(x_clipped, y_clean)
        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.zeros(len(X), dtype=float)
        x_clean = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        x_scaled = self.scaler.transform(x_clean)
        x_clipped = np.clip(x_scaled, -3.0, 3.0)
        raw_pred = self.model.predict(x_clipped)
        return np.clip(raw_pred, -0.15, 0.15)


class ExponentialSmoothingForecaster(BaseForecaster):
    """Classical econometric exponential smoothing for return series with mean reversion damping."""

    def __init__(self, alpha: float = 0.15, beta: float = 0.02, phi: float = 0.50):
        super().__init__("exponential_smoothing")
        self.alpha = alpha
        self.beta = beta
        self.phi = phi
        self.level_ = 0.0
        self.trend_ = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "ExponentialSmoothingForecaster":
        valid = y[np.isfinite(y)]
        if len(valid) < 5:
            self.level_ = 0.0
            self.trend_ = 0.0
            self.is_fitted = True
            return self

        level = float(np.mean(valid[:5]))
        trend = 0.0

        for val in valid[1:]:
            val_f = float(val)
            prev_level = level
            level = self.alpha * val_f + (1.0 - self.alpha) * (level + self.phi * trend)
            trend = self.beta * (level - prev_level) + (1.0 - self.beta) * self.phi * trend
            trend = float(np.clip(trend, -0.01, 0.01))

        self.level_ = float(level)
        self.trend_ = float(trend)
        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        pred_val = float(np.clip(self.level_ + (self.phi * self.trend_), -0.10, 0.10))
        return np.full(len(X), pred_val, dtype=float)


def convert_return_to_price(current_price: float, return_pred: float) -> float:
    """Transform log-return forecast into expected future nominal price."""
    if current_price <= 0:
        return 0.0
    return round(float(current_price * np.exp(return_pred)), 4)

