"""Tests for the scenario-based CVaR optimizer.

The optimizer's own objective value is checked against the independently
implemented empirical CVaR metric, so a sign error or an off-by-one in the tail
would show up as a disagreement between two separately derived numbers rather
than being invisible.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest
from conftest import DISTINCT_ASSET_CLASSES

from src.data.window import MarketDataView
from src.estimation.parameters import estimate_parameters
from src.estimation.scenarios import (
    DailyHistoricalScenarios,
    InsufficientScenariosError,
    NonOverlappingHorizonScenarios,
)
from src.portfolio.constraints import ConstraintSet
from src.portfolio.cvar import CVaROptimizer
from src.portfolio.equal_weight import EqualWeightOptimizer
from src.risk.metrics import historical_cvar

LOOKBACK = 500
TOL = 1e-6


def build(confidence=0.95, **constraint_kwargs) -> CVaROptimizer:
    return CVaROptimizer(
        confidence=confidence,
        lookback_days=LOOKBACK,
        asset_class_map=DISTINCT_ASSET_CLASSES,
        constraints=ConstraintSet(**constraint_kwargs),
    )


# ---------------------------------------------------------------------------
# Optimization feasibility
# ---------------------------------------------------------------------------


def test_weights_sum_to_one(risk_view, rebalance_context):
    decision = build().allocate(risk_view, rebalance_context)
    assert decision.weights.sum() == pytest.approx(1.0, abs=TOL)


def test_no_negative_weights(risk_view, rebalance_context):
    weights = build().allocate(risk_view, rebalance_context).weights
    assert (weights >= 0).all()


@pytest.mark.parametrize("cap", [0.25, 0.3, 0.5, 0.8])
def test_max_weight_constraint_is_respected(cap, risk_view, rebalance_context):
    weights = build(max_weight=cap).allocate(risk_view, rebalance_context).weights
    assert weights.max() <= cap + TOL


@pytest.mark.parametrize("limit", [0.2, 0.4, 0.6])
def test_asset_class_constraint_is_respected(limit, risk_view, rebalance_context):
    decision = build(asset_class_limits={"Equity": limit}).allocate(
        risk_view, rebalance_context
    )
    assert decision.weights[["STOCK", "WILD"]].sum() <= limit + TOL


def test_all_constraints_hold_together(risk_view, rebalance_context):
    decision = build(
        max_weight=0.4, asset_class_limits={"Equity": 0.5}, min_return=0.02
    ).allocate(risk_view, rebalance_context)
    weights = decision.weights

    assert weights.sum() == pytest.approx(1.0, abs=TOL)
    assert (weights >= 0).all()
    assert weights.max() <= 0.4 + TOL
    assert weights[["STOCK", "WILD"]].sum() <= 0.5 + TOL


def test_solver_status_is_valid_and_reported(risk_view, rebalance_context):
    decision = build().allocate(risk_view, rebalance_context)
    assert decision.status == "optimal"
    assert decision.diagnostics["solver"] == "HIGHS"
    assert decision.diagnostics["solve_seconds"] >= 0


def test_invalid_confidence_is_rejected():
    for bad in (0.0, 1.0, -0.5, 1.5):
        with pytest.raises(ValueError, match="confidence must lie"):
            CVaROptimizer(confidence=bad)


def test_optimizer_is_deterministic(risk_view, rebalance_context):
    optimizer = build(max_weight=0.5)
    first = optimizer.allocate(risk_view, rebalance_context)
    second = optimizer.allocate(risk_view, rebalance_context)
    pd.testing.assert_series_equal(first.weights, second.weights)


# ---------------------------------------------------------------------------
# CVaR correctness
# ---------------------------------------------------------------------------


def test_reported_cvar_matches_the_independent_metric(risk_view, rebalance_context):
    """The LP objective value must equal the empirical CVaR of its own solution."""
    optimizer = build(max_weight=0.5)
    decision = optimizer.allocate(risk_view, rebalance_context)

    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)
    realised = scenarios.portfolio_returns(decision.weights)
    expected = historical_cvar(realised, confidence=0.95)

    assert decision.diagnostics["cvar"] == pytest.approx(expected, abs=1e-9)


def test_reported_var_is_the_tail_threshold(risk_view, rebalance_context):
    from src.risk.metrics import historical_var

    decision = build(max_weight=0.5).allocate(risk_view, rebalance_context)
    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)
    realised = scenarios.portfolio_returns(decision.weights)

    assert decision.diagnostics["var"] == pytest.approx(
        historical_var(realised, 0.95), abs=1e-7
    )


def test_cvar_is_at_least_var(risk_view, rebalance_context):
    """CVaR averages losses beyond VaR, so it can never be smaller."""
    diagnostics = build(max_weight=0.5).allocate(risk_view, rebalance_context).diagnostics
    assert diagnostics["cvar"] >= diagnostics["var"] - 1e-12


def test_optimized_cvar_is_no_worse_than_equal_weight(risk_view, rebalance_context):
    """The CVaR-minimal portfolio must beat 1/N on its own objective, in sample."""
    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)

    optimized = build().allocate(risk_view, rebalance_context)
    equal = EqualWeightOptimizer(lookback_days=LOOKBACK).allocate(
        risk_view, rebalance_context
    )

    equal_cvar = historical_cvar(scenarios.portfolio_returns(equal.weights), 0.95)
    assert optimized.diagnostics["cvar"] <= equal_cvar + 1e-9


def test_higher_confidence_gives_a_more_severe_tail(risk_view, rebalance_context):
    """A deeper tail cannot be less severe: CVaR is increasing in alpha."""
    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)
    weights = build().allocate(risk_view, rebalance_context).weights
    returns = scenarios.portfolio_returns(weights)

    values = [historical_cvar(returns, a) for a in (0.90, 0.95, 0.99)]
    assert values == sorted(values), f"CVaR must be non-decreasing in alpha: {values}"
    assert values[-1] > values[0], "the fixture must actually separate the levels"


def test_optimizing_at_a_deeper_level_lowers_that_levels_cvar(risk_view, rebalance_context):
    """Optimizing for the 99% tail must beat the 95% portfolio at 99%."""
    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)

    at_99 = build(confidence=0.99).allocate(risk_view, rebalance_context)
    at_95 = build(confidence=0.95).allocate(risk_view, rebalance_context)

    cvar99_of_95 = historical_cvar(scenarios.portfolio_returns(at_95.weights), 0.99)
    assert at_99.diagnostics["cvar"] <= cvar99_of_95 + 1e-9


def test_diagnostics_label_the_risk_horizon(risk_view, rebalance_context):
    """The optimized quantity is a 1-day CVaR and must say so."""
    diagnostics = build().allocate(risk_view, rebalance_context).diagnostics
    assert diagnostics["risk_horizon_days"] == 1
    assert diagnostics["scenario_horizon_days"] == 1
    assert diagnostics["cvar_confidence"] == 0.95
    assert diagnostics["n_scenarios"] == LOOKBACK


# ---------------------------------------------------------------------------
# Risk horizon
# ---------------------------------------------------------------------------


def test_default_horizon_uses_daily_scenarios():
    optimizer = CVaROptimizer(lookback_days=LOOKBACK)
    assert optimizer.risk_horizon_days == 1
    assert isinstance(optimizer.scenario_builder, DailyHistoricalScenarios)


def test_a_multi_day_horizon_uses_non_overlapping_compounded_scenarios(
    risk_view, rebalance_context
):
    builder = NonOverlappingHorizonScenarios(5, min_scenarios=10)
    optimizer = CVaROptimizer(
        lookback_days=LOOKBACK, scenario_builder=builder, constraints=ConstraintSet()
    )
    decision = optimizer.allocate(risk_view, rebalance_context)

    assert optimizer.risk_horizon_days == 5
    assert decision.diagnostics["risk_horizon_days"] == 5
    assert decision.diagnostics["scenario_method"] == "historical_non_overlapping"
    assert decision.diagnostics["n_scenarios"] == LOOKBACK // 5
    assert decision.weights.sum() == pytest.approx(1.0, abs=TOL)


def test_a_horizon_with_too_few_scenarios_is_refused(risk_view, rebalance_context):
    """Better to fail than to report a tail measured from a handful of points."""
    optimizer = CVaROptimizer(
        lookback_days=LOOKBACK, risk_horizon_days=21, constraints=ConstraintSet()
    )
    with pytest.raises(InsufficientScenariosError, match="below the minimum"):
        optimizer.allocate(risk_view, rebalance_context)


# ---------------------------------------------------------------------------
# Return target and shortfall
# ---------------------------------------------------------------------------


def test_no_return_target_reports_zero_shortfall(risk_view, rebalance_context):
    diagnostics = build().allocate(risk_view, rebalance_context).diagnostics
    assert diagnostics["return_shortfall"] == 0.0
    assert diagnostics["return_target"] is None


def test_feasible_return_target_produces_zero_shortfall(risk_view, rebalance_context):
    parameters = estimate_parameters(risk_view, LOOKBACK)
    attainable = float(parameters.expected_returns.max()) * 0.5

    decision = build(min_return=attainable).allocate(risk_view, rebalance_context)

    assert decision.diagnostics["return_shortfall"] == 0.0
    assert decision.status == "optimal"
    assert decision.diagnostics["expected_return"] >= attainable - TOL


def test_infeasible_return_target_produces_a_positive_shortfall(
    risk_view, rebalance_context
):
    parameters = estimate_parameters(risk_view, LOOKBACK)
    impossible = float(parameters.expected_returns.max()) + 0.5

    decision = build(min_return=impossible).allocate(risk_view, rebalance_context)

    assert decision.diagnostics["return_shortfall"] > 0
    assert decision.status == "optimal_with_shortfall"


def test_shortfall_matches_the_maximum_attainable_return(risk_view, rebalance_context):
    parameters = estimate_parameters(risk_view, LOOKBACK)
    impossible = float(parameters.expected_returns.max()) + 0.5

    diagnostics = build(max_weight=0.4, min_return=impossible).allocate(
        risk_view, rebalance_context
    ).diagnostics

    assert diagnostics["max_attainable_return"] == pytest.approx(
        impossible - diagnostics["return_shortfall"], abs=1e-7
    )
    assert diagnostics["expected_return"] == pytest.approx(
        diagnostics["max_attainable_return"], abs=1e-6
    )


def test_shortfall_agrees_with_the_markowitz_implementation(risk_view, rebalance_context):
    """Both models share one mechanism, so both must report the same shortfall."""
    from src.portfolio.markowitz import MarkowitzOptimizer

    target = 5.0
    cvar = build(max_weight=0.4, min_return=target).allocate(risk_view, rebalance_context)
    markowitz = MarkowitzOptimizer(
        2.5,
        lookback_days=LOOKBACK,
        asset_class_map=DISTINCT_ASSET_CLASSES,
        constraints=ConstraintSet(max_weight=0.4, min_return=target),
    ).allocate(risk_view, rebalance_context)

    assert cvar.diagnostics["return_shortfall"] == pytest.approx(
        markowitz.diagnostics["return_shortfall"], abs=1e-7
    )


def test_a_return_target_raises_tail_risk(risk_view, rebalance_context):
    """Demanding return should not reduce downside risk; the constraint binds."""
    free = build(max_weight=0.5).allocate(risk_view, rebalance_context)
    constrained = build(max_weight=0.5, min_return=0.05).allocate(
        risk_view, rebalance_context
    )
    assert constrained.diagnostics["cvar"] >= free.diagnostics["cvar"] - 1e-9


# ---------------------------------------------------------------------------
# Look-ahead protection
# ---------------------------------------------------------------------------


def test_cvar_sees_only_the_data_view(risk_prices, rebalance_context):
    as_of = risk_prices.index[1500]
    optimizer = build(max_weight=0.5, min_return=0.02)

    clean = optimizer.allocate(MarketDataView(risk_prices, as_of), rebalance_context)

    poisoned_panel = risk_prices.copy()
    poisoned_panel.loc[poisoned_panel.index > as_of] = 818_181.0
    poisoned = optimizer.allocate(
        MarketDataView(poisoned_panel, as_of), rebalance_context
    )

    pd.testing.assert_series_equal(poisoned.weights, clean.weights)
    assert poisoned.diagnostics["cvar"] == pytest.approx(clean.diagnostics["cvar"])
    assert poisoned.diagnostics["var"] == pytest.approx(clean.diagnostics["var"])


def test_cvar_is_unchanged_when_the_future_is_missing(risk_prices, rebalance_context):
    as_of = risk_prices.index[1500]
    optimizer = build(max_weight=0.5)

    full = optimizer.allocate(MarketDataView(risk_prices, as_of), rebalance_context)
    truncated = optimizer.allocate(
        MarketDataView(risk_prices.loc[risk_prices.index <= as_of], as_of),
        rebalance_context,
    )
    pd.testing.assert_series_equal(truncated.weights, full.weights)


def test_scenario_window_never_crosses_the_decision_date(risk_view, rebalance_context):
    diagnostics = build().allocate(risk_view, rebalance_context).diagnostics
    assert pd.Timestamp(diagnostics["scenario_window_end"]) <= risk_view.as_of


def test_scenario_state_does_not_leak_between_calls(risk_prices, rebalance_context):
    """Scenarios are per-decision; a stale set must never be reused."""
    optimizer = build(max_weight=0.5)
    optimizer.allocate(MarketDataView(risk_prices, risk_prices.index[1500]), rebalance_context)
    assert getattr(optimizer, "_scenarios", None) is None


# ---------------------------------------------------------------------------
# Numerical hygiene
# ---------------------------------------------------------------------------


def test_solving_emits_no_numpy_warnings(risk_view, rebalance_context):
    """Regression: cp.sum over a long vector triggered an intermittent
    'invalid value encountered in reduce' from CVXPY's shape inference, which
    sums uninitialised memory. The objective uses an explicit probability inner
    product instead. See src/portfolio/cvar.py::_minimise_cvar.
    """
    for confidence in (0.90, 0.95, 0.99):
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            build(confidence=confidence, max_weight=0.5).allocate(
                risk_view, rebalance_context
            )


def test_solution_is_finite(risk_view, rebalance_context):
    decision = build(max_weight=0.5, min_return=0.02).allocate(
        risk_view, rebalance_context
    )
    assert np.all(np.isfinite(decision.weights.to_numpy()))
    assert np.isfinite(decision.diagnostics["cvar"])
    assert np.isfinite(decision.diagnostics["var"])
