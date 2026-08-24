"""Tests for the historical replay engine.

Correctness here is checked against *analytically known* answers wherever
possible -- a buy-and-hold single asset must track its own price exactly, an
equal-weight portfolio's first-day return must equal the mean asset return --
rather than against previously recorded engine output.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import FixedWeightStrategy, UniformStrategy, make_prices

from src.backtest.engine import BacktestConfigurationError, BacktestEngine
from src.backtest.strategy import AllocationDecision
from src.config.settings import BacktestSettings, RebalanceFrequency


@pytest.fixture
def engine_settings() -> BacktestSettings:
    return BacktestSettings(
        start=pd.Timestamp("2016-01-01").date(),
        end=pd.Timestamp("2018-12-31").date(),
        lookback_years=1.0,
        rebalance_frequency=RebalanceFrequency.QUARTERLY,
        initial_capital=100_000.0,
        transaction_cost_bps=0.0,
    )


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


def test_backtest_starts_on_the_first_decision_date(prices, engine_settings):
    engine = BacktestEngine(prices, engine_settings)
    result = engine.run({"uniform": UniformStrategy()})["uniform"]
    assert result.start_date == engine.rebalance_dates[0]
    assert result.start_date >= pd.Timestamp(engine_settings.start)


def test_backtest_ends_on_the_last_trading_day_within_the_window(prices, engine_settings):
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    end = pd.Timestamp(engine_settings.end)
    expected_last = prices.index[prices.index <= end][-1]
    assert result.end_date == expected_last


def test_backtest_never_records_a_value_outside_its_window(prices, engine_settings):
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    assert result.portfolio_values.index.min() >= pd.Timestamp(engine_settings.start)
    assert result.portfolio_values.index.max() <= pd.Timestamp(engine_settings.end)


def test_rebalance_count_matches_the_frequency(prices):
    for frequency, expected in [
        (RebalanceFrequency.QUARTERLY, 12),
        (RebalanceFrequency.ANNUAL, 3),
    ]:
        settings = BacktestSettings(
            start=pd.Timestamp("2016-01-01").date(),
            end=pd.Timestamp("2018-12-31").date(),
            lookback_years=1.0,
            rebalance_frequency=frequency,
        )
        engine = BacktestEngine(prices, settings)
        assert len(engine.rebalance_dates) == expected
        result = engine.run({"uniform": UniformStrategy()})["uniform"]
        assert len(result.weights_history) == expected


def test_value_index_has_no_duplicates_or_gaps(prices, engine_settings):
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    assert not result.portfolio_values.index.has_duplicates
    assert result.portfolio_values.index.is_monotonic_increasing

    expected_days = prices.index[
        (prices.index >= result.start_date) & (prices.index <= result.end_date)
    ]
    assert len(result.portfolio_values) == len(expected_days)


# ---------------------------------------------------------------------------
# Value arithmetic against known answers
# ---------------------------------------------------------------------------


def test_single_asset_portfolio_tracks_that_asset_exactly(prices, engine_settings):
    """A 100%-in-AAA portfolio must reproduce AAA's own price path."""
    weights = pd.Series([1.0, 0.0, 0.0, 0.0], index=prices.columns)
    result = BacktestEngine(prices, engine_settings).run(
        {"all_in": FixedWeightStrategy(weights, name="all_in")}
    )["all_in"]

    start, end = result.start_date, result.end_date
    expected_ratio = prices.loc[end, "AAA"] / prices.loc[start, "AAA"]
    actual_ratio = result.portfolio_values.iloc[-1] / result.portfolio_values.iloc[0]

    assert actual_ratio == pytest.approx(expected_ratio, rel=1e-10)


def test_portfolio_starts_at_the_configured_capital(prices, engine_settings):
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    assert result.portfolio_values.iloc[0] == pytest.approx(engine_settings.initial_capital)


def test_first_day_return_equals_the_mean_asset_return(prices, engine_settings):
    """With equal weights, day one's portfolio return is the cross-sectional mean."""
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    decision_date = result.start_date
    first_day = prices.index[prices.index > decision_date][0]

    asset_returns = prices.loc[first_day] / prices.loc[decision_date] - 1.0
    expected = float(asset_returns.mean())

    assert result.daily_returns.loc[first_day] == pytest.approx(expected, rel=1e-10)


def test_weights_drift_between_rebalances(prices, engine_settings):
    """Positions must move with the market, not be silently held at target."""
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    later = result.rebalances[3]
    assert not np.allclose(later.weights_before.to_numpy(), 0.25), (
        "drifted weights are exactly equal-weight, which means drift was not applied"
    )
    assert later.weights_before.sum() == pytest.approx(1.0)


def test_drifted_weights_match_a_hand_computed_value(prices, engine_settings):
    """Verify drift arithmetic explicitly over the first holding period."""
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    t0 = result.rebalances[0].as_of
    t1 = result.rebalances[1].as_of

    growth = prices.loc[t1] / prices.loc[t0]
    expected = (0.25 * growth) / (0.25 * growth).sum()

    pd.testing.assert_series_equal(
        result.rebalances[1].weights_before, expected, check_names=False, rtol=1e-10
    )


# ---------------------------------------------------------------------------
# Turnover and costs
# ---------------------------------------------------------------------------


def test_initial_rebalance_trades_the_whole_portfolio(prices, engine_settings):
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    first = result.rebalances[0]
    assert first.weights_before.sum() == pytest.approx(0.0)
    assert first.traded_fraction == pytest.approx(1.0)
    assert first.turnover == pytest.approx(0.5)


def test_turnover_is_half_the_absolute_weight_change(prices, engine_settings):
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    for record in result.rebalances[1:]:
        expected = 0.5 * float((record.weights_after - record.weights_before).abs().sum())
        assert record.turnover == pytest.approx(expected)
        assert record.traded_fraction == pytest.approx(2 * expected)


def test_a_never_changing_portfolio_still_has_turnover_from_drift(prices, engine_settings):
    """Rebalancing back to a fixed target is itself trading."""
    weights = pd.Series(0.25, index=prices.columns)
    result = BacktestEngine(prices, engine_settings).run(
        {"fixed": FixedWeightStrategy(weights, name="fixed")}
    )["fixed"]
    later_turnover = [r.turnover for r in result.rebalances[1:]]
    assert all(t > 0 for t in later_turnover)
    assert result.average_turnover() > 0


def test_zero_cost_baseline_charges_nothing(prices, engine_settings):
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    assert result.total_cost == 0.0
    assert all(r.cost == 0.0 for r in result.rebalances)


def test_transaction_costs_reduce_the_final_value(prices, engine_settings):
    free = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    costly_settings = BacktestSettings(
        start=engine_settings.start,
        end=engine_settings.end,
        lookback_years=engine_settings.lookback_years,
        rebalance_frequency=engine_settings.rebalance_frequency,
        initial_capital=engine_settings.initial_capital,
        transaction_cost_bps=25.0,
    )
    costly = BacktestEngine(prices, costly_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]

    assert costly.total_cost > 0
    assert costly.portfolio_values.iloc[-1] < free.portfolio_values.iloc[-1]
    # Weights are unaffected: cost changes the value path, not the decisions.
    pd.testing.assert_frame_equal(costly.weights_history, free.weights_history)


def test_initial_cost_matches_a_hand_computed_charge(prices):
    settings = BacktestSettings(
        start=pd.Timestamp("2016-01-01").date(),
        end=pd.Timestamp("2016-12-31").date(),
        lookback_years=1.0,
        initial_capital=100_000.0,
        transaction_cost_bps=10.0,
    )
    result = BacktestEngine(prices, settings).run({"uniform": UniformStrategy()})["uniform"]
    # Establishing the position trades 100% of notional at 10bps.
    assert result.rebalances[0].cost == pytest.approx(100_000.0 * 10.0 / 10_000.0)


# ---------------------------------------------------------------------------
# Multi-strategy runs
# ---------------------------------------------------------------------------


def test_strategies_run_over_identical_dates(prices, engine_settings):
    experiment = BacktestEngine(prices, engine_settings).run(
        {
            "uniform": UniformStrategy(),
            "fixed": FixedWeightStrategy(
                pd.Series([0.4, 0.3, 0.2, 0.1], index=prices.columns), name="fixed"
            ),
        }
    )
    assert set(experiment.strategy_names) == {"uniform", "fixed"}
    values = experiment.value_frame()
    assert not values.isna().any().any()
    assert list(experiment["uniform"].weights_history.index) == list(
        experiment["fixed"].weights_history.index
    )


def test_running_one_strategy_alone_matches_running_it_alongside_others(
    prices, engine_settings
):
    """Strategies must not influence one another through shared engine state."""
    alone = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    together = BacktestEngine(prices, engine_settings).run(
        {
            "uniform": UniformStrategy(),
            "other": FixedWeightStrategy(
                pd.Series([1.0, 0.0, 0.0, 0.0], index=prices.columns), name="other"
            ),
        }
    )["uniform"]

    pd.testing.assert_series_equal(alone.portfolio_values, together.portfolio_values)


def test_results_are_deterministic(prices, engine_settings):
    a = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})["uniform"]
    b = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})["uniform"]
    pd.testing.assert_series_equal(a.portfolio_values, b.portfolio_values)


# ---------------------------------------------------------------------------
# Weight validity and failure handling
# ---------------------------------------------------------------------------


def test_recorded_weights_sum_to_one_and_are_non_negative(prices, engine_settings):
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    sums = result.weights_history.sum(axis=1)
    assert np.allclose(sums.to_numpy(), 1.0)
    assert (result.weights_history.to_numpy() >= -1e-12).all()


def test_malformed_weights_are_rejected(prices, engine_settings):
    class BadStrategy:
        name = "bad"

        def allocate(self, view, context):
            w = pd.Series(0.1, index=view.tickers)  # sums to 0.4, not 1.0
            return AllocationDecision(weights=w)

    result = BacktestEngine(prices, engine_settings).run({"bad": BadStrategy()})["bad"]
    # The engine must not accept it silently; the failure is recorded as status.
    assert all(r.status.startswith("error") for r in result.rebalances)


def test_a_failing_strategy_is_recorded_not_hidden(prices, engine_settings):
    class ExplodingStrategy:
        name = "boom"

        def allocate(self, view, context):
            raise RuntimeError("solver exploded")

    result = BacktestEngine(prices, engine_settings).run({"boom": ExplodingStrategy()})["boom"]
    assert all("error" in r.status for r in result.rebalances)
    assert any("solver exploded" in str(r.diagnostics.get("error", "")) for r in result.rebalances)


# ---------------------------------------------------------------------------
# Configuration errors
# ---------------------------------------------------------------------------


def test_empty_panel_is_rejected():
    with pytest.raises(BacktestConfigurationError, match="empty"):
        BacktestEngine(pd.DataFrame(index=pd.DatetimeIndex([])), BacktestSettings())


def test_insufficient_history_before_the_first_decision_is_rejected():
    panel = make_prices(n_days=80, start="2015-11-02")
    settings = BacktestSettings(
        start=pd.Timestamp("2015-12-01").date(),
        end=pd.Timestamp("2016-02-01").date(),
        lookback_years=1.0,
    )
    with pytest.raises(BacktestConfigurationError, match="observations exist"):
        BacktestEngine(panel, settings)


def test_window_with_no_trading_days_is_rejected(prices):
    settings = BacktestSettings(
        start=pd.Timestamp("2030-01-01").date(),
        end=pd.Timestamp("2031-01-01").date(),
        lookback_years=1.0,
    )
    with pytest.raises(BacktestConfigurationError, match="no trading days"):
        BacktestEngine(prices, settings)


def test_running_without_strategies_is_rejected(prices, engine_settings):
    with pytest.raises(ValueError, match="at least one strategy"):
        BacktestEngine(prices, engine_settings).run({})


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def test_diagnostics_frame_exposes_the_audit_trail(prices, engine_settings):
    result = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    frame = result.diagnostics_frame()
    assert len(frame) == len(result.rebalances)
    for column in ("as_of", "status", "turnover", "data_last_date", "n_observations_used"):
        assert column in frame.columns
    assert (frame["data_last_date"] <= frame["as_of"]).all()


def test_settings_summary_is_recorded_with_results(prices, engine_settings):
    experiment = BacktestEngine(prices, engine_settings).run({"uniform": UniformStrategy()})
    summary = experiment.settings_summary
    assert summary["rebalance_frequency"] == "quarterly"
    assert summary["cutoff"] == "inclusive"
    assert summary["transaction_cost_bps"] == 0.0
    assert summary["n_rebalances"] == len(experiment.rebalance_dates)
