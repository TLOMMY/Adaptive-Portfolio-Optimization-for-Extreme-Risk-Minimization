"""Tests for the robust minimum-variance optimizer.

Optimality is checked two independent ways: against an exhaustive grid search on
a three-asset fixture, and against structural properties the worst-case objective
must satisfy (monotonicity in the uncertainty set, reduction to ordinary minimum
variance for a singleton set).
"""

from __future__ import annotations

import warnings

import cvxpy as cp
import numpy as np
import pandas as pd
import pytest
from conftest import DISTINCT_ASSET_CLASSES

from src.data.window import MarketDataView
from src.estimation.covariance_scenarios import (
    CovarianceScenario,
    CovarianceScenarioSet,
    CovarianceUncertaintySet,
    RollingWindowUncertaintySet,
)
from src.estimation.parameters import estimate_parameters
from src.portfolio.constraints import ConstraintSet
from src.portfolio.equal_weight import EqualWeightOptimizer
from src.portfolio.robust_variance import RobustMinimumVarianceOptimizer

LOOKBACK = 756
SMALL_LOOKBACK = 500
TOL = 1e-6


@pytest.fixture
def long_view(risk_prices) -> MarketDataView:
    return MarketDataView(risk_prices, risk_prices.index[1900])


@pytest.fixture
def long_context(risk_prices):
    from src.backtest.strategy import RebalanceContext

    return RebalanceContext(
        as_of=risk_prices.index[1900],
        current_weights=pd.Series(0.0, index=list(risk_prices.columns)),
        portfolio_value=100_000.0,
        period_index=0,
    )


def build(**constraint_kwargs) -> RobustMinimumVarianceOptimizer:
    return RobustMinimumVarianceOptimizer(
        lookback_days=LOOKBACK,
        asset_class_map=DISTINCT_ASSET_CLASSES,
        constraints=ConstraintSet(**constraint_kwargs),
    )


class FixedUncertaintySet(CovarianceUncertaintySet):
    """A set supplied directly, for tests that need exact control of the matrices."""

    method = "fixed"

    def __init__(self, matrices: list[np.ndarray], tickers: list[str]) -> None:
        self.matrices = matrices
        self.tickers = tickers

    def build(self, view, lookback_days) -> CovarianceScenarioSet:
        scenarios = tuple(
            CovarianceScenario(
                matrix=m, tickers=self.tickers, label=f"fixed{i}", n_observations=252,
                window_start=view.as_of - pd.Timedelta(days=365),
                window_end=view.as_of, shrinkage=0.0,
            )
            for i, m in enumerate(self.matrices)
        )
        return CovarianceScenarioSet(
            scenarios=scenarios, tickers=self.tickers, as_of=view.as_of,
            method=self.method, window_length=252, stride=126,
        )


# ---------------------------------------------------------------------------
# Optimization validity
# ---------------------------------------------------------------------------


def test_weights_sum_to_one(long_view, long_context):
    decision = build().allocate(long_view, long_context)
    assert decision.weights.sum() == pytest.approx(1.0, abs=TOL)


def test_no_negative_weights(long_view, long_context):
    assert (build().allocate(long_view, long_context).weights >= 0).all()


@pytest.mark.parametrize("cap", [0.25, 0.3, 0.5, 0.8])
def test_max_weight_constraint_is_respected(cap, long_view, long_context):
    weights = build(max_weight=cap).allocate(long_view, long_context).weights
    assert weights.max() <= cap + TOL


@pytest.mark.parametrize("limit", [0.2, 0.4, 0.6])
def test_asset_class_constraint_is_respected(limit, long_view, long_context):
    decision = build(asset_class_limits={"Equity": limit}).allocate(long_view, long_context)
    assert decision.weights[["STOCK", "WILD"]].sum() <= limit + TOL


def test_all_constraints_hold_together(long_view, long_context):
    weights = build(
        max_weight=0.4, asset_class_limits={"Equity": 0.5}, min_return=0.02
    ).allocate(long_view, long_context).weights

    assert weights.sum() == pytest.approx(1.0, abs=TOL)
    assert (weights >= 0).all()
    assert weights.max() <= 0.4 + TOL
    assert weights[["STOCK", "WILD"]].sum() <= 0.5 + TOL


def test_solver_status_is_valid_and_reported(long_view, long_context):
    decision = build().allocate(long_view, long_context)
    assert decision.status == "optimal"
    assert decision.diagnostics["solver"] == "CLARABEL"
    assert decision.diagnostics["solve_seconds"] >= 0


def test_optimizer_is_deterministic(long_view, long_context):
    optimizer = build(max_weight=0.5)
    a = optimizer.allocate(long_view, long_context)
    b = optimizer.allocate(long_view, long_context)
    pd.testing.assert_series_equal(a.weights, b.weights)


# ---------------------------------------------------------------------------
# The objective means what it says
# ---------------------------------------------------------------------------


def test_robust_objective_equals_the_worst_case_over_scenarios(long_view, long_context):
    decision = build(max_weight=0.5).allocate(long_view, long_context)
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)

    expected = scenarios.worst_case_variance(decision.weights)
    assert decision.diagnostics["worst_case_variance"] == pytest.approx(expected, abs=1e-12)
    assert decision.diagnostics["robust_objective"] == pytest.approx(expected, abs=1e-8)


def test_reported_worst_case_scenario_is_correct(long_view, long_context):
    decision = build(max_weight=0.5).allocate(long_view, long_context)
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)

    index = decision.diagnostics["worst_case_scenario_index"]
    variances = scenarios.variances(decision.weights)

    assert index == int(np.argmax(variances))
    assert decision.diagnostics["worst_case_scenario_label"] == scenarios.labels[index]
    assert decision.diagnostics["variance_by_scenario"][index] == pytest.approx(
        variances.max()
    )


def test_per_scenario_variances_are_reported_for_every_scenario(long_view, long_context):
    diagnostics = build(max_weight=0.5).allocate(long_view, long_context).diagnostics
    assert len(diagnostics["variance_by_scenario"]) == diagnostics["n_covariance_scenarios"] == 6
    assert all(v >= 0 for v in diagnostics["variance_by_scenario"])


def test_worst_case_volatility_is_the_square_root_of_the_objective(long_view, long_context):
    """No square root is taken inside the program; it is reporting only."""
    diagnostics = build(max_weight=0.5).allocate(long_view, long_context).diagnostics
    assert diagnostics["worst_case_volatility"] == pytest.approx(
        np.sqrt(diagnostics["worst_case_variance"])
    )


def test_diagnostics_record_the_uncertainty_set_configuration(long_view, long_context):
    diagnostics = build().allocate(long_view, long_context).diagnostics
    assert diagnostics["covariance_window_length"] == 252
    assert diagnostics["covariance_window_stride"] == 126
    assert diagnostics["n_covariance_scenarios"] == 6


# ---------------------------------------------------------------------------
# Optimality
# ---------------------------------------------------------------------------


def test_robust_beats_equal_weight_on_worst_case_variance(long_view, long_context):
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)

    robust = build().allocate(long_view, long_context)
    equal = EqualWeightOptimizer(lookback_days=LOOKBACK).allocate(long_view, long_context)

    equal_worst = scenarios.worst_case_variance(equal.weights)
    assert robust.diagnostics["worst_case_variance"] <= equal_worst + 1e-12


def test_robust_matches_a_brute_force_grid_search(three_asset_view, three_asset_context):
    """Exhaustive search on a three-asset simplex must not beat the optimizer."""
    builder = RollingWindowUncertaintySet(
        window_length=200, stride=100, n_subwindows=3, min_observations=150
    )
    optimizer = RobustMinimumVarianceOptimizer(
        lookback_days=SMALL_LOOKBACK, uncertainty_set=builder, constraints=ConstraintSet()
    )
    decision = optimizer.allocate(three_asset_view, three_asset_context)
    scenarios = builder.build(three_asset_view, SMALL_LOOKBACK)

    step = 0.005
    grid = np.arange(0.0, 1.0 + step / 2, step)
    best = np.inf
    for a in grid:
        for b in np.arange(0.0, 1.0 - a + step / 2, step):
            weights = np.array([a, b, 1.0 - a - b])
            if weights[2] < -1e-12:
                continue
            best = min(best, scenarios.worst_case_variance(weights))

    achieved = decision.diagnostics["worst_case_variance"]
    assert achieved <= best + 1e-9, f"optimizer {achieved} worse than grid best {best}"
    # And the grid cannot beat it by more than its own resolution.
    assert best <= achieved + 1e-5


def test_a_singleton_set_reduces_to_ordinary_minimum_variance(
    three_asset_view, three_asset_context
):
    """With one covariance matrix the worst case is that matrix."""
    from src.estimation.covariance import ledoit_wolf_covariance

    sigma, _ = ledoit_wolf_covariance(three_asset_view, SMALL_LOOKBACK)
    tickers = list(sigma.columns)
    matrix = sigma.to_numpy()

    robust = RobustMinimumVarianceOptimizer(
        lookback_days=SMALL_LOOKBACK,
        uncertainty_set=FixedUncertaintySet([matrix], tickers),
        constraints=ConstraintSet(),
    ).allocate(three_asset_view, three_asset_context)

    # Ordinary minimum variance, solved independently.
    x = cp.Variable(len(tickers))
    problem = cp.Problem(
        cp.Minimize(cp.quad_form(x, cp.psd_wrap(matrix))),
        [cp.sum(x) == 1, x >= 0, x <= 1.0],
    )
    problem.solve(solver="CLARABEL")
    reference = np.asarray(x.value).flatten()

    # The objective is the well-determined quantity and is asserted tightly.
    # Weights are asserted more loosely because the minimum-variance objective is
    # flat near its optimum: with curvature ~2*Sigma, a 1e-4 difference in weights
    # corresponds to an objective difference of order 1e-10, so two solvers
    # agreeing on the value to 1e-9 can legitimately differ on the argmin by more
    # than that. Demanding 1e-5 on weights would be testing solver internals.
    assert robust.diagnostics["worst_case_variance"] == pytest.approx(
        float(problem.value), abs=1e-9
    )
    assert np.allclose(robust.weights.to_numpy(), reference, atol=1e-3)
    assert robust.weights.sum() == pytest.approx(1.0, abs=1e-9)


def test_adding_an_adverse_scenario_cannot_improve_the_optimum(
    three_asset_view, three_asset_context
):
    """The worst-case objective is monotone non-decreasing in the uncertainty set."""
    from src.estimation.covariance import ledoit_wolf_covariance

    sigma, _ = ledoit_wolf_covariance(three_asset_view, SMALL_LOOKBACK)
    tickers = list(sigma.columns)
    base = sigma.to_numpy()
    adverse = base * 3.0  # a strictly more hostile scenario

    smaller = RobustMinimumVarianceOptimizer(
        lookback_days=SMALL_LOOKBACK,
        uncertainty_set=FixedUncertaintySet([base], tickers),
        constraints=ConstraintSet(),
    ).allocate(three_asset_view, three_asset_context)

    larger = RobustMinimumVarianceOptimizer(
        lookback_days=SMALL_LOOKBACK,
        uncertainty_set=FixedUncertaintySet([base, adverse], tickers),
        constraints=ConstraintSet(),
    ).allocate(three_asset_view, three_asset_context)

    assert (
        larger.diagnostics["worst_case_variance"]
        >= smaller.diagnostics["worst_case_variance"] - 1e-12
    )


def test_a_dominated_extra_scenario_leaves_the_optimum_unchanged(
    three_asset_view, three_asset_context
):
    """Adding a uniformly milder scenario cannot change the worst case."""
    from src.estimation.covariance import ledoit_wolf_covariance

    sigma, _ = ledoit_wolf_covariance(three_asset_view, SMALL_LOOKBACK)
    tickers = list(sigma.columns)
    base = sigma.to_numpy()
    mild = base * 0.25

    alone = RobustMinimumVarianceOptimizer(
        lookback_days=SMALL_LOOKBACK,
        uncertainty_set=FixedUncertaintySet([base], tickers),
        constraints=ConstraintSet(),
    ).allocate(three_asset_view, three_asset_context)

    with_mild = RobustMinimumVarianceOptimizer(
        lookback_days=SMALL_LOOKBACK,
        uncertainty_set=FixedUncertaintySet([base, mild], tickers),
        constraints=ConstraintSet(),
    ).allocate(three_asset_view, three_asset_context)

    assert with_mild.diagnostics["worst_case_variance"] == pytest.approx(
        alone.diagnostics["worst_case_variance"], abs=1e-8
    )


def test_robust_differs_from_single_window_minimum_variance(long_view, long_context):
    """The uncertainty set must actually change the answer, or it is decoration."""
    from src.estimation.covariance import ledoit_wolf_covariance

    sigma, _ = ledoit_wolf_covariance(long_view, LOOKBACK)
    tickers = list(sigma.columns)

    robust = build().allocate(long_view, long_context)
    single = RobustMinimumVarianceOptimizer(
        lookback_days=LOOKBACK,
        uncertainty_set=FixedUncertaintySet([sigma.to_numpy()], tickers),
        constraints=ConstraintSet(),
    ).allocate(long_view, long_context)

    assert not np.allclose(robust.weights.to_numpy(), single.weights.to_numpy(), atol=1e-4)


# ---------------------------------------------------------------------------
# Return target
# ---------------------------------------------------------------------------


def test_no_return_target_reports_zero_shortfall(long_view, long_context):
    diagnostics = build().allocate(long_view, long_context).diagnostics
    assert diagnostics["return_shortfall"] == 0.0
    assert diagnostics["return_target"] is None


def test_feasible_return_target_produces_zero_shortfall(long_view, long_context):
    parameters = estimate_parameters(long_view, LOOKBACK)
    attainable = float(parameters.expected_returns.max()) * 0.5

    decision = build(min_return=attainable).allocate(long_view, long_context)
    assert decision.diagnostics["return_shortfall"] == 0.0
    assert decision.status == "optimal"
    assert decision.diagnostics["expected_return"] >= attainable - TOL


def test_infeasible_return_target_produces_a_positive_shortfall(long_view, long_context):
    parameters = estimate_parameters(long_view, LOOKBACK)
    impossible = float(parameters.expected_returns.max()) + 0.5

    decision = build(min_return=impossible).allocate(long_view, long_context)
    assert decision.diagnostics["return_shortfall"] > 0
    assert decision.status == "optimal_with_shortfall"
    assert decision.diagnostics["max_attainable_return"] == pytest.approx(
        impossible - decision.diagnostics["return_shortfall"], abs=1e-7
    )


def test_a_return_target_raises_worst_case_variance(long_view, long_context):
    free = build(max_weight=0.5).allocate(long_view, long_context)
    constrained = build(max_weight=0.5, min_return=0.05).allocate(long_view, long_context)
    assert (
        constrained.diagnostics["worst_case_variance"]
        >= free.diagnostics["worst_case_variance"] - 1e-12
    )


def test_all_three_optimizers_share_one_attainable_return_boundary(
    long_view, long_context
):
    """Robust, CVaR and Markowitz must agree on what is attainable."""
    from src.portfolio.cvar import CVaROptimizer
    from src.portfolio.markowitz import MarkowitzOptimizer

    target = 5.0
    kwargs = dict(max_weight=0.4, asset_class_limits={"Equity": 0.6}, min_return=target)

    robust = build(**kwargs).allocate(long_view, long_context)
    markowitz = MarkowitzOptimizer(
        2.5, lookback_days=LOOKBACK, asset_class_map=DISTINCT_ASSET_CLASSES,
        constraints=ConstraintSet(**kwargs),
    ).allocate(long_view, long_context)
    cvar = CVaROptimizer(
        0.95, lookback_days=LOOKBACK, asset_class_map=DISTINCT_ASSET_CLASSES,
        constraints=ConstraintSet(**kwargs),
    ).allocate(long_view, long_context)

    for other in (markowitz, cvar):
        assert robust.diagnostics["return_shortfall"] == pytest.approx(
            other.diagnostics["return_shortfall"], abs=1e-7
        )
        assert robust.diagnostics["max_attainable_return"] == pytest.approx(
            other.diagnostics["max_attainable_return"], abs=1e-7
        )


# ---------------------------------------------------------------------------
# Look-ahead protection
# ---------------------------------------------------------------------------


def test_robust_sees_only_the_data_view(risk_prices, long_context):
    as_of = risk_prices.index[1900]
    optimizer = build(max_weight=0.5, min_return=0.02)

    clean = optimizer.allocate(MarketDataView(risk_prices, as_of), long_context)

    poisoned_panel = risk_prices.copy()
    poisoned_panel.loc[poisoned_panel.index > as_of] = 191_919.0
    poisoned = optimizer.allocate(MarketDataView(poisoned_panel, as_of), long_context)

    pd.testing.assert_series_equal(poisoned.weights, clean.weights)
    assert poisoned.diagnostics["worst_case_variance"] == pytest.approx(
        clean.diagnostics["worst_case_variance"]
    )


def test_robust_is_unchanged_when_the_future_is_missing(risk_prices, long_context):
    as_of = risk_prices.index[1900]
    optimizer = build(max_weight=0.5)

    full = optimizer.allocate(MarketDataView(risk_prices, as_of), long_context)
    truncated = optimizer.allocate(
        MarketDataView(risk_prices.loc[risk_prices.index <= as_of], as_of), long_context
    )
    pd.testing.assert_series_equal(truncated.weights, full.weights)


def test_uncertainty_set_state_does_not_leak_between_calls(long_view, long_context):
    optimizer = build()
    optimizer.allocate(long_view, long_context)
    assert optimizer._covariances is None


def test_covariance_window_never_crosses_the_decision_date(long_view, long_context):
    diagnostics = build().allocate(long_view, long_context).diagnostics
    assert pd.Timestamp(diagnostics["covariance_window_end"]) <= long_view.as_of


# ---------------------------------------------------------------------------
# Numerical hygiene
# ---------------------------------------------------------------------------


def test_solving_emits_no_numpy_warnings(long_view, long_context):
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        build(max_weight=0.5, min_return=0.02).allocate(long_view, long_context)


def test_solution_is_finite(long_view, long_context):
    decision = build(max_weight=0.5).allocate(long_view, long_context)
    assert np.all(np.isfinite(decision.weights.to_numpy()))
    assert np.isfinite(decision.diagnostics["worst_case_variance"])
    assert np.isfinite(decision.diagnostics["robust_objective"])
