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
from src.portfolio.constraints import ConstraintSet, asset_class_exposures, build_constraints

logger = logging.getLogger(__name__)

WEIGHT_TOLERANCE = 1e-6
"""Slack allowed when verifying constraints on a returned solution.

Interior-point solvers land within a small tolerance of the boundary rather than
exactly on it, so a cap of 0.30 may come back as 0.30000000004. Violations
beyond this tolerance are treated as real.
"""

CLEAN_THRESHOLD = 1e-9
"""Weights with magnitude below this are treated as zero before renormalising."""

SHORTFALL_TOLERANCE = 1e-8
"""Below this, a reported return shortfall is solver noise rather than a real gap.

An interior-point solver settles a shortfall that is exactly zero at values
around 1e-10. Reporting that as an unattainable target would be wrong -- and
visibly so, since the achieved return then exceeds the target -- so
sub-tolerance shortfalls are snapped to exactly zero. In annualised decimals
1e-8 is a millionth of a percentage point, far below any meaningful difference.
"""

FEASIBILITY_SLACK = 1e-7
"""Relative relaxation applied to an exactly-binding return target.

When the target is unattainable, the closest attainable target is binding at the
optimum and the feasible region collapses to (near) a single point. An
interior-point solver can then return an inaccurate solution, or declare the
region infeasible outright.

The relaxation is applied *relative* to the target's magnitude,
``FEASIBILITY_SLACK * max(1, |target|)``, rather than as a fixed absolute amount:
an absolute slack that is comfortable for a target of 0.05 sits right on the
solver's own tolerance for a target of 5.0, which was observed to produce
`optimal_inaccurate` statuses. At 1e-7 relative the effective target differs
from the attainable one by at most a ten-thousandth of a percentage point.
"""


@dataclass(frozen=True, slots=True)
class ReturnTarget:
    """The outcome of reconciling a minimum-return requirement with feasibility.

    Attributes
    ----------
    target
        The requested minimum annualised return, or ``None`` if unset.
    shortfall
        The **minimum unavoidable shortfall**, an annualised decimal in the same
        units as ``target``. Zero when the target is attainable or unset.
    max_attainable
        The highest annualised expected return any feasible portfolio can
        deliver. ``None`` when no target was requested (it is not computed).
    effective
        The return constraint actually imposed on the model, or ``None`` when no
        target was requested. Equals ``target`` when attainable, and
        ``max_attainable`` (less a numerical relaxation) when not.
    """

    target: float | None
    shortfall: float
    max_attainable: float | None
    effective: float | None

    @property
    def is_binding(self) -> bool:
        """True when the target could not be met in full."""
        return self.shortfall > 0.0

    def diagnostics(self) -> dict[str, Any]:
        """The audit record. ``return_shortfall`` is always present."""
        record: dict[str, Any] = {
            "return_target": self.target,
            # Annualised decimal, in the same units as `return_target`.
            # 0.0 means the target was met, or that no target was set.
            "return_shortfall": self.shortfall,
        }
        if self.target is not None:
            record["max_attainable_return"] = self.max_attainable
            record["effective_return_target"] = (
                None if self.max_attainable is None else self.target - self.shortfall
            )
        return record


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

    # -- shared return-target mechanism  (decision D9) ------------------------

    def _resolve_return_target(
        self, mu: np.ndarray, tickers: list[str], solver: str
    ) -> ReturnTarget:
        """Reconcile the configured minimum-return requirement with feasibility.

        An unattainable target is never dropped. A nonnegative slack variable is
        minimised against it, yielding the exact minimum unavoidable shortfall;
        the model is then solved at the closest attainable target and the gap is
        reported. See :class:`ReturnTarget`.

        Shared by every optimizer so the mechanism -- and its numerical
        tolerances -- are identical across models.
        """
        target = self.constraints.min_return
        if target is None:
            return ReturnTarget(target=None, shortfall=0.0, max_attainable=None, effective=None)

        shortfall, max_attainable = self._minimum_shortfall(mu, tickers, target, solver)

        effective = target - shortfall
        if shortfall > 0.0:
            # Only a genuinely binding target needs the numerical relaxation;
            # an attainable one is imposed exactly as configured.
            effective -= FEASIBILITY_SLACK * max(1.0, abs(target))

        return ReturnTarget(
            target=target,
            shortfall=shortfall,
            max_attainable=max_attainable,
            effective=effective,
        )

    def _minimum_shortfall(
        self, mu: np.ndarray, tickers: list[str], target: float, solver: str
    ) -> tuple[float, float]:
        r"""Minimise the nonnegative shortfall :math:`s` against a return target.

        .. math::
            \min_{x, s} \; s
            \quad\text{s.t.}\quad
            \mu^\top x + s \ge R_{\min}, \; s \ge 0,
            \; \text{(structural constraints)}

        Returns ``(shortfall, max_attainable_return)``. A structurally infeasible
        constraint set raises here -- that is a configuration error, distinct
        from a target that is merely too ambitious.
        """
        x = cp.Variable(len(tickers), name="x")
        s = cp.Variable(nonneg=True, name="shortfall")

        constraints = build_constraints(x, tickers, self.constraints, self.asset_class_map)
        constraints.append(mu @ x + s >= target)

        problem = cp.Problem(cp.Minimize(s), constraints)
        self._solve_problem(problem, solver, "shortfall stage")

        if s.value is None or x.value is None:
            raise SolverError("shortfall stage returned no solution")

        shortfall = max(float(s.value), 0.0)
        if shortfall < SHORTFALL_TOLERANCE:
            shortfall = 0.0
        return shortfall, float(mu @ x.value)

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
