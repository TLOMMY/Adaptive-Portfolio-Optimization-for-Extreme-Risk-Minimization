"""Common machinery for every portfolio optimizer.

A ``PortfolioOptimizer`` satisfies the backtest engine's ``Strategy`` protocol,
so optimizers plug into the time machine without the engine knowing anything
about how they compute weights.

The base class owns the parts that must be identical across models -- parameter
estimation, weight cleaning, constraint verification and the diagnostics record
-- leaving each subclass responsible only for its own optimization problem.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import cvxpy as cp
import numpy as np
import pandas as pd

from src.backtest.strategy import AllocationDecision, RebalanceContext
from src.data.window import MarketDataView
from src.estimation.parameters import EstimatedParameters, estimate_parameters
from src.portfolio.constraints import ConstraintSet, asset_class_exposures

logger = logging.getLogger(__name__)

WEIGHT_TOLERANCE = 1e-6
"""Slack allowed when verifying constraints on a returned solution.

Interior-point solvers land within a small tolerance of the boundary rather than
exactly on it, so a cap of 0.30 may come back as 0.30000000004. Violations
beyond this tolerance are treated as real.
"""

CLEAN_THRESHOLD = 1e-9
"""Weights with magnitude below this are treated as zero before renormalising."""


class OptimizationError(RuntimeError):
    """Base class for optimizer failures. Carries structured diagnostics."""

    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class InfeasibleProblemError(OptimizationError):
    """The problem has no feasible solution.

    Raised only for structural infeasibility -- a feasible region that is empty
    regardless of objective. An unattainable *return target* is not this: it is
    measured by the shortfall mechanism and reported, never raised.
    """


class SolverError(OptimizationError):
    """The solver failed to return a usable solution."""


@dataclass(slots=True)
class OptimizationOutcome:
    """What a subclass returns from :meth:`PortfolioOptimizer._solve`."""

    weights: np.ndarray
    status: str
    solver: str
    diagnostics: dict[str, Any] = field(default_factory=dict)


class PortfolioOptimizer(ABC):
    """Base class for models that turn estimated parameters into weights.

    Parameters
    ----------
    constraints
        The feasible region. Defaults to long-only, fully invested, uncapped.
    asset_class_map
        ``asset_class -> tickers``, needed only when asset-class limits are set.
    lookback_days
        Estimation window length. When ``None`` the optimizer must be given one
        by the caller before use; the backtest supplies it from settings.
    """

    name: str = "optimizer"

    def __init__(
        self,
        constraints: ConstraintSet | None = None,
        asset_class_map: dict[str, list[str]] | None = None,
        lookback_days: int = 756,
        name: str | None = None,
    ) -> None:
        self.constraints = constraints if constraints is not None else ConstraintSet()
        self.asset_class_map = asset_class_map or {}
        self.lookback_days = lookback_days
        if name is not None:
            self.name = name

    # -- Strategy protocol ---------------------------------------------------

    def allocate(self, view: MarketDataView, context: RebalanceContext) -> AllocationDecision:
        """Estimate parameters from the view and solve for target weights.

        The view is the only source of market information. Nothing in this call
        chain has access to data after ``view.as_of``.
        """
        parameters = estimate_parameters(view, self.lookback_days)
        self.constraints.validate_for(parameters.tickers, self.asset_class_map)

        started = time.perf_counter()
        outcome = self._solve(parameters, context)
        elapsed = time.perf_counter() - started

        weights = self._clean(outcome.weights, parameters.tickers)
        self._verify(weights, parameters.tickers)

        diagnostics: dict[str, Any] = {
            "solver": outcome.solver,
            "solve_seconds": round(elapsed, 4),
            "expected_return": parameters.portfolio_return(weights),
            "expected_volatility": parameters.portfolio_volatility(weights),
        }
        diagnostics.update(parameters.summary())
        diagnostics.update(outcome.diagnostics)

        if self.asset_class_map:
            diagnostics["asset_class_exposure"] = asset_class_exposures(
                weights.to_dict(), parameters.tickers, self.asset_class_map
            )

        return AllocationDecision(
            weights=weights, status=outcome.status, diagnostics=diagnostics
        )

    @abstractmethod
    def _solve(
        self, parameters: EstimatedParameters, context: RebalanceContext
    ) -> OptimizationOutcome:
        """Solve this model's optimization problem. Subclass responsibility."""

    # -- shared helpers ------------------------------------------------------

    def _clean(self, raw: np.ndarray, tickers: list[str]) -> pd.Series:
        """Remove solver noise and renormalise to a valid weight vector.

        Interior-point solvers return values like ``-3e-17`` for weights that are
        exactly zero, and a budget that sums to ``0.9999999997``. Both are
        artefacts of the numerical method, not decisions, so they are cleaned
        here rather than propagating into reported allocations.
        """
        weights = np.asarray(raw, dtype="float64").flatten()
        if weights.shape != (len(tickers),):
            raise SolverError(
                f"solver returned {weights.shape} weights for {len(tickers)} assets"
            )
        if not np.all(np.isfinite(weights)):
            raise SolverError("solver returned non-finite weights")

        weights[np.abs(weights) < CLEAN_THRESHOLD] = 0.0
        weights = np.clip(weights, 0.0, None)

        total = weights.sum()
        if total <= 0:
            raise SolverError("solver returned an all-zero portfolio")
        weights = weights / total

        return pd.Series(weights, index=tickers, name="weight")

    def _verify(self, weights: pd.Series, tickers: list[str]) -> None:
        """Assert the returned solution actually satisfies its constraints.

        Cleaning renormalises, which can in principle push a weight fractionally
        above a cap, so verification happens *after* cleaning rather than being
        trusted to the solver.
        """
        total = float(weights.sum())
        if abs(total - 1.0) > WEIGHT_TOLERANCE:
            raise SolverError(f"weights sum to {total}, expected 1.0")

        if (weights < -WEIGHT_TOLERANCE).any():
            offenders = weights[weights < -WEIGHT_TOLERANCE]
            raise SolverError(f"negative weights returned: {offenders.to_dict()}")

        cap = self.constraints.max_weight
        breaches = weights[weights > cap + WEIGHT_TOLERANCE]
        if not breaches.empty:
            raise SolverError(
                f"weights exceed max_weight={cap}: {breaches.round(6).to_dict()}"
            )

        for cls, limit in self.constraints.asset_class_limits.items():
            members = [t for t in self.asset_class_map.get(cls, []) if t in tickers]
            exposure = float(weights.reindex(members).fillna(0.0).sum())
            if exposure > limit + WEIGHT_TOLERANCE:
                raise SolverError(
                    f"asset class {cls!r} exposure {exposure:.6f} exceeds limit {limit}"
                )

    @staticmethod
    def _solve_problem(
        problem: cp.Problem,
        solver: str,
        context: str,
        **solver_options: Any,
    ) -> str:
        """Solve a CVXPY problem and insist on a usable status."""
        try:
            problem.solve(solver=solver, **solver_options)
        except cp.error.SolverError as exc:
            raise SolverError(f"{context}: solver {solver} failed: {exc}") from exc

        status = problem.status
        if status in (cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE):
            raise InfeasibleProblemError(f"{context}: problem is infeasible ({status})")
        if status in (cp.UNBOUNDED, cp.UNBOUNDED_INACCURATE):
            raise SolverError(f"{context}: problem is unbounded ({status})")
        if status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
            raise SolverError(f"{context}: unusable solver status {status!r}")
        if status == cp.OPTIMAL_INACCURATE:
            logger.warning("%s: solver returned an inaccurate solution", context)
        return status
