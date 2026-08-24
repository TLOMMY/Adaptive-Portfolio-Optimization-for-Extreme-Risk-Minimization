r"""Robust minimum-variance optimization over a finite covariance uncertainty set.

Model
-----
Ordinary minimum variance minimises :math:`x^\top \Sigma x` for a single
estimated :math:`\Sigma`, treating that estimate as known. The robust model
instead minimises the **worst-case** variance across a finite set of covariance
matrices :math:`\{Q_s\}`, each estimated from a different slice of the same
history. In epigraph form:

.. math::
    \min_{x, z} \quad & z \\
    \text{s.t.}\quad & x^\top Q_s x \le z \quad \forall\, s \\
                     & \mathbf{1}^\top x = 1 \\
                     & 0 \le x_i \le w_{\max} \\
                     & \textstyle\sum_{i \in c} x_i \le L_c \quad \forall\, c \\
                     & \mu^\top x \ge R_{\min}

Each :math:`Q_s` is positive semidefinite, so every quadratic constraint is
convex and the program is a convex QCQP (solved as a second-order cone program).
At the optimum :math:`z^\star = \max_s x^{\star\top} Q_s x^\star`: the epigraph
constraint that binds identifies the worst-case scenario.

Units
-----
The objective is **variance**, annualised, in the same units as the covariance
estimates. No square root is taken inside the optimization -- doing so would
change the objective, and minimising variance and minimising volatility give the
same argmin only because the square root is monotone, which is a property of the
objective rather than something to rely on inside a solver. Worst-case
volatility is reported afterwards as :math:`\sqrt{z^\star}`.

What this objective is not
--------------------------
It protects against *estimation* uncertainty in the covariance -- the risk that
the sample window happened to understate co-movement -- not against regimes
absent from the lookback entirely. A worst case taken over six overlapping
windows of the same three years is a statement about that history, not about
the future.
"""

from __future__ import annotations

import logging
from typing import Any

import cvxpy as cp
import numpy as np

from src.backtest.strategy import AllocationDecision, RebalanceContext
from src.data.window import MarketDataView
from src.estimation.covariance_scenarios import (
    CovarianceScenarioSet,
    CovarianceUncertaintySet,
    RollingWindowUncertaintySet,
)
from src.estimation.parameters import EstimatedParameters
from src.portfolio.base import (
    OptimizationOutcome,
    PortfolioOptimizer,
    SolverError,
)
from src.portfolio.constraints import ConstraintSet, build_constraints

logger = logging.getLogger(__name__)

DEFAULT_SOLVER = "CLARABEL"
"""The program is a convex QCQP; CLARABEL solves the resulting SOCP directly."""


class RobustMinimumVarianceOptimizer(PortfolioOptimizer):
    """Minimise worst-case annualised variance over a covariance uncertainty set."""

    name = "Robust Min-Variance"

    def __init__(
        self,
        constraints: ConstraintSet | None = None,
        asset_class_map: dict[str, list[str]] | None = None,
        lookback_days: int = 756,
        uncertainty_set: CovarianceUncertaintySet | None = None,
        solver: str = DEFAULT_SOLVER,
        name: str | None = None,
    ) -> None:
        super().__init__(
            constraints=constraints,
            asset_class_map=asset_class_map,
            lookback_days=lookback_days,
            name=name,
        )
        self.uncertainty_set = uncertainty_set or RollingWindowUncertaintySet()
        self.solver = solver
        self._covariances: CovarianceScenarioSet | None = None

    # -- Strategy protocol ---------------------------------------------------

    def build_uncertainty_set(self, view: MarketDataView) -> CovarianceScenarioSet:
        """Construct the uncertainty set from the view. Separated for testability."""
        return self.uncertainty_set.build(view, self.lookback_days)

    def allocate(
        self, view: MarketDataView, context: RebalanceContext
    ) -> AllocationDecision:
        # The uncertainty set is built from the same view the base class
        # estimates mu from, so every input to this decision shares one boundary.
        self._covariances = self.build_uncertainty_set(view)
        try:
            decision = super().allocate(view, context)
            # Recompute the worst case from the *returned* weights rather than
            # the raw solver iterate: cleaning renormalises, so these are the
            # numbers that actually describe the portfolio being reported.
            decision.diagnostics.update(
                self._worst_case_diagnostics(self._covariances, decision.weights)
            )
            return decision
        finally:
            self._covariances = None

    def _solve(
        self, parameters: EstimatedParameters, context: RebalanceContext
    ) -> OptimizationOutcome:
        covariances = self._covariances
        if covariances is None:
            raise SolverError("uncertainty set was not built before solving")
        if covariances.tickers != parameters.tickers:
            raise SolverError(
                f"covariance scenarios cover {covariances.tickers}, "
                f"expected {parameters.tickers}"
            )

        mu = parameters.mu
        tickers = parameters.tickers
        previous = self.current_weights_array(context, tickers)

        def solve(weights_for_turnover):
            target = self._resolve_return_target(
                mu, tickers, self.solver, weights_for_turnover
            )
            x, objective = self._minimise_worst_case(
                covariances, mu, tickers, target.effective, weights_for_turnover
            )
            return x, objective, target

        (weights, objective, target), relaxed = self._solve_with_turnover_fallback(
            solve, previous
        )

        diagnostics: dict[str, Any] = {
            # Annualised VARIANCE, not volatility. sqrt is applied only for
            # reporting, in _worst_case_diagnostics.
            "robust_objective": objective,
            "turnover_limit": self.constraints.max_turnover,
            "turnover_limit_relaxed": relaxed,
        }
        diagnostics.update(covariances.summary())
        diagnostics.update(target.diagnostics())

        return OptimizationOutcome(
            weights=weights,
            status="optimal_with_shortfall" if target.is_binding else "optimal",
            solver=self.solver,
            diagnostics=diagnostics,
        )

    # -- the program ---------------------------------------------------------

    def _minimise_worst_case(
        self,
        covariances: CovarianceScenarioSet,
        mu: np.ndarray,
        tickers: list[str],
        return_target: float | None,
        current_weights: np.ndarray | None = None,
    ) -> tuple[np.ndarray, float]:
        x = cp.Variable(len(tickers), name="x")
        z = cp.Variable(name="worst_case_variance")

        constraints = build_constraints(
            x, tickers, self.constraints, self.asset_class_map, current_weights
        )
        for scenario in covariances.scenarios:
            # psd_wrap: the matrices are PSD by construction and validated as
            # such, but floating-point symmetrisation can leave eigenvalues at
            # -1e-18, which CVXPY would otherwise reject.
            constraints.append(cp.quad_form(x, cp.psd_wrap(scenario.matrix)) <= z)

        if return_target is not None:
            constraints.append(mu @ x >= return_target)

        problem = cp.Problem(cp.Minimize(z), constraints)
        self._solve_problem(problem, self.solver, "robust min-variance stage")

        if x.value is None or z.value is None:
            raise SolverError("robust min-variance stage returned no solution")

        return np.asarray(x.value, dtype="float64"), float(z.value)

    # -- reporting -----------------------------------------------------------

    @staticmethod
    def _worst_case_diagnostics(
        covariances: CovarianceScenarioSet, weights
    ) -> dict[str, Any]:
        """Worst-case figures recomputed from the final weight vector."""
        variances = covariances.variances(weights)
        index = int(np.argmax(variances))
        worst = float(variances[index])
        return {
            "worst_case_variance": worst,
            # Reported only; never used as an optimization objective.
            "worst_case_volatility": float(np.sqrt(max(worst, 0.0))),
            "variance_by_scenario": [float(v) for v in variances],
            "worst_case_scenario_index": index,
            "worst_case_scenario_label": covariances.labels[index],
        }
