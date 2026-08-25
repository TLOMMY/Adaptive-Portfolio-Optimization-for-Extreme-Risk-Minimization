"""Historical CVaR portfolio model adapter using a linear program."""

from __future__ import annotations

from typing import Mapping, Optional

import cvxpy as cp
import numpy as np
import pandas as pd

from ._constraints import common_weight_constraints


def fit_cvar(
    train_returns: pd.DataFrame,
    profile_config: Optional[Mapping[str, object]] = None,
) -> pd.Series:
    """Fit a long-only historical-CVaR portfolio on training scenarios.

    ``confidence_level=0.95`` means the average loss in the worst five
    percent of observed scenarios. Optional target return, turnover, CVaR
    limit, cash, sector, and exclusion constraints are hard constraints.
    """
    if train_returns.empty:
        raise ValueError("train_returns must not be empty")
    config = dict(profile_config or {})
    clean = train_returns.astype(float).dropna(how="any")
    if len(clean) < 2:
        raise ValueError("at least two training observations are required")
    confidence = float(config.get("confidence_level", 0.95))
    if not 0 < confidence < 1:
        raise ValueError("confidence_level must be between 0 and 1")
    periods = float(config.get("periods_per_year", 252))
    scenarios = clean.to_numpy(dtype=float)
    n_scenarios, n_assets = scenarios.shape
    weights = cp.Variable(n_assets)
    var_threshold = cp.Variable()
    excess_losses = cp.Variable(n_scenarios, nonneg=True)
    losses = -scenarios @ weights
    cvar = var_threshold + cp.sum(excess_losses) / ((1.0 - confidence) * n_scenarios)
    mean = clean.mean().to_numpy(dtype=float) * periods
    constraints = common_weight_constraints(weights, list(clean.columns), config, mean)
    constraints.append(excess_losses >= losses - var_threshold)
    cvar_limit = config.get("cvar_limit")
    if cvar_limit is not None:
        cvar_limit = float(cvar_limit)
        if cvar_limit < 0:
            raise ValueError("cvar_limit must be non-negative")
        constraints.append(cvar <= cvar_limit)
    problem = cp.Problem(cp.Minimize(cvar), constraints)
    try:
        problem.solve(solver="HIGHS")
    except cp.error.SolverError:
        problem.solve(solver="CLARABEL")
    if problem.status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE} or weights.value is None:
        raise RuntimeError(f"CVaR optimization is infeasible or failed: status={problem.status}")
    values = np.asarray(weights.value, dtype=float).reshape(-1)
    if not np.isfinite(values).all():
        raise RuntimeError("CVaR solver returned non-finite weights")
    return pd.Series(values, index=clean.columns, name="weight")
