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

DEFAULT_RISK_AVERSION = 2.5
"""Default :math:`\\lambda`. With annualised inputs this trades one unit of
variance against 2.5 units of expected return, a moderate setting; investor
profiles override it."""

DEFAULT_SOLVER = "CLARABEL"
"""Both stages use one solver so the feasibility stage and the mean-variance
stage agree on the boundary to within the same numerical tolerance."""

SHORTFALL_TOLERANCE = 1e-8
"""Below this, a reported shortfall is solver noise rather than a real gap.

An interior-point solver settles a shortfall that is exactly zero at values
around 1e-10. Reporting that as an unattainable target would be wrong -- and
visibly so, since the achieved return exceeds the target in those cases -- so
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
        target = self.constraints.min_return

        shortfall = 0.0
        max_attainable: float | None = None
        effective_target: float | None = None

        if target is not None:
            shortfall, max_attainable = self._minimum_shortfall(mu, tickers, target)
            # When the target is attainable the constraint is imposed as given;
            # only a genuinely binding target needs the numerical relaxation.
            effective_target = target - shortfall
            if shortfall > 0.0:
                effective_target -= FEASIBILITY_SLACK * max(1.0, abs(target))

        weights = self._mean_variance(mu, sigma, tickers, effective_target)

        status = "optimal_with_shortfall" if shortfall > 0.0 else "optimal"
        diagnostics = {
            "risk_aversion": self.risk_aversion,
            "return_target": target,
            # Annualised decimal, in the same units as `return_target`.
            # 0.0 means the target was met, or that no target was set.
            "return_shortfall": shortfall,
        }
        if target is not None:
            diagnostics["max_attainable_return"] = max_attainable
            diagnostics["effective_return_target"] = target - shortfall

        return OptimizationOutcome(
            weights=weights,
            status=status,
            solver=self.solver,
            diagnostics=diagnostics,
        )

    # -- stage 1: how far is the target from attainable? ---------------------

    def _minimum_shortfall(
        self, mu: np.ndarray, tickers: list[str], target: float
    ) -> tuple[float, float]:
        r"""Minimise the nonnegative shortfall :math:`s` against the return target.

        Returns ``(shortfall, max_attainable_return)``. A structurally infeasible
        constraint set raises here -- that is a configuration error, distinct
        from a target that is merely too ambitious.
        """
        x = cp.Variable(len(tickers), name="x")
        s = cp.Variable(nonneg=True, name="shortfall")

        constraints = build_constraints(x, tickers, self.constraints, self.asset_class_map)
        constraints.append(mu @ x + s >= target)

        problem = cp.Problem(cp.Minimize(s), constraints)
        self._solve_problem(problem, self.solver, "shortfall stage")

        if s.value is None or x.value is None:
            raise SolverError("shortfall stage returned no solution")

        shortfall = max(float(s.value), 0.0)
        if shortfall < SHORTFALL_TOLERANCE:
            shortfall = 0.0
        max_attainable = float(mu @ x.value)
        return shortfall, max_attainable

    # -- stage 2: mean-variance under the attainable target ------------------

    def _mean_variance(
        self,
        mu: np.ndarray,
        sigma: np.ndarray,
        tickers: list[str],
        return_target: float | None,
    ) -> np.ndarray:
        x = cp.Variable(len(tickers), name="x")

        constraints = build_constraints(x, tickers, self.constraints, self.asset_class_map)
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
