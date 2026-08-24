r"""Scenario-based CVaR (Expected Shortfall) optimization.

Model
-----
The Rockafellar-Uryasev formulation. For scenario :math:`s` the portfolio loss is

.. math:: L_s(x) = -r_s^\top x

with :math:`r_s` the asset-return vector in that scenario. Introducing the VaR
threshold :math:`z` and excess-loss variables :math:`u_s`:

.. math::
    \min_{x, z, u} \quad & z + \frac{1}{(1-\alpha)N} \sum_{s=1}^{N} u_s \\
    \text{s.t.}\quad & u_s \ge -r_s^\top x - z, \quad u_s \ge 0 \\
                     & \mathbf{1}^\top x = 1 \\
                     & 0 \le x_i \le w_{\max} \\
                     & \textstyle\sum_{i \in c} x_i \le L_c \quad \forall\, c \\
                     & \mu^\top x \ge R_{\min}

Every term is linear, so this is a **linear program** -- not a quadratic one.
That is the substantive difference from mean-variance: the objective penalises
only the magnitude of losses in the worst :math:`(1-\alpha)` fraction of
scenarios, and is entirely indifferent to dispersion elsewhere, including upside
dispersion. A portfolio with violent gains and mild losses is unremarkable to
this objective and unattractive to a variance objective.

At the optimum, :math:`z^\star` is the Value-at-Risk and the objective value is
the Conditional Value-at-Risk of the optimal portfolio. Minimising over
:math:`z` for *fixed* :math:`x` recovers exactly :math:`\mathrm{CVaR}_\alpha(x)`,
which is why the joint minimisation yields the CVaR-minimal portfolio rather
than merely a portfolio with a good bound.

Units and horizon
-----------------
Scenarios are returns over ``risk_horizon_days``. With the default horizon of 1
the optimized quantity is a **1-day historical CVaR** and is labelled as such
throughout. It is *not* annualised: a square-root-of-time rule is invalid for a
tail measure, and no rescaling is applied anywhere. A 1-day CVaR does not
describe long-horizon risk and must not be presented as if it did.

The minimum-return constraint, by contrast, is in **annualised** units, since it
comes from the shared estimation layer. The two live in different units on
purpose and both are labelled.
"""

from __future__ import annotations

import logging

import cvxpy as cp
import numpy as np

from src.backtest.strategy import RebalanceContext
from src.data.window import MarketDataView
from src.estimation.parameters import EstimatedParameters
from src.estimation.scenarios import (
    ReturnScenarios,
    ScenarioBuilder,
    build_scenario_builder,
)
from src.portfolio.base import (
    OptimizationOutcome,
    PortfolioOptimizer,
    SolverError,
)
from src.portfolio.constraints import ConstraintSet, build_constraints

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE = 0.95
"""Default :math:`\\alpha`. The objective then averages the worst 5% of scenarios."""

DEFAULT_SOLVER = "HIGHS"
"""The CVaR problem is a pure LP, and HiGHS is a dedicated LP solver.

Its simplex method terminates at a vertex with an exact basis, which suits a
problem whose optimal face is frequently degenerate -- many scenarios sit exactly
at the VaR threshold. CLARABEL (used for the quadratic mean-variance model)
solves it too and is available as a fallback.
"""


class CVaROptimizer(PortfolioOptimizer):
    r"""Minimise the :math:`\alpha`-level Conditional Value-at-Risk of losses.

    Parameters
    ----------
    confidence
        :math:`\alpha`, the tail confidence level. ``0.95`` averages the worst
        5% of scenarios.
    scenario_builder
        How scenarios are constructed. Defaults to one equiprobable scenario per
        daily return in the lookback window.
    risk_horizon_days
        Convenience for selecting a builder when none is supplied. ``1`` (the
        default) gives daily scenarios; see the module docstring on units.
    """

    name = "CVaR"

    def __init__(
        self,
        confidence: float = DEFAULT_CONFIDENCE,
        constraints: ConstraintSet | None = None,
        asset_class_map: dict[str, list[str]] | None = None,
        lookback_days: int = 756,
        risk_horizon_days: int = 1,
        scenario_builder: ScenarioBuilder | None = None,
        solver: str = DEFAULT_SOLVER,
        name: str | None = None,
    ) -> None:
        super().__init__(
            constraints=constraints,
            asset_class_map=asset_class_map,
            lookback_days=lookback_days,
            name=name,
        )
        if not 0.0 < confidence < 1.0:
            raise ValueError(f"confidence must lie in (0, 1), got {confidence}")
        self.confidence = float(confidence)
        self.scenario_builder = scenario_builder or build_scenario_builder(risk_horizon_days)
        self.solver = solver

    @property
    def risk_horizon_days(self) -> int:
        return self.scenario_builder.horizon_days  # type: ignore[attr-defined]

    # -- solve ---------------------------------------------------------------

    def _build_scenarios(self, view: MarketDataView) -> ReturnScenarios:
        """Construct scenarios from the view. Separated so it is directly testable."""
        return self.scenario_builder.build(view, self.lookback_days)

    def allocate(self, view: MarketDataView, context: RebalanceContext):
        # Scenarios come from the same view the base class estimates mu and
        # Sigma from, so every input to this decision shares one boundary.
        self._scenarios = self._build_scenarios(view)
        try:
            return super().allocate(view, context)
        finally:
            self._scenarios = None

    def _solve(
        self, parameters: EstimatedParameters, context: RebalanceContext
    ) -> OptimizationOutcome:
        scenarios: ReturnScenarios | None = getattr(self, "_scenarios", None)
        if scenarios is None:
            raise SolverError("scenarios were not built before solving")
        if scenarios.tickers != parameters.tickers:
            raise SolverError(
                f"scenario assets {scenarios.tickers} do not match "
                f"estimated assets {parameters.tickers}"
            )

        mu = parameters.mu
        tickers = parameters.tickers
        previous = self.current_weights_array(context, tickers)

        def solve(weights_for_turnover):
            target = self._resolve_return_target(
                mu, tickers, self.solver, weights_for_turnover
            )
            x, var, cvar = self._minimise_cvar(
                scenarios, mu, tickers, target.effective, weights_for_turnover
            )
            return x, var, cvar, target

        (weights, var, cvar, target), relaxed = self._solve_with_turnover_fallback(
            solve, previous
        )

        diagnostics = {
            "cvar_confidence": self.confidence,
            "turnover_limit": self.constraints.max_turnover,
            "turnover_limit_relaxed": relaxed,
            # Loss units, positive = loss, over `risk_horizon_days`. NOT annualised.
            "cvar": cvar,
            "var": var,
            "risk_horizon_days": scenarios.horizon_days,
        }
        diagnostics.update(scenarios.summary())
        diagnostics.update(target.diagnostics())

        return OptimizationOutcome(
            weights=weights,
            status="optimal_with_shortfall" if target.is_binding else "optimal",
            solver=self.solver,
            diagnostics=diagnostics,
        )

    def _minimise_cvar(
        self,
        scenarios: ReturnScenarios,
        mu: np.ndarray,
        tickers: list[str],
        return_target: float | None,
        current_weights: np.ndarray | None = None,
    ) -> tuple[np.ndarray, float, float]:
        """Solve the Rockafellar-Uryasev LP. Returns ``(weights, VaR, CVaR)``."""
        n_scenarios = scenarios.n_scenarios
        returns = scenarios.returns

        x = cp.Variable(len(tickers), name="x")
        z = cp.Variable(name="var")          # the VaR threshold
        u = cp.Variable(n_scenarios, nonneg=True, name="excess_loss")

        constraints = build_constraints(
            x, tickers, self.constraints, self.asset_class_map, current_weights
        )
        # u_s >= L_s(x) - z, with L_s(x) = -r_s' x. Vectorised over scenarios.
        constraints.append(u >= -(returns @ x) - z)
        if return_target is not None:
            constraints.append(mu @ x >= return_target)

        # The RU tail term is  (1 / ((1-a) N)) * sum_s u_s, which for equiprobable
        # scenarios equals  (1 / (1-a)) * sum_s p_s u_s. Writing it as an explicit
        # inner product against the scenario probabilities is mathematically
        # identical here and generalises to non-uniform weighting without a
        # change of formulation.
        #
        # It also avoids `cp.sum` over a long vector. CVXPY derives that atom's
        # output shape via `np.sum(np.empty(shape))` -- summing uninitialised
        # memory and keeping only `.shape`. When the garbage happens to hold NaN
        # or mixed +/-inf, numpy emits "invalid value encountered in reduce".
        # The summed values are discarded, so the warning is harmless, but it is
        # intermittent (observed ~3 runs in 15) and would otherwise appear at
        # random in output. See test_cvar.py::test_solving_emits_no_numpy_warnings.
        probabilities = scenarios.probabilities
        objective = cp.Minimize(z + (probabilities @ u) / (1.0 - self.confidence))

        problem = cp.Problem(objective, constraints)
        self._solve_problem(problem, self.solver, "CVaR stage")

        if x.value is None or z.value is None:
            raise SolverError("CVaR stage returned no solution")

        return (
            np.asarray(x.value, dtype="float64"),
            float(z.value),
            float(problem.value),
        )
