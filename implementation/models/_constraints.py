"""Shared validation and convex constraints for portfolio model adapters."""

from __future__ import annotations

import numpy as np
import cvxpy as cp
import pandas as pd


def common_weight_constraints(
    weights: cp.Variable,
    assets: list[str],
    config: dict[str, object],
    expected_annual_returns: np.ndarray,
) -> list[cp.Constraint]:
    """Build constraints shared by MVO and historical-CVaR models.

    ``max_holdings`` is intentionally not handled here: cardinality is a
    mixed-integer constraint and belongs to Yesh's AMPL/HiGHS presentation
    backend. The local CVXPY adapters cover the continuous constraints that
    can be compared consistently across MVO and CVaR.
    """
    n_assets = len(assets)
    if n_assets == 0:
        raise ValueError("at least one asset is required")
    max_weight = float(config.get("max_weight", 1.0))
    if not 0 < max_weight <= 1:
        raise ValueError("max_weight must be in (0, 1]")
    if n_assets * max_weight < 1.0 - 1e-9:
        raise ValueError("max_weight is infeasible for this asset count")
    constraints: list[cp.Constraint] = [
        cp.sum(weights) == 1,
        weights >= 0,
        weights <= max_weight,
    ]

    excluded = set(config.get("exclude", []))
    for asset in excluded.intersection(assets):
        constraints.append(weights[assets.index(asset)] == 0)

    target = config.get("target_annual_return")
    if target is not None:
        target = float(target)
        constraints.append(expected_annual_returns @ weights >= target)

    turnover = config.get("max_turnover")
    if turnover is not None:
        turnover = float(turnover)
        if turnover < 0:
            raise ValueError("max_turnover must be non-negative")
        current = config.get("current_weights")
        if current is None:
            current_series = pd.Series(1.0 / n_assets, index=assets)
        elif isinstance(current, pd.Series):
            current_series = current.astype(float).reindex(assets)
        else:
            current_series = pd.Series(current, dtype=float).reindex(assets)
        if current_series.isna().any() or not np.isfinite(current_series.to_numpy()).all():
            raise ValueError("current_weights must contain one finite value per asset")
        if (current_series < -1e-10).any() or current_series.sum() <= 0:
            raise ValueError("current_weights must be non-negative with positive total")
        current_values = current_series.to_numpy(dtype=float)
        current_values = current_values / current_values.sum()
        constraints.append(cp.norm1(weights - current_values) <= turnover)

    cash_asset = config.get("cash_asset")
    cash_min = config.get("cash_min")
    if cash_asset is not None and cash_min is not None:
        if cash_asset not in assets:
            raise ValueError(f"cash_asset is not in the asset universe: {cash_asset}")
        cash_min = float(cash_min)
        if not 0 <= cash_min <= 1:
            raise ValueError("cash_min must be between 0 and 1")
        constraints.append(weights[assets.index(cash_asset)] >= cash_min)

    sector_caps = config.get("sector_caps")
    asset_sectors = config.get("asset_sectors")
    if sector_caps is not None:
        if not isinstance(asset_sectors, dict):
            raise ValueError("asset_sectors is required when sector_caps is supplied")
        for sector, cap in dict(sector_caps).items():
            cap = float(cap)
            if not 0 <= cap <= 1:
                raise ValueError("sector caps must be between 0 and 1")
            indices = [i for i, asset in enumerate(assets) if asset_sectors.get(asset) == sector]
            if indices:
                constraints.append(cp.sum(weights[indices]) <= cap)
    return constraints


def project_simplex(values: np.ndarray) -> np.ndarray:
    """Project a vector onto nonnegative weights that sum to one."""

    values = np.asarray(values, dtype=float).reshape(-1)
    if values.size == 0:
        raise ValueError("at least one asset is required")
    sorted_values = np.sort(values)[::-1]
    cumulative = np.cumsum(sorted_values)
    candidates = sorted_values - (cumulative - 1.0) / np.arange(1, len(values) + 1)
    valid = np.flatnonzero(candidates > 0)
    rho = int(valid[-1]) if len(valid) else 0
    threshold = (cumulative[rho] - 1.0) / (rho + 1)
    return np.maximum(values - threshold, 0.0)


def project_bounded_simplex(values: np.ndarray, max_weight: float) -> np.ndarray:
    """Project onto sum=1, 0<=w<=max_weight via bisection."""

    values = np.asarray(values, dtype=float).reshape(-1)
    if not 0 < max_weight <= 1:
        raise ValueError("max_weight must be in (0, 1]")
    if len(values) * max_weight < 1.0 - 1e-10:
        raise ValueError("max_weight is infeasible for this asset count")
    low = float(np.min(values) - max_weight)
    high = float(np.max(values))
    for _ in range(80):
        threshold = (low + high) / 2
        candidate = np.clip(values - threshold, 0.0, max_weight)
        if candidate.sum() > 1.0:
            low = threshold
        else:
            high = threshold
    result = np.clip(values - high, 0.0, max_weight)
    # Correct tiny floating-point residual without violating bounds materially.
    residual = 1.0 - result.sum()
    if abs(residual) > 1e-8:
        room = max_weight - result
        if residual > 0:
            result += residual * room / room.sum()
        else:
            room = result
            result += residual * room / room.sum()
    return result
