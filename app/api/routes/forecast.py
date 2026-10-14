"""API endpoints for probabilistic stock forecasting, system health, and walk-forward backtesting."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.forecasting.hardware import get_hardware_profile
from app.forecasting.service import ForecastingService
from app.market.symbol_resolver import resolve_symbol

router = APIRouter(prefix="/forecast", tags=["Forecasting"])
forecast_service = ForecastingService()


class CustomModelRequest(BaseModel):
    symbol: str = Field(..., description="Stock ticker symbol to evaluate")
    horizon: int = Field(5, description="Forecast horizon in sessions (1, 5, or 20)")
    momentum_weight: float = Field(0.5, ge=0.0, le=2.0, description="Weight for momentum returns")
    mean_reversion_weight: float = Field(0.2, ge=0.0, le=2.0, description="Weight for distance to SMA")
    alpha: float = Field(8.0, ge=0.1, le=100.0, description="L2 shrinkage penalty alpha")
    l2_penalty: float | None = Field(None, description="Optional alias for alpha")

    @property
    def effective_alpha(self) -> float:
        return self.l2_penalty if self.l2_penalty is not None else self.alpha


def _resolve_or_400(symbol: str) -> str:
    res = resolve_symbol(symbol)
    if not res["valid"]:
        raise HTTPException(status_code=400, detail=f"Invalid stock symbol format: '{symbol}'")
    return res["resolved_symbol"]


@router.get("/system/health")
async def get_system_health() -> dict[str, Any]:
    """Return genuine, dynamic hardware specifications, system memory, and service status."""
    hw = await asyncio.to_thread(get_hardware_profile)
    from app.forecasting.service import MODEL_METADATA
    return {
        "success": True,
        "hardware": hw,
        "model_registry": MODEL_METADATA,
        "services": {
            "market_data_api": "Operational (yfinance / Market Service)",
            "news_feed_api": "Operational (Google News / RSS Feeds)",
            "analyst_consensus_api": "Operational (Yahoo Public Feed)",
            "database_persistence": "Operational (SQLite / ForecastRecord)",
        },
    }


@router.post("/system/revalidate")
async def revalidate_system() -> dict[str, Any]:
    """Force revalidation, purge stale forecast cache, and refresh hardware diagnostics."""
    cleared = forecast_service.clear_cache()
    hw = await asyncio.to_thread(get_hardware_profile)
    return {
        "success": True,
        "message": f"Successfully cleared {cleared} cached forecast entries and revalidated diagnostics.",
        "hardware": hw,
    }


@router.get("/featured/summary")
async def get_featured_forecasts(
    horizon: int = Query(5, description="Forecast horizon in trading sessions (1, 5, or 20)"),
) -> dict[str, Any]:
    """Provide curated ML forecast summaries for prominent US and Indian tickers for the landing showcase."""
    if horizon not in (1, 5, 20):
        horizon = 5

    featured_symbols = [
        {"symbol": "AAPL", "name": "Apple Inc.", "market": "us"},
        {"symbol": "NVDA", "name": "NVIDIA Corporation", "market": "us"},
        {"symbol": "MSFT", "name": "Microsoft Corporation", "market": "us"},
        {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "market": "india"},
        {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "market": "india"},
        {"symbol": "INFY.NS", "name": "Infosys", "market": "india"},
    ]

    async def fetch_one(item: dict[str, str]):
        sym = item["symbol"]
        try:
            fc = await asyncio.to_thread(
                forecast_service.forecast,
                sym,
                horizon=horizon,
                model_name="historical_drift",
                confidence=0.80,
                refresh=False,
            )
            if fc.get("success"):
                intv = fc.get("interval", {})
                chart_data = fc.get("chart_data", {})
                path = chart_data.get("projection_path", [])
                sparkline_points = [p.get("price") for p in path if p.get("price") is not None]
                return {
                    "symbol": sym,
                    "name": item["name"],
                    "market": item["market"],
                    "currency": fc.get("currency", "USD"),
                    "current_price": fc.get("current_price"),
                    "expected_price": intv.get("expected_price"),
                    "expected_return_percent": intv.get("expected_return_percent"),
                    "directional_probability": fc.get("directional_probability"),
                    "directional_label": fc.get("directional_label"),
                    "selected_model": fc.get("selected_model"),
                    "horizon": horizon,
                    "lower_bound_price": intv.get("lower_bound_price"),
                    "upper_bound_price": intv.get("upper_bound_price"),
                    "confidence_percent": intv.get("confidence_percent", 80),
                    "last_bar_at": fc.get("last_bar_at"),
                    "sparkline_points": sparkline_points,
                    "freshness": fc.get("freshness", "FRESH"),
                }
        except Exception:
            pass
        return None

    results = await asyncio.gather(*(fetch_one(item) for item in featured_symbols))
    summaries = [r for r in results if r is not None]

    return {
        "success": True,
        "horizon": horizon,
        "items": summaries,
    }


@router.get("/models/catalog")
async def get_model_catalog() -> dict[str, Any]:
    """Return comprehensive metadata, formulas, hardware profiles, and descriptions for all forecasting models."""
    from app.forecasting.service import MODEL_METADATA
    hw = await asyncio.to_thread(get_hardware_profile)
    return {
        "success": True,
        "models": MODEL_METADATA,
        "hardware": hw,
    }


@router.post("/custom/evaluate")
async def evaluate_custom_model_endpoint(req: CustomModelRequest) -> dict[str, Any]:
    """Execute a chronological walk-forward evaluation on a user-parameterized custom quantitative model."""
    resolved_symbol = _resolve_or_400(req.symbol)
    if req.horizon not in (1, 5, 20):
        req.horizon = 5

    res = await asyncio.to_thread(
        forecast_service.evaluate_custom_model,
        symbol=resolved_symbol,
        horizon=req.horizon,
        momentum_weight=req.momentum_weight,
        mean_reversion_weight=req.mean_reversion_weight,
        l2_penalty=req.effective_alpha,
    )
    if not res.get("success"):
        raise HTTPException(status_code=422, detail=res.get("error", "Custom model evaluation failed"))
    return res


@router.get("/{symbol}")
async def get_stock_forecast(
    symbol: str,
    horizon: int = Query(5, description="Forecast horizon in trading sessions (1, 5, or 20)"),
    model: str = Query("auto", pattern="^(auto|ridge|hist_gradient_boosting|random_forest|mlp_neural_net|exponential_smoothing|historical_drift|naive_zero|custom_model)$"),
    confidence: float = Query(0.80, description="Nominal confidence interval level (0.80, 0.90, or 0.95)"),
    refresh: bool = Query(False, description="Bypass cache and pull fresh data"),
) -> dict[str, Any]:
    """Generate an evidence-grounded, probabilistic stock forecast with calibrated prediction intervals."""
    resolved_symbol = _resolve_or_400(symbol)
    if horizon not in (1, 5, 20):
        raise HTTPException(status_code=400, detail="Horizon must be 1, 5, or 20 trading sessions.")
    if confidence not in (0.80, 0.90, 0.95):
        confidence = 0.80

    try:
        result = await asyncio.to_thread(
            forecast_service.forecast,
            resolved_symbol,
            horizon=horizon,
            model_name=model,
            confidence=confidence,
            refresh=refresh,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Forecasting engine error: {exc}")

    if not result.get("success"):
        status = result.get("status", "insufficient_data")
        status_code = 422 if status in ("insufficient_data", "unreliable_model", "data_quality_failure") else 503
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": result.get("error", "Forecast could not be generated"),
                "status": status,
                "symbol": resolved_symbol,
                "abstain": True,
            },
        )

    return result


@router.get("/{symbol}/backtest")
async def get_forecast_backtest(
    symbol: str,
    horizon: int = Query(5, description="Backtest horizon in trading sessions (1, 5, or 20)"),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    """Retrieve full chronological walk-forward benchmark comparing ML against Naive baselines."""
    resolved_symbol = _resolve_or_400(symbol)
    if horizon not in (1, 5, 20):
        raise HTTPException(status_code=400, detail="Horizon must be 1, 5, or 20 trading sessions.")

    result = await asyncio.to_thread(
        forecast_service.forecast,
        resolved_symbol,
        horizon=horizon,
        model_name="auto",
        refresh=refresh,
    )

    if not result.get("success"):
        raise HTTPException(status_code=422, detail=result.get("error", "Backtest unavailable for symbol"))

    return {
        "symbol": resolved_symbol,
        "horizon": horizon,
        "benchmarks": result.get("benchmark_comparison"),
        "validation_selected_model": result.get("selected_model"),
        "last_bar_at": result.get("last_bar_at"),
    }
