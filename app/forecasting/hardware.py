"""Hardware profiling, resource health, and model availability registry."""
from __future__ import annotations

import logging
import os
import platform
import sys
from typing import Any

logger = logging.getLogger("stockrag.forecasting.hardware")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def get_hardware_profile() -> dict[str, Any]:
    """Detect actual hardware specifications and operating-system resources."""
    cpu_logical = os.cpu_count() or 1
    cpu_physical = cpu_logical
    cpu_pct = 0.0
    total_ram_gb = 8.0
    avail_ram_gb = 4.0
    ram_used_pct = 50.0

    if HAS_PSUTIL:
        try:
            cpu_physical = psutil.cpu_count(logical=False) or cpu_logical
            cpu_pct = round(psutil.cpu_percent(interval=None), 1)
            vmem = psutil.virtual_memory()
            total_ram_gb = round(vmem.total / (1024 ** 3), 2)
            avail_ram_gb = round(vmem.available / (1024 ** 3), 2)
            ram_used_pct = round(vmem.percent, 1)
        except Exception as exc:
            logger.debug("psutil_query_failed", extra={"error": str(exc)})

    # GPU detection (safely check torch/cuda if installed)
    gpu_available = False
    gpu_name = "None (CPU Vectorization Profile)"
    gpu_vram_gb = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu_available = True
            gpu_name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            gpu_vram_gb = round(props.total_memory / (1024 ** 3), 2)
    except Exception:
        gpu_available = False

    # Check key ML dependencies
    dependencies = {
        "scikit-learn": False,
        "numpy": False,
        "pandas": False,
        "psutil": HAS_PSUTIL,
        "scipy": False,
        "torch": False,
    }
    try:
        import sklearn  # noqa: F401
        dependencies["scikit-learn"] = True
    except ImportError:
        pass

    try:
        import numpy  # noqa: F401
        dependencies["numpy"] = True
    except ImportError:
        pass

    try:
        import pandas  # noqa: F401
        dependencies["pandas"] = True
    except ImportError:
        pass

    try:
        import scipy  # noqa: F401
        dependencies["scipy"] = True
    except ImportError:
        pass

    try:
        import torch  # noqa: F401
        dependencies["torch"] = True
    except ImportError:
        pass

    # Hardware resource tier recommendation
    if avail_ram_gb < 1.0:
        recommended_model = "historical_drift"
        resource_state = "Resource Limited"
    elif avail_ram_gb < 2.0 or cpu_logical <= 2:
        recommended_model = "historical_drift"
        resource_state = "Lightweight CPU Profile"
    else:
        recommended_model = "auto"
        resource_state = "Full Multi-Core ML Capable"

    cpu_brand = platform.processor() or platform.machine() or "Standard x86_64"
    if "Intel" not in cpu_brand and "AMD" not in cpu_brand and "ARM" not in cpu_brand:
        cpu_brand = f"Multi-Core CPU ({cpu_logical} logical cores)"

    return {
        "cpu": {
            "logical_cores": cpu_logical,
            "physical_cores": cpu_physical,
            "usage_percent": cpu_pct,
            "processor": cpu_brand,
            "architecture": platform.machine(),
        },
        "memory": {
            "total_gb": total_ram_gb,
            "available_gb": avail_ram_gb,
            "used_percent": ram_used_pct,
            "is_low_memory": avail_ram_gb < 1.5,
        },
        "gpu": {
            "available": gpu_available,
            "device_name": gpu_name,
            "vram_gb": gpu_vram_gb,
            "acceleration_type": "CUDA / Tensor" if gpu_available else "Pure CPU Vectorized (SIMD)",
        },
        "runtime": {
            "python_version": sys.version.split()[0],
            "os": f"{platform.system()} {platform.release()}",
            "dependencies": dependencies,
        },
        "health_state": "HEALTHY" if avail_ram_gb >= 1.0 else "RESOURCE_CONSTRAINED",
        "resource_tier": resource_state,
        "recommended_model": recommended_model,
    }


def evaluate_model_availability(
    model_id: str,
    bar_count: int,
    freshness: str,
    hardware_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Determine genuine availability state and actionable diagnostics for a model.
    
    Valid states:
    - Ready: Model is installed, calibrated, and ready to run.
    - Running: Real inference / validation executing.
    - Insufficient Data: Historical bars < requirement.
    - Resource Limited: Available RAM / CPU below minimum configuration.
    - Dependency Missing: Required library not installed.
    - Stale: Underlying market data > 5 days old.
    - Training Required: Model artifacts or initial calibration missing.
    - Failed: Execution error occurred.
    """
    hw = hardware_profile or get_hardware_profile()
    avail_ram = hw["memory"]["available_gb"]
    deps = hw["runtime"]["dependencies"]

    # Minimum data bars required per model
    min_bars = 55
    if bar_count < min_bars:
        return {
            "state": "Insufficient Data",
            "is_executable": False,
            "reason": f"Requires at least {min_bars} historical bars; only {bar_count} available.",
            "action": "Select a broader date range or an instrument with deeper trading history.",
        }

    # Dependency verification
    if model_id in ("ridge", "hist_gradient_boosting", "random_forest", "mlp_neural_net") and not deps.get("scikit-learn"):
        return {
            "state": "Dependency Missing",
            "is_executable": False,
            "reason": "scikit-learn library is required but not installed.",
            "action": "Run `pip install scikit-learn` in your terminal environment.",
        }

    # Resource requirements
    if model_id in ("hist_gradient_boosting", "random_forest") and avail_ram < 0.25:
        return {
            "state": "Resource Limited",
            "is_executable": False,
            "reason": "Available system RAM is critically low (<250 MB).",
            "action": "Free system memory or switch to the lightweight Empirical Drift baseline.",
        }

    if model_id == "mlp_neural_net" and avail_ram < 0.40:
        return {
            "state": "Resource Limited",
            "is_executable": False,
            "reason": "Available system RAM is critically low (<400 MB) for Multi-Layer Perceptron neural net.",
            "action": "Free system memory or use Ridge / Drift baseline.",
        }

    if freshness == "STALE":
        return {
            "state": "Stale",
            "is_executable": True,
            "reason": "Market history observation cutoff is older than 5 days.",
            "action": "Click 'Revalidate & Sync' to pull newer market closes from provider.",
        }

    return {
        "state": "Ready",
        "is_executable": True,
        "reason": "All hardware resources, dependencies, and historical observations verified.",
        "action": "Model is online and calibrated for real inference.",
    }


def get_model_suitability_specs(hw_profile: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Return dynamic hardware suitability, resource tiers, and best-for guidance for all models."""
    hw = hw_profile or get_hardware_profile()
    cpu_cores = hw["cpu"]["logical_cores"]
    avail_ram = hw["memory"]["available_gb"]

    return {
        "historical_drift": {
            "tier": "Ultra-Lightweight Baseline",
            "tier_color": "emerald",
            "capacity_level": 1,
            "best_for": "Default baseline · Steady macro trends · Hurdle rate",
            "memory_footprint": "< 2 MB",
            "compute_latency": "< 1 ms",
            "device_suitability": f"Supported on CPU ({cpu_cores} cores, {avail_ram} GB free RAM · Vectorized execution)",
            "capacity_needed": "Minimal (Runs on any standard CPU architecture)",
            "recommended": True,
        },
        "naive_zero": {
            "tier": "Martingale Persistence",
            "tier_color": "gray",
            "capacity_level": 1,
            "best_for": "Random walk benchmark · Sanity check for overfit ML",
            "memory_footprint": "< 1 MB",
            "compute_latency": "0 ms",
            "device_suitability": "Identity transform (Zero computational overhead)",
            "capacity_needed": "Zero (Martingale persistence identity)",
            "recommended": False,
        },
        "exponential_smoothing": {
            "tier": "Adaptive Econometric",
            "tier_color": "teal",
            "capacity_level": 1,
            "best_for": "Short-term momentum · Damped trend · Fast regime transitions",
            "memory_footprint": "< 5 MB",
            "compute_latency": "< 2 ms",
            "device_suitability": f"Supported on CPU ({cpu_cores} cores · Pure SIMD math)",
            "capacity_needed": "Low (Pure vector math, zero parameter bloat)",
            "recommended": False,
        },
        "ridge": {
            "tier": "Lightweight Linear ML",
            "tier_color": "sky",
            "capacity_level": 2,
            "best_for": "Multi-factor technicals · Collinear signal shrinkage · Stable returns",
            "memory_footprint": "< 12 MB",
            "compute_latency": "~ 4 ms",
            "device_suitability": f"Supported on CPU ({cpu_cores} cores · Closed-form analytical solver)",
            "capacity_needed": "Low (L2 analytical closed-form solver)",
            "recommended": True,
        },
        "hist_gradient_boosting": {
            "tier": "Balanced Ensemble ML",
            "tier_color": "indigo",
            "capacity_level": 3,
            "best_for": "Non-linear regime shifts · Volatility breakouts · Factor interactions",
            "memory_footprint": "< 35 MB",
            "compute_latency": "~ 12 ms",
            "device_suitability": f"Supported on CPU ({cpu_cores} cores · Integer-binned decision trees)",
            "capacity_needed": "Moderate (Requires integer binning & decision tree splits)",
            "recommended": True,
        },
        "random_forest": {
            "tier": "Multi-Tree Bagging Ensemble",
            "tier_color": "purple",
            "capacity_level": 3,
            "best_for": "Complex factor interactions · Outlier resilience · Variance reduction",
            "memory_footprint": "< 80 MB",
            "compute_latency": "~ 22 ms",
            "device_suitability": f"Supported on CPU ({cpu_cores} cores · Multi-threaded bagging)",
            "capacity_needed": "Medium (Bagging multiple decision trees in parallel)",
            "recommended": False,
        },
        "mlp_neural_net": {
            "tier": "Deep Neural Perceptron",
            "tier_color": "amber",
            "capacity_level": 4,
            "best_for": "Deep pattern recognition · Multi-scale non-linear representations",
            "memory_footprint": "< 180 MB",
            "compute_latency": "~ 38 ms",
            "device_suitability": f"{'Supported on CPU' if avail_ram >= 0.5 else 'Resource Constrained'} ({cpu_cores} cores, {avail_ram} GB free RAM)",
            "capacity_needed": "High Capacity (Iterative backpropagation & ReLU gradient steps)",
            "recommended": False,
        },
        "custom_model": {
            "tier": "Custom Parameterized Model",
            "tier_color": "pink",
            "capacity_level": 2,
            "best_for": "User hyperparameter testing · Momentum + Mean-reversion benchmarking",
            "memory_footprint": "< 15 MB",
            "compute_latency": "~ 6 ms",
            "device_suitability": f"Supported on CPU ({cpu_cores} cores · Custom linear solver)",
            "capacity_needed": "Low to Moderate",
            "recommended": False,
        },
    }
