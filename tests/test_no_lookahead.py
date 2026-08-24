"""Proofs that no decision in this project uses information from after its date.

The tests here are the project's central methodological claim, so they are
written to *falsify* the claim rather than to illustrate it. The key design is
the poisoned-future test: history after a decision date is replaced with data
that bears no relation to the truth, and the decisions taken at or before that
date must come out bit-identical. If any estimator or optimizer reached past the
boundary, the corrupted values would propagate and the comparison would fail.

A strategy that ignores its inputs would pass such a test vacuously, so the
data-dependent ``TrailingMomentumStrategy`` is used throughout: its weights are
a function of the estimation window's contents.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import (
    RecordingStrategy,
    TrailingMomentumStrategy,
    UniformStrategy,
    make_prices,
)

from src.backtest.engine import BacktestEngine
from src.config.settings import BacktestSettings, DataCutoff, RebalanceFrequency
from src.data.window import LookAheadError, MarketDataView

POISON_VALUE = 987_654.0


def poison_after(prices: pd.DataFrame, boundary: pd.Timestamp, value: float = POISON_VALUE):
    """Replace every observation strictly after ``boundary`` with a constant.

    The replacement is a valid price (positive, finite) so it passes every data
    check and can only be caught by the invariance assertion itself.
    """
    poisoned = prices.copy()
    poisoned.loc[poisoned.index > boundary] = value
    return poisoned


@pytest.fixture
def experiment_settings() -> BacktestSettings:
    return BacktestSettings(
        start=pd.Timestamp("2016-01-01").date(),
        end=pd.Timestamp("2018-12-31").date(),
        lookback_years=1.0,
        rebalance_frequency=RebalanceFrequency.QUARTERLY,
        transaction_cost_bps=0.0,
    )


# ---------------------------------------------------------------------------
# The flagship test
# ---------------------------------------------------------------------------


def test_decisions_are_identical_when_the_future_is_poisoned(prices, experiment_settings):
    """For every decision date t, corrupting all data after t must change nothing
    about the decisions taken at or before t."""
    reference = BacktestEngine(prices, experiment_settings).run(
        {"momentum": TrailingMomentumStrategy(lookback=120)}
    )["momentum"]

    assert len(reference.weights_history) >= 8, "experiment too short to be meaningful"

    for boundary in reference.weights_history.index:
        poisoned_run = BacktestEngine(
            poison_after(prices, boundary), experiment_settings
        ).run({"momentum": TrailingMomentumStrategy(lookback=120)})["momentum"]

        unaffected = reference.weights_history.loc[:boundary]
        observed = poisoned_run.weights_history.loc[:boundary]

        pd.testing.assert_frame_equal(
            observed,
            unaffected,
            obj=f"weights at or before {boundary.date()} with future poisoned",
        )


def test_decisions_are_identical_when_the_future_is_missing(prices, experiment_settings):
    """Truncating the panel at a decision date must not change decisions up to it.

    Complements the poison test: poisoning proves future values are not *read*;
    truncation proves the code does not silently depend on their *existence*.
    """
    full = BacktestEngine(prices, experiment_settings).run(
        {"momentum": TrailingMomentumStrategy(lookback=120)}
    )["momentum"]

    # Skip the first decision date: truncating there would leave an experiment
    # whose end coincides with its start, which is not a valid configuration.
    for boundary in full.weights_history.index[1:7]:
        truncated_prices = prices.loc[prices.index <= boundary]
        truncated_settings = BacktestSettings(
            start=experiment_settings.start,
            end=boundary.date(),
            lookback_years=experiment_settings.lookback_years,
            rebalance_frequency=experiment_settings.rebalance_frequency,
            transaction_cost_bps=0.0,
        )
        truncated = BacktestEngine(truncated_prices, truncated_settings).run(
            {"momentum": TrailingMomentumStrategy(lookback=120)}
        )["momentum"]

        pd.testing.assert_frame_equal(
            truncated.weights_history,
            full.weights_history.loc[: truncated.weights_history.index[-1]],
            obj=f"weights with panel truncated at {boundary.date()}",
        )


# ---------------------------------------------------------------------------
# Boundary invariants observed from inside a running backtest
# ---------------------------------------------------------------------------


def test_no_strategy_ever_observes_data_past_its_decision_date(prices, experiment_settings):
    strategy = RecordingStrategy()
    BacktestEngine(prices, experiment_settings).run({"recording": strategy})

    assert strategy.seen, "strategy was never called"
    for record in strategy.seen:
        assert record["max_visible_date"] <= record["as_of"], (
            f"view anchored at {record['as_of'].date()} exposed "
            f"{record['max_visible_date'].date()}"
        )


def test_recorded_data_boundary_matches_decision_date(prices, experiment_settings):
    """The audit trail written into the results must itself show no leakage."""
    result = BacktestEngine(prices, experiment_settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    for record in result.rebalances:
        assert record.data_last_date is not None
        assert record.data_last_date <= record.as_of


def test_realised_returns_begin_strictly_after_the_decision_date(prices, experiment_settings):
    """A portfolio must not be credited with the return of the day it was formed."""
    engine = BacktestEngine(prices, experiment_settings)
    for i, decision_date in enumerate(engine.rebalance_dates):
        final_day = engine._prices.index[engine._prices.index <= pd.Timestamp(experiment_settings.end)][-1]
        window = engine._period_returns(decision_date, i, final_day)
        if window is None:
            continue
        assert window.index.min() > decision_date, (
            f"holding period for {decision_date.date()} starts on "
            f"{window.index.min().date()}, which is not strictly after it"
        )


# ---------------------------------------------------------------------------
# The firewall itself
# ---------------------------------------------------------------------------


def test_view_excludes_all_future_observations(prices):
    as_of = pd.Timestamp("2016-06-15")
    view = MarketDataView(prices, as_of)
    assert view.prices().index.max() <= as_of
    assert view.returns(30).index.max() <= as_of
    view.assert_within_boundary()


def test_exclusive_cutoff_excludes_the_decision_date_itself(prices):
    as_of = prices.index[500]
    inclusive = MarketDataView(prices, as_of, cutoff=DataCutoff.INCLUSIVE)
    exclusive = MarketDataView(prices, as_of, cutoff=DataCutoff.EXCLUSIVE)

    assert inclusive.last_date == as_of
    assert exclusive.last_date < as_of
    assert exclusive.n_observations == inclusive.n_observations - 1
    exclusive.assert_within_boundary()


def test_view_does_not_retain_a_reference_to_the_full_panel(prices):
    """Mutating the source panel after construction must not affect the view.

    This is the structural guarantee: the view owns a slice, not a window onto
    someone else's data.
    """
    view = MarketDataView(prices, pd.Timestamp("2016-06-15"))
    before = view.prices()

    mutated = prices  # same object the caller holds
    mutated.iloc[:, :] = 1.0

    pd.testing.assert_frame_equal(view.prices(), before)


def test_view_returned_frames_are_copies(prices):
    view = MarketDataView(prices, pd.Timestamp("2016-06-15"))
    snapshot = view.prices()
    snapshot.iloc[0, 0] = -12345.0
    assert view.prices().iloc[0, 0] != -12345.0


def test_assert_within_boundary_detects_a_violation(prices):
    """The self-check must actually fire when the invariant is broken."""
    view = MarketDataView(prices, pd.Timestamp("2016-06-15"))
    # Reach past the public API to simulate a defect that bypassed construction.
    tampered = view.prices()
    future_row = prices.loc[[pd.Timestamp("2016-06-16")]] if pd.Timestamp("2016-06-16") in prices.index else None
    if future_row is None:
        pytest.skip("fixture lacks the required future date")
    object.__setattr__(view, "_visible", pd.concat([tampered, future_row]))

    with pytest.raises(LookAheadError, match="exposes an observation"):
        view.assert_within_boundary()


def test_returns_window_never_crosses_the_boundary(prices):
    for offset in (200, 600, 1200):
        as_of = prices.index[offset]
        view = MarketDataView(prices, as_of)
        returns = view.returns(90)
        assert len(returns) == 90
        assert returns.index.max() <= as_of


def test_forward_fill_inside_a_window_cannot_import_future_data():
    """Gap filling must use only observations already inside the view."""
    panel = make_prices(n_days=300, tickers=["AAA", "BBB"], seed=7)
    gapped = panel.copy()
    as_of = panel.index[200]
    # Blank the two sessions immediately before the decision date.
    gapped.loc[panel.index[199], "AAA"] = np.nan
    gapped.loc[as_of, "AAA"] = np.nan

    view = MarketDataView(gapped, as_of)
    latest = view.latest_prices()

    # The carried-forward value must be the last *observed* price at or before
    # the boundary, never the next real quote after it.
    assert latest["AAA"] == pytest.approx(panel.loc[panel.index[198], "AAA"])
    assert latest["AAA"] != pytest.approx(panel.loc[panel.index[201], "AAA"])


def test_all_strategies_receive_the_same_view(prices, experiment_settings):
    """Cross-strategy comparison is only valid if the information set is shared."""
    a, b = RecordingStrategy(), RecordingStrategy()
    BacktestEngine(prices, experiment_settings).run({"a": a, "b": b})

    assert len(a.seen) == len(b.seen) > 0
    for ra, rb in zip(a.seen, b.seen, strict=True):
        assert ra["as_of"] == rb["as_of"]
        assert ra["n_obs"] == rb["n_obs"]
        assert ra["checksum"] == rb["checksum"]
        assert ra["max_visible_date"] == rb["max_visible_date"]
