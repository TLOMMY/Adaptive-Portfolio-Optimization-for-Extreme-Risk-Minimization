r"""Markowitz mean-variance optimization.

Model
-----
Decision variable :math:`x \in \mathbb{R}^N`, the fraction of capital in each asset.

.. math::
    \max_{x} \quad & \mu^\top x - \lambda\, x^\top \Sigma x \\
    \text{s.t.}\quad & \mathbf{1}^\top x = 1 \\
                     & 0 \le x_i \le w_{\max} \\
                     & \textstyle\sum_{i \in c} x_i \le L_c \quad \forall\, c \\
                     & \mu^\top x \ge R_{\min}

:math:`\mu` and :math:`\Sigma` are the annualised sample-mean and Ledoit-Wolf
estimates from the lookback window.  :math:`\lambda` is the risk-aversion
coefficient: larger values weight variance more heavily and produce lower-risk
portfolios.  Because :math:`\Sigma` is positive semidefinite, :math:`x^\top\Sigma x`
is convex, so the problem is a convex QP with a unique optimal value.

Unattainable return targets
---------------------------
:math:`R_{\min}` may exceed what any feasible portfolio can deliver.  The target
is never dropped in that case.  Instead a nonnegative shortfall variable
:math:`s` measures how far the target is from attainable:

.. math::
    \min_{x, s} \quad & s \\
    \text{s.t.}\quad & \mu^\top x + s \ge R_{\min}, \quad s \ge 0 \\
                     & \text{(all structural constraints)}

The optimal :math:`s^\star` is the *minimum unavoidable shortfall*: zero when the
target is attainable, and otherwise exactly the gap between the target and the
best achievable expected return.  The mean-variance problem is then solved with
the closest attainable target, :math:`R_{\min} - s^\star`, and :math:`s^\star` is
reported as ``return_shortfall`` in annualised decimal units.

This is preferred to a big-M penalty: it needs no penalty weight to be tuned,
and :math:`s^\star` is exact rather than an artefact of how the penalty was
scaled.
"""

from __future__ import annotations

import logging

import cvxpy as cp
import numpy as np

from src.backtest.strategy import RebalanceContext
from src.estimation.parameters import EstimatedParameters
from src.portfolio.base import (
    OptimizationOutcome,
    PortfolioOptimizer,
    SolverError,
)
from src.portfolio.constraints import ConstraintSet, build_constraints

logger = logging.getLogger(__name__)

DEFAULT_RISK_AVERSION = 2.5
"""Default :math:`\\lambda`. With annualised inputs this trades one unit of
variance against 2.5 units of expected return, a moderate setting; investor
profiles override it."""

DEFAULT_SOLVER = "CLARABEL"
"""Both stages use one solver so the feasibility stage and the mean-variance
stage agree on the boundary to within the same numerical tolerance."""


class MarkowitzOptimizer(PortfolioOptimizer):
    """Mean-variance optimizer with an exact return-shortfall mechanism."""

    name = "Markowitz"

    def __init__(
        self,
        risk_aversion: float = DEFAULT_RISK_AVERSION,
        constraints: ConstraintSet | None = None,
        asset_class_map: dict[str, list[str]] | None = None,
        lookback_days: int = 756,
        solver: str = DEFAULT_SOLVER,
        name: str | None = None,
    ) -> None:
        super().__init__(
            constraints=constraints,
            asset_class_map=asset_class_map,
            lookback_days=lookback_days,
            name=name,
        )
        if risk_aversion < 0:
            raise ValueError(f"risk_aversion must be non-negative, got {risk_aversion}")
        self.risk_aversion = float(risk_aversion)
        self.solver = solver

    # -- solve ---------------------------------------------------------------

    def _solve(
        self, parameters: EstimatedParameters, context: RebalanceContext
    ) -> OptimizationOutcome:
        mu, sigma = parameters.mu, parameters.sigma
        tickers = parameters.tickers
        previous = self.current_weights_array(context, tickers)

        def solve(weights_for_turnover):
            target = self._resolve_return_target(
                mu, tickers, self.solver, weights_for_turnover
            )
            x = self._mean_variance(
                mu, sigma, tickers, target.effective, weights_for_turnover
            )
            return x, target

        (weights, target), relaxed = self._solve_with_turnover_fallback(solve, previous)

        diagnostics = {
            "risk_aversion": self.risk_aversion,
            "turnover_limit": self.constraints.max_turnover,
            "turnover_limit_relaxed": relaxed,
        }
        diagnostics.update(target.diagnostics())

        return OptimizationOutcome(
            weights=weights,
            status="optimal_with_shortfall" if target.is_binding else "optimal",
            solver=self.solver,
            diagnostics=diagnostics,
        )

    def _mean_variance(
        self,
        mu: np.ndarray,
        sigma: np.ndarray,
        tickers: list[str],
        return_target: float | None,
        current_weights: np.ndarray | None = None,
    ) -> np.ndarray:
        x = cp.Variable(len(tickers), name="x")

        constraints = build_constraints(
            x, tickers, self.constraints, self.asset_class_map, current_weights
        )
        if return_target is not None:
            constraints.append(mu @ x >= return_target)

        # psd_wrap avoids CVXPY rejecting a matrix that is PSD in exact
        # arithmetic but shows eigenvalues at -1e-18 after floating-point
        # symmetrisation. Positive semidefiniteness is enforced upstream in
        # `estimation.covariance.ensure_positive_semidefinite`.
        risk = cp.quad_form(x, cp.psd_wrap(sigma))
        objective = cp.Maximize(mu @ x - self.risk_aversion * risk)

        problem = cp.Problem(objective, constraints)
        self._solve_problem(problem, self.solver, "mean-variance stage")

        if x.value is None:
            raise SolverError("mean-variance stage returned no solution")
        return np.asarray(x.value, dtype="float64")
