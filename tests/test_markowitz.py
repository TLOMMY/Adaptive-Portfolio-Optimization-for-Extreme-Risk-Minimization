"""Tests for the Markowitz mean-variance optimizer.

Constraint satisfaction is verified on the *returned* weights rather than
trusted to the solver, and the shortfall mechanism is checked against the exact
identity it is supposed to satisfy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import DISTINCT_ASSET_CLASSES

from src.data.window import MarketDataView
from src.estimation.parameters import estimate_parameters
from src.portfolio.constraints import ConstraintSet
from src.portfolio.markowitz import MarkowitzOptimizer

LOOKBACK = 500
TOL = 1e-6


def build(risk_aversion=2.5, **constraint_kwargs) -> MarkowitzOptimizer:
    return MarkowitzOptimizer(
        risk_aversion=risk_aversion,
        lookback_days=LOOKBACK,
        asset_class_map=DISTINCT_ASSET_CLASSES,
        constraints=ConstraintSet(**constraint_kwargs),
    )


# ---------------------------------------------------------------------------
# Basic solution validity
# ---------------------------------------------------------------------------


def test_weights_sum_to_one(risk_view, rebalance_context):
    decision = build().allocate(risk_view, rebalance_context)
    assert decision.weights.sum() == pytest.approx(1.0, abs=TOL)


def test_no_negative_weights(risk_view, rebalance_context):
    decision = build().allocate(risk_view, rebalance_context)
    assert (decision.weights >= -TOL).all()
    assert (decision.weights >= 0).all(), "cleaning must remove solver noise entirely"


def test_solver_status_is_reported(risk_view, rebalance_context):
    decision = build().allocate(risk_view, rebalance_context)
    assert decision.status == "optimal"
    assert decision.diagnostics["solver"] == "CLARABEL"
    assert decision.diagnostics["solve_seconds"] >= 0


def test_weights_are_labelled_by_ticker(risk_view, rebalance_context):
    decision = build().allocate(risk_view, rebalance_context)
    assert list(decision.weights.index) == risk_view.tickers


def test_negative_risk_aversion_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        MarkowitzOptimizer(risk_aversion=-1.0)


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cap", [0.25, 0.3, 0.5, 0.8])
def test_max_weight_constraint_is_respected(cap, risk_view, rebalance_context):
    decision = build(max_weight=cap).allocate(risk_view, rebalance_context)
    assert decision.weights.max() <= cap + TOL


def test_an_unconstrained_solution_concentrates_more_than_a_capped_one(
    risk_view, rebalance_context
):
    """Confirms the cap actually binds on this fixture, so the test above has force."""
    free = build(max_weight=1.0).allocate(risk_view, rebalance_context)
    capped = build(max_weight=0.3).allocate(risk_view, rebalance_context)
    assert free.weights.max() > capped.weights.max() + 0.05


@pytest.mark.parametrize("limit", [0.2, 0.4, 0.6])
def test_asset_class_constraint_is_respected(limit, risk_view, rebalance_context):
    decision = build(asset_class_limits={"Equity": limit}).allocate(
        risk_view, rebalance_context
    )
    equity = decision.weights[["STOCK", "WILD"]].sum()
    assert equity <= limit + TOL
    assert decision.diagnostics["asset_class_exposure"]["Equity"] == pytest.approx(
        equity, abs=TOL
    )


def test_multiple_asset_class_constraints_hold_simultaneously(risk_view, rebalance_context):
    decision = build(
        asset_class_limits={"Equity": 0.45, "Fixed Income": 0.8}
    ).allocate(risk_view, rebalance_context)
    weights = decision.weights
    assert weights[["STOCK", "WILD"]].sum() <= 0.45 + TOL
    assert weights[["SAFE", "BOND"]].sum() <= 0.80 + TOL


def test_constraints_hold_together_with_a_return_target(risk_view, rebalance_context):
    decision = build(
        max_weight=0.4, asset_class_limits={"Equity": 0.5}, min_return=0.03
    ).allocate(risk_view, rebalance_context)
    weights = decision.weights

    assert weights.sum() == pytest.approx(1.0, abs=TOL)
    assert (weights >= 0).all()
    assert weights.max() <= 0.4 + TOL
    assert weights[["STOCK", "WILD"]].sum() <= 0.5 + TOL


# ---------------------------------------------------------------------------
# Risk aversion drives the trade-off
# ---------------------------------------------------------------------------


def test_higher_risk_aversion_lowers_portfolio_risk(risk_view, rebalance_context):
    """lambda must materially move the solution along the risk-return trade-off."""
    parameters = estimate_parameters(risk_view, LOOKBACK)

    volatilities, returns = [], []
    for lam in (0.5, 2.5, 10.0, 50.0):
        weights = build(risk_aversion=lam).allocate(risk_view, rebalance_context).weights
        volatilities.append(parameters.portfolio_volatility(weights))
        returns.append(parameters.portfolio_return(weights))

    assert volatilities == sorted(volatilities, reverse=True), (
        f"volatility must fall as risk aversion rises, got {volatilities}"
    )
    assert returns == sorted(returns, reverse=True), (
        f"expected return must fall as risk aversion rises, got {returns}"
    )
    # "Materially": not a rounding-level difference.
    assert volatilities[0] - volatilities[-1] > 0.02


def test_very_high_risk_aversion_approaches_minimum_variance(risk_view, rebalance_context):
    """As lambda grows the mean term becomes negligible and only variance matters."""
    parameters = estimate_parameters(risk_view, LOOKBACK)
    weights = build(risk_aversion=10_000.0).allocate(risk_view, rebalance_context).weights

    # SAFE is by construction the lowest-variance asset in this fixture.
    assert weights["SAFE"] > 0.8
    assert parameters.portfolio_volatility(weights) < 0.03


def test_zero_risk_aversion_maximises_expected_return(risk_view, rebalance_context):
    """With lambda = 0 the objective is linear, so the solution is a corner."""
    parameters = estimate_parameters(risk_view, LOOKBACK)
    weights = build(risk_aversion=0.0).allocate(risk_view, rebalance_context).weights

    best_asset = parameters.expected_returns.idxmax()
    assert weights[best_asset] == pytest.approx(1.0, abs=1e-4)


# ---------------------------------------------------------------------------
# Return-target shortfall  (decision D9)
# ---------------------------------------------------------------------------


def test_no_return_target_reports_zero_shortfall(risk_view, rebalance_context):
    decision = build().allocate(risk_view, rebalance_context)
    assert decision.diagnostics["return_shortfall"] == 0.0
    assert decision.diagnostics["return_target"] is None
    assert decision.status == "optimal"


def test_feasible_return_target_produces_zero_shortfall(risk_view, rebalance_context):
    parameters = estimate_parameters(risk_view, LOOKBACK)
    attainable = float(parameters.expected_returns.max()) * 0.5  # comfortably reachable

    decision = build(min_return=attainable).allocate(risk_view, rebalance_context)

    assert decision.diagnostics["return_shortfall"] == 0.0
    assert decision.status == "optimal"
    assert decision.diagnostics["expected_return"] >= attainable - TOL


def test_infeasible_return_target_produces_a_positive_shortfall(
    risk_view, rebalance_context
):
    parameters = estimate_parameters(risk_view, LOOKBACK)
    impossible = float(parameters.expected_returns.max()) + 0.50

    decision = build(min_return=impossible).allocate(risk_view, rebalance_context)

    assert decision.diagnostics["return_shortfall"] > 0
    assert decision.status == "optimal_with_shortfall"


def test_the_return_constraint_is_never_silently_removed(risk_view, rebalance_context):
    """An unattainable target must still bind at the closest attainable value."""
    parameters = estimate_parameters(risk_view, LOOKBACK)
    impossible = float(parameters.expected_returns.max()) + 0.50

    decision = build(min_return=impossible).allocate(risk_view, rebalance_context)
    diagnostics = decision.diagnostics

    # The identity that defines the mechanism.
    assert diagnostics["max_attainable_return"] == pytest.approx(
        impossible - diagnostics["return_shortfall"], abs=1e-7
    )
    assert diagnostics["effective_return_target"] == pytest.approx(
        diagnostics["max_attainable_return"], abs=1e-7
    )
    # The portfolio actually delivers the closest attainable return.
    assert diagnostics["expected_return"] == pytest.approx(
        diagnostics["max_attainable_return"], abs=1e-6
    )


def test_shortfall_is_the_minimum_possible(risk_view, rebalance_context):
    """No feasible portfolio may beat the reported max attainable return."""
    parameters = estimate_parameters(risk_view, LOOKBACK)
    impossible = 1.0

    decision = build(max_weight=0.4, min_return=impossible).allocate(
        risk_view, rebalance_context
    )
    reported_max = decision.diagnostics["max_attainable_return"]

    # Brute force the true maximum under the same box constraints: fill the
    # highest-mean assets up to the cap.
    order = parameters.expected_returns.sort_values(ascending=False)
    remaining, best = 1.0, 0.0
    for _, mu in order.items():
        take = min(0.4, remaining)
        best += take * mu
        remaining -= take
        if remaining <= 0:
            break

    assert reported_max == pytest.approx(best, abs=1e-6)


def test_shortfall_is_expressed_in_annualised_decimal_units(risk_view, rebalance_context):
    """`return_shortfall` must be directly comparable to `return_target`."""
    parameters = estimate_parameters(risk_view, LOOKBACK)
    target = float(parameters.expected_returns.max()) + 0.25

    diagnostics = build(min_return=target).allocate(risk_view, rebalance_context).diagnostics

    shortfall = diagnostics["return_shortfall"]
    assert 0 < shortfall < 1.0  # a decimal, not a percentage
    assert diagnostics["return_target"] - shortfall == pytest.approx(
        diagnostics["effective_return_target"], abs=1e-9
    )


def test_a_target_at_exactly_the_maximum_is_feasible(risk_view, rebalance_context):
    parameters = estimate_parameters(risk_view, LOOKBACK)
    exact_max = float(parameters.expected_returns.max())

    decision = build(max_weight=1.0, min_return=exact_max).allocate(
        risk_view, rebalance_context
    )
    assert decision.diagnostics["return_shortfall"] == pytest.approx(0.0, abs=1e-7)


# ---------------------------------------------------------------------------
# Information boundary
# ---------------------------------------------------------------------------


def test_markowitz_sees_only_the_data_view(risk_prices, rebalance_context):
    """Corrupting the future must not change the optimizer's weights."""
    as_of = risk_prices.index[1500]
    optimizer = build(max_weight=0.5, min_return=0.02)

    clean = optimizer.allocate(MarketDataView(risk_prices, as_of), rebalance_context)

    poisoned_panel = risk_prices.copy()
    poisoned_panel.loc[poisoned_panel.index > as_of] = 777_777.0
    poisoned = optimizer.allocate(
        MarketDataView(poisoned_panel, as_of), rebalance_context
    )

    pd.testing.assert_series_equal(poisoned.weights, clean.weights)
    assert poisoned.diagnostics["return_shortfall"] == clean.diagnostics["return_shortfall"]


def test_markowitz_reports_the_window_it_used(risk_view, rebalance_context):
    diagnostics = build().allocate(risk_view, rebalance_context).diagnostics
    assert diagnostics["n_observations"] == LOOKBACK
    assert pd.Timestamp(diagnostics["window_end"]) <= risk_view.as_of


def test_optimizer_is_deterministic(risk_view, rebalance_context):
    optimizer = build(max_weight=0.4, min_return=0.02)
    first = optimizer.allocate(risk_view, rebalance_context)
    second = optimizer.allocate(risk_view, rebalance_context)
    pd.testing.assert_series_equal(first.weights, second.weights)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_reported_moments_match_the_estimated_parameters(risk_view, rebalance_context):
    parameters = estimate_parameters(risk_view, LOOKBACK)
    decision = build(max_weight=0.5).allocate(risk_view, rebalance_context)

    assert decision.diagnostics["expected_return"] == pytest.approx(
        parameters.portfolio_return(decision.weights)
    )
    assert decision.diagnostics["expected_volatility"] == pytest.approx(
        parameters.portfolio_volatility(decision.weights)
    )


def test_diagnostics_record_the_estimators_and_risk_aversion(risk_view, rebalance_context):
    diagnostics = build(risk_aversion=7.5).allocate(risk_view, rebalance_context).diagnostics
    assert diagnostics["risk_aversion"] == 7.5
    assert diagnostics["mu_estimator"] == "sample_mean"
    assert diagnostics["covariance_estimator"] == "ledoit_wolf"


def test_weights_are_cleaned_of_solver_noise(risk_view, rebalance_context):
    """Zero positions must be exactly zero, not 1e-17."""
    weights = build(risk_aversion=10_000.0).allocate(risk_view, rebalance_context).weights
    tiny = weights[(weights.abs() > 0) & (weights.abs() < 1e-9)]
    assert tiny.empty
    assert np.all((weights.to_numpy() == 0) | (weights.to_numpy() > 1e-9))
