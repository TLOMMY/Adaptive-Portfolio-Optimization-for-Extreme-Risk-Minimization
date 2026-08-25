"""Constrained mean-variance portfolio model adapter."""

from __future__ import annotations

from typing import Mapping, Optional

import cvxpy as cp
import numpy as np
import pandas as pd

from ._constraints import common_weight_constraints


def fit_mvo(
    train_returns: pd.DataFrame,
    profile_config: Optional[Mapping[str, object]] = None,
) -> pd.Series:
    """Fit a long-only Markowitz portfolio using training returns only.

    The objective is annualized mean return minus ``risk_aversion`` times
    annualized variance. Target return and turnover are hard constraints when
    present in ``profile_config``; infeasible configurations raise a clear
    ``RuntimeError`` instead of silently relaxing the investor requirements.
    """
    if train_returns.empty:
        raise ValueError("train_returns must not be empty")
    config = dict(profile_config or {})
    clean = train_returns.astype(float).dropna(how="any")
    if len(clean) < 2:
        raise ValueError("at least two training observations are required")
    periods = float(config.get("periods_per_year", 252))
    risk_aversion = float(config.get("risk_aversion", 5.0))
    if risk_aversion < 0:
        raise ValueError("risk_aversion must be non-negative")
    mean = clean.mean().to_numpy(dtype=float) * periods
    covariance = clean.cov().to_numpy(dtype=float) * periods
    covariance = (covariance + covariance.T) / 2.0 + np.eye(len(mean)) * 1e-10

    weights = cp.Variable(len(mean))
    objective = cp.Maximize(mean @ weights - risk_aversion * cp.quad_form(weights, cp.psd_wrap(covariance)))
    constraints = common_weight_constraints(weights, list(clean.columns), config, mean)
    problem = cp.Problem(objective, constraints)
    try:
        problem.solve(solver="CLARABEL")
    except cp.error.SolverError:
        problem.solve(solver="SCS", eps=1e-6, max_iters=100_000)
    if problem.status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE} or weights.value is None:
        raise RuntimeError(f"MVO optimization is infeasible or failed: status={problem.status}")
    values = np.asarray(weights.value, dtype=float).reshape(-1)
    if not np.isfinite(values).all():
        raise RuntimeError("MVO solver returned non-finite weights")
    return pd.Series(values, index=clean.columns, name="weight")
