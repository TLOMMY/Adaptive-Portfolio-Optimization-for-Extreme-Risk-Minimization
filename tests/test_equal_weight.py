"""Tests for the equal-weight benchmark.

Correctness for 1/N is exactly checkable, so it is checked exactly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import DISTINCT_ASSET_CLASSES

from src.portfolio.constraints import ConstraintError, ConstraintSet
from src.portfolio.equal_weight import EqualWeightOptimizer

LOOKBACK = 500


def test_every_weight_is_exactly_one_over_n(risk_view, rebalance_context):
    optimizer = EqualWeightOptimizer(lookback_days=LOOKBACK)
    decision = optimizer.allocate(risk_view, rebalance_context)

    n = len(risk_view.tickers)
    assert np.allclose(decision.weights.to_numpy(), 1.0 / n)
    assert decision.weights.sum() == pytest.approx(1.0)
    assert list(decision.weights.index) == risk_view.tickers


def test_weights_do_not_depend_on_estimated_parameters(risk_prices, rebalance_context):
    """1/N is immune to estimation error; that is the point of the benchmark."""
    from src.data.window import MarketDataView

    optimizer = EqualWeightOptimizer(lookback_days=LOOKBACK)
    as_of = risk_prices.index[1500]

    normal = optimizer.allocate(MarketDataView(risk_prices, as_of), rebalance_context)

    scaled = risk_prices.copy()
    scaled["WILD"] = scaled["WILD"] * 3.0  # different level, different estimates
    shifted = optimizer.allocate(MarketDataView(scaled, as_of), rebalance_context)

    pd.testing.assert_series_equal(normal.weights, shifted.weights)


def test_status_reports_that_no_solver_ran(risk_view, rebalance_context):
    decision = EqualWeightOptimizer(lookback_days=LOOKBACK).allocate(
        risk_view, rebalance_context
    )
    assert decision.status == "analytic"
    assert decision.diagnostics["solver"] == "none"
    assert decision.diagnostics["n_assets"] == len(risk_view.tickers)


def test_expected_moments_are_still_reported(risk_view, rebalance_context):
    """The benchmark ignores parameters when choosing, but still reports them."""
    decision = EqualWeightOptimizer(lookback_days=LOOKBACK).allocate(
        risk_view, rebalance_context
    )
    assert "expected_return" in decision.diagnostics
    assert decision.diagnostics["expected_volatility"] > 0


def test_a_cap_below_one_over_n_is_an_error_not_a_violation(risk_view, rebalance_context):
    optimizer = EqualWeightOptimizer(
        lookback_days=LOOKBACK, constraints=ConstraintSet(max_weight=0.2)
    )
    with pytest.raises(ConstraintError, match="cannot sum to 1"):
        optimizer.allocate(risk_view, rebalance_context)


def test_an_incompatible_asset_class_limit_is_an_error(risk_view, rebalance_context):
    """1/N puts 50% in equity here; a 30% cap cannot be silently satisfied."""
    optimizer = EqualWeightOptimizer(
        lookback_days=LOOKBACK,
        asset_class_map=DISTINCT_ASSET_CLASSES,
        constraints=ConstraintSet(asset_class_limits={"Equity": 0.3}),
    )
    with pytest.raises(ConstraintError, match="asset class"):
        optimizer.allocate(risk_view, rebalance_context)


def test_a_satisfiable_asset_class_limit_is_accepted(risk_view, rebalance_context):
    optimizer = EqualWeightOptimizer(
        lookback_days=LOOKBACK,
        asset_class_map=DISTINCT_ASSET_CLASSES,
        constraints=ConstraintSet(asset_class_limits={"Equity": 0.5}),
    )
    decision = optimizer.allocate(risk_view, rebalance_context)
    assert decision.diagnostics["asset_class_exposure"]["Equity"] == pytest.approx(0.5)


def test_equal_weight_is_stable_across_decision_dates(risk_prices, rebalance_context):
    from src.data.window import MarketDataView

    optimizer = EqualWeightOptimizer(lookback_days=LOOKBACK)
    first = optimizer.allocate(MarketDataView(risk_prices, risk_prices.index[1200]), rebalance_context)
    later = optimizer.allocate(MarketDataView(risk_prices, risk_prices.index[1800]), rebalance_context)
    pd.testing.assert_series_equal(first.weights, later.weights)
