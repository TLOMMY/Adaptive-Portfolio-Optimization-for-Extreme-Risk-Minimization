"""Robust minimum-variance portfolio adapter.

Portable integration of Jia Qi's Robust Mean Variance formulation. It keeps
Bowen's ``fit_model(train_returns, profile_config)`` contract while replacing a
single covariance estimate with a finite set of rolling covariance scenarios.
"""

from __future__ import annotations

from typing import Mapping, Optional

import cvxpy as cp
import numpy as np
import pandas as pd

from ._constraints import common_weight_constraints


def _covariance_scenarios(
    returns: pd.DataFrame, periods: float, config: Mapping[str, object]
) -> list[np.ndarray]:
    """Build annualised PSD covariance scenarios from past-only observations."""
    n_obs = len(returns)
    requested_length = int(config.get("scenario_window", 252))
    window = min(requested_length, n_obs)
    if window < 2:
        raise ValueError("scenario_window must provide at least two observations")
    requested_count = int(config.get("scenario_count", 5))
    if requested_count < 1:
        raise ValueError("scenario_count must be positive")
    stride = int(config.get("scenario_stride", 126))
    if stride < 1:
        raise ValueError("scenario_stride must be positive")

    starts = [i * stride for i in range(requested_count)]
    if starts[-1] + window > n_obs:
        max_start = n_obs - window
        if max_start < 0:
            raise ValueError("not enough observations for covariance scenarios")
        if requested_count == 1:
            starts = [0]
        else:
            starts = [round(i * max_start / (requested_count - 1)) for i in range(requested_count)]
    if len(set(starts)) != len(starts):
        raise ValueError(
            "scenario_count is too large for the available observations; "
            "reduce scenario_count or scenario_window"
        )

    blocks = [returns.iloc[start : start + window] for start in starts]
    if bool(config.get("include_full_scenario", True)):
        blocks.append(returns)

    scenarios: list[np.ndarray] = []
    for block in blocks:
        matrix = block.cov().to_numpy(dtype=float) * periods
        matrix = (matrix + matrix.T) / 2.0
        eigenvalues, eigenvectors = np.linalg.eigh(matrix)
        repaired = eigenvectors @ np.diag(np.maximum(eigenvalues, 1e-10)) @ eigenvectors.T
        scenarios.append((repaired + repaired.T) / 2.0)
    return scenarios


def fit_robust_mvo(
    train_returns: pd.DataFrame,
    profile_config: Optional[Mapping[str, object]] = None,
) -> pd.Series:
    """Minimise worst-case annualised variance over covariance scenarios."""
    if train_returns.empty:
        raise ValueError("train_returns must not be empty")
    config = dict(profile_config or {})
    clean = train_returns.astype(float).dropna(how="any")
    if len(clean) < 2:
        raise ValueError("at least two training observations are required")
    periods = float(config.get("periods_per_year", 252))
    mean = clean.mean().to_numpy(dtype=float) * periods
    scenarios = _covariance_scenarios(clean, periods, config)

    weights = cp.Variable(len(clean.columns))
    worst_case_variance = cp.Variable()
    constraints = common_weight_constraints(weights, list(clean.columns), config, mean)
    for covariance in scenarios:
        constraints.append(cp.quad_form(weights, cp.psd_wrap(covariance)) <= worst_case_variance)
    problem = cp.Problem(cp.Minimize(worst_case_variance), constraints)
    try:
        problem.solve(solver="CLARABEL")
    except cp.error.SolverError:
        problem.solve(solver="SCS", eps=1e-6, max_iters=100_000)
    if problem.status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE} or weights.value is None:
        raise RuntimeError(
            f"Robust MVO optimization is infeasible or failed: status={problem.status}"
        )
    values = np.asarray(weights.value, dtype=float).reshape(-1)
    if not np.isfinite(values).all():
        raise RuntimeError("Robust MVO solver returned non-finite weights")
    return pd.Series(values, index=clean.columns, name="weight")
