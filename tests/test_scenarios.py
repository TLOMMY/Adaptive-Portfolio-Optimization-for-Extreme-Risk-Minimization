"""Tests for return-scenario construction.

Scenario construction is the point where a tail measure acquires its empirical
content, so it gets the same boundary scrutiny as parameter estimation: a
scenario set built at date t must be a function of data up to t and nothing else.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import make_distinct_risk_prices

from src.data.window import MarketDataView
from src.estimation.scenarios import (
    MIN_SCENARIOS,
    DailyHistoricalScenarios,
    InsufficientScenariosError,
    NonOverlappingHorizonScenarios,
    build_scenario_builder,
)

LOOKBACK = 500


# ---------------------------------------------------------------------------
# Daily scenarios (the MVP construction)
# ---------------------------------------------------------------------------


def test_daily_builder_makes_one_scenario_per_observation(risk_view):
    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)
    assert scenarios.n_scenarios == LOOKBACK
    assert scenarios.horizon_days == 1
    assert scenarios.method == "historical_daily"


def test_daily_scenarios_are_exactly_the_window_returns(risk_view):
    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)
    expected = risk_view.returns(LOOKBACK)

    assert np.allclose(scenarios.returns, expected.to_numpy())
    assert scenarios.tickers == list(expected.columns)


def test_scenarios_are_equiprobable(risk_view):
    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)
    probabilities = scenarios.probabilities
    assert probabilities.sum() == pytest.approx(1.0)
    assert np.allclose(probabilities, 1.0 / LOOKBACK)


def test_scenarios_store_returns_not_losses(risk_view):
    """Sign convention: stored values are returns; losses are derived."""
    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)
    weights = pd.Series(0.25, index=scenarios.tickers)

    returns = scenarios.portfolio_returns(weights)
    losses = scenarios.portfolio_losses(weights)
    assert np.allclose(losses, -returns)


def test_portfolio_returns_match_matrix_algebra(risk_view):
    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)
    weights = np.array([0.4, 0.3, 0.2, 0.1])
    assert np.allclose(scenarios.portfolio_returns(weights), scenarios.returns @ weights)


def test_wrong_weight_length_is_rejected(risk_view):
    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)
    with pytest.raises(ValueError, match="expected 4 weights"):
        scenarios.portfolio_returns(np.array([0.5, 0.5]))


def test_summary_records_the_construction(risk_view):
    summary = DailyHistoricalScenarios().build(risk_view, LOOKBACK).summary()
    assert summary["n_scenarios"] == LOOKBACK
    assert summary["scenario_method"] == "historical_daily"
    assert summary["scenario_horizon_days"] == 1


# ---------------------------------------------------------------------------
# The minimum-scenario guard
# ---------------------------------------------------------------------------


def test_too_few_scenarios_is_rejected(risk_view):
    with pytest.raises(InsufficientScenariosError, match="below the minimum"):
        DailyHistoricalScenarios().build(risk_view, 50)


def test_the_guard_threshold_is_configurable(risk_view):
    scenarios = DailyHistoricalScenarios(min_scenarios=10).build(risk_view, 50)
    assert scenarios.n_scenarios == 50


def test_default_lookback_clears_the_guard(risk_view):
    assert LOOKBACK >= MIN_SCENARIOS
    DailyHistoricalScenarios().build(risk_view, LOOKBACK)


# ---------------------------------------------------------------------------
# Multi-day horizons
# ---------------------------------------------------------------------------


def test_non_overlapping_blocks_compound_correctly(risk_view):
    """Each scenario is the compounded return of a block of consecutive days."""
    horizon = 5
    builder = NonOverlappingHorizonScenarios(horizon, min_scenarios=10)
    scenarios = builder.build(risk_view, LOOKBACK)

    assert scenarios.n_scenarios == LOOKBACK // horizon
    assert scenarios.horizon_days == horizon
    assert scenarios.method == "historical_non_overlapping"

    window = risk_view.returns(LOOKBACK)
    first_block = window.iloc[:horizon]["SAFE"]
    expected = float((1.0 + first_block).prod() - 1.0)
    assert scenarios.returns[0, scenarios.tickers.index("SAFE")] == pytest.approx(expected)


def test_non_overlapping_blocks_do_not_overlap(risk_view):
    """Consecutive scenarios must be built from disjoint observations."""
    horizon = 10
    builder = NonOverlappingHorizonScenarios(horizon, min_scenarios=10)
    scenarios = builder.build(risk_view, LOOKBACK)
    window = risk_view.returns(LOOKBACK)

    for block_index in (0, 1, 7):
        block = window.iloc[block_index * horizon : (block_index + 1) * horizon]
        expected = (1.0 + block).prod() - 1.0
        assert np.allclose(scenarios.returns[block_index], expected.to_numpy())


def test_multi_day_blocks_align_to_the_most_recent_data(risk_view):
    """A remainder is dropped from the oldest end, never the newest."""
    horizon = 7  # 500 is not divisible by 7
    builder = NonOverlappingHorizonScenarios(horizon, min_scenarios=10)
    scenarios = builder.build(risk_view, LOOKBACK)

    window = risk_view.returns(LOOKBACK)
    n_blocks = LOOKBACK // horizon
    assert scenarios.n_scenarios == n_blocks
    assert scenarios.window_end == window.index[-1]
    assert scenarios.window_start == window.index[LOOKBACK - n_blocks * horizon]


def test_a_monthly_horizon_on_a_three_year_lookback_trips_the_guard(risk_view):
    """756/21 = 36 scenarios is far too few for a 95% tail; the guard must fire."""
    builder = NonOverlappingHorizonScenarios(21)
    with pytest.raises(InsufficientScenariosError, match="below the minimum"):
        builder.build(risk_view, 756 if risk_view.n_observations > 757 else LOOKBACK)


def test_a_horizon_longer_than_the_window_is_rejected(risk_view):
    builder = NonOverlappingHorizonScenarios(600, min_scenarios=1)
    with pytest.raises(InsufficientScenariosError, match="cannot fill a single"):
        builder.build(risk_view, LOOKBACK)


def test_invalid_horizon_is_rejected():
    with pytest.raises(ValueError, match="horizon_days must be >= 1"):
        NonOverlappingHorizonScenarios(0)


def test_factory_selects_the_builder_for_the_horizon():
    assert isinstance(build_scenario_builder(1), DailyHistoricalScenarios)
    assert isinstance(build_scenario_builder(5), NonOverlappingHorizonScenarios)
    assert build_scenario_builder(5).horizon_days == 5


# ---------------------------------------------------------------------------
# Look-ahead protection
# ---------------------------------------------------------------------------


def test_scenarios_never_include_a_post_decision_observation(risk_prices):
    as_of = risk_prices.index[1500]
    scenarios = DailyHistoricalScenarios().build(
        MarketDataView(risk_prices, as_of), LOOKBACK
    )
    assert scenarios.window_end <= as_of
    assert scenarios.as_of == as_of


def test_scenarios_are_unchanged_when_the_future_is_poisoned(risk_prices):
    as_of = risk_prices.index[1500]
    builder = DailyHistoricalScenarios()

    clean = builder.build(MarketDataView(risk_prices, as_of), LOOKBACK)

    poisoned_panel = risk_prices.copy()
    poisoned_panel.loc[poisoned_panel.index > as_of] = 313_131.0
    poisoned = builder.build(MarketDataView(poisoned_panel, as_of), LOOKBACK)

    assert np.array_equal(poisoned.returns, clean.returns)
    assert poisoned.window_end == clean.window_end


def test_scenarios_are_unchanged_when_the_future_is_missing(risk_prices):
    as_of = risk_prices.index[1500]
    builder = DailyHistoricalScenarios()

    full = builder.build(MarketDataView(risk_prices, as_of), LOOKBACK)
    truncated = builder.build(
        MarketDataView(risk_prices.loc[risk_prices.index <= as_of], as_of), LOOKBACK
    )
    assert np.array_equal(truncated.returns, full.returns)


def test_multi_day_scenarios_also_respect_the_boundary(risk_prices):
    as_of = risk_prices.index[1500]
    builder = NonOverlappingHorizonScenarios(5, min_scenarios=10)

    clean = builder.build(MarketDataView(risk_prices, as_of), LOOKBACK)
    poisoned_panel = risk_prices.copy()
    poisoned_panel.loc[poisoned_panel.index > as_of] = 313_131.0
    poisoned = builder.build(MarketDataView(poisoned_panel, as_of), LOOKBACK)

    assert np.array_equal(poisoned.returns, clean.returns)
    assert clean.window_end <= as_of


def test_builder_accepts_only_a_view_not_a_panel(risk_prices):
    """The builder's input type is what makes leakage impossible."""
    with pytest.raises(AttributeError):
        DailyHistoricalScenarios().build(risk_prices, LOOKBACK)  # type: ignore[arg-type]


def test_scenario_matrix_is_finite(risk_view):
    """Non-finite scenario data would silently corrupt the LP."""
    scenarios = DailyHistoricalScenarios().build(risk_view, LOOKBACK)
    assert np.all(np.isfinite(scenarios.returns))


def test_scenarios_from_a_gapped_panel_are_still_finite():
    panel = make_distinct_risk_prices(n_days=800)
    gapped = panel.copy()
    gapped.iloc[300, 1] = np.nan  # an interior gap, forward-filled by the view

    scenarios = DailyHistoricalScenarios().build(
        MarketDataView(gapped, gapped.index[700]), LOOKBACK
    )
    assert np.all(np.isfinite(scenarios.returns))
