"""Walk-forward integration for the Phase 2 models.

The optimizers are exercised through the real backtest engine, on the frozen
research window and on synthetic fixtures, to confirm that:

* the no-look-ahead guarantee survives contact with an actual optimizer -- not
  just the trivial strategies Phase 1 used;
* constraints hold at *every* decision date, not only at the one a unit test
  happens to pick;
* the shortfall mechanism behaves across a whole experiment.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import DISTINCT_ASSET_CLASSES

from src.backtest.engine import BacktestEngine
from src.config.assets import DEFAULT_UNIVERSE
from src.config.settings import DEFAULT_SNAPSHOT, BacktestSettings, RebalanceFrequency
from src.data.csv_provider import CsvProvider
from src.portfolio.constraints import ConstraintSet
from src.portfolio.equal_weight import EqualWeightOptimizer
from src.portfolio.markowitz import MarkowitzOptimizer

TOL = 1e-6


@pytest.fixture
def wf_settings() -> BacktestSettings:
    return BacktestSettings(
        start=pd.Timestamp("2016-01-01").date(),
        end=pd.Timestamp("2018-12-31").date(),
        lookback_years=1.0,
        rebalance_frequency=RebalanceFrequency.QUARTERLY,
        transaction_cost_bps=0.0,
    )


def make_strategies(lookback: int, **kwargs) -> dict:
    return {
        "ew": EqualWeightOptimizer(lookback_days=lookback),
        "mv": MarkowitzOptimizer(
            2.5,
            lookback_days=lookback,
            asset_class_map=DISTINCT_ASSET_CLASSES,
            constraints=ConstraintSet(**kwargs),
        ),
    }


# ---------------------------------------------------------------------------
# The no-look-ahead guarantee, with real optimizers in the loop
# ---------------------------------------------------------------------------


def test_walkforward_decisions_survive_a_poisoned_future(risk_prices, wf_settings):
    """The flagship invariance check, now with an actual optimizer."""
    lookback = wf_settings.lookback_days

    def run(panel):
        return BacktestEngine(panel, wf_settings).run(
            make_strategies(lookback, max_weight=0.5, min_return=0.02)
        )

    reference = run(risk_prices)["mv"]
    assert len(reference.weights_history) >= 8

    for boundary in reference.weights_history.index:
        poisoned = risk_prices.copy()
        poisoned.loc[poisoned.index > boundary] = 424_242.0

        observed = run(poisoned)["mv"]

        pd.testing.assert_frame_equal(
            observed.weights_history.loc[:boundary],
            reference.weights_history.loc[:boundary],
            obj=f"Markowitz weights at or before {boundary.date()}",
        )


def test_walkforward_shortfall_diagnostics_survive_a_poisoned_future(
    risk_prices, wf_settings
):
    """Diagnostics, not just weights, must be free of future information."""
    lookback = wf_settings.lookback_days
    strategies = lambda: make_strategies(lookback, max_weight=0.5, min_return=5.0)  # noqa: E731

    reference = BacktestEngine(risk_prices, wf_settings).run(strategies())["mv"]
    boundary = reference.weights_history.index[4]

    poisoned = risk_prices.copy()
    poisoned.loc[poisoned.index > boundary] = 424_242.0
    observed = BacktestEngine(poisoned, wf_settings).run(strategies())["mv"]

    ref_frame = reference.diagnostics_frame()
    obs_frame = observed.diagnostics_frame()
    upto = ref_frame["as_of"] <= boundary

    assert np.allclose(
        obs_frame.loc[upto, "return_shortfall"].to_numpy(),
        ref_frame.loc[upto, "return_shortfall"].to_numpy(),
    )


def test_every_decision_records_a_boundary_at_or_before_its_date(risk_prices, wf_settings):
    experiment = BacktestEngine(risk_prices, wf_settings).run(
        make_strategies(wf_settings.lookback_days, max_weight=0.6)
    )
    for result in experiment:
        for record in result.rebalances:
            assert record.data_last_date <= record.as_of


def test_optimizers_receive_an_identical_information_set(risk_prices, wf_settings):
    """Both models must see the same window at every decision date."""
    experiment = BacktestEngine(risk_prices, wf_settings).run(
        make_strategies(wf_settings.lookback_days, max_weight=0.6)
    )
    ew, mv = experiment["ew"].diagnostics_frame(), experiment["mv"].diagnostics_frame()

    assert (ew["as_of"] == mv["as_of"]).all()
    assert (ew["window_start"] == mv["window_start"]).all()
    assert (ew["window_end"] == mv["window_end"]).all()
    assert (ew["n_observations"] == mv["n_observations"]).all()


# ---------------------------------------------------------------------------
# Constraints hold at every decision date
# ---------------------------------------------------------------------------


def test_constraints_hold_at_every_rebalance(risk_prices, wf_settings):
    experiment = BacktestEngine(risk_prices, wf_settings).run(
        make_strategies(
            wf_settings.lookback_days,
            max_weight=0.4,
            asset_class_limits={"Equity": 0.5},
        )
    )
    weights = experiment["mv"].weights_history

    assert np.allclose(weights.sum(axis=1).to_numpy(), 1.0, atol=TOL)
    assert (weights.to_numpy() >= -TOL).all()
    assert (weights.to_numpy() <= 0.4 + TOL).all()
    assert (weights[["STOCK", "WILD"]].sum(axis=1).to_numpy() <= 0.5 + TOL).all()


def test_no_rebalance_failed(risk_prices, wf_settings):
    """A solver failure would show up as an `error:` status, never silently."""
    experiment = BacktestEngine(risk_prices, wf_settings).run(
        make_strategies(wf_settings.lookback_days, max_weight=0.4, min_return=0.02)
    )
    for result in experiment:
        statuses = {r.status for r in result.rebalances}
        assert not any(s.startswith("error") for s in statuses), statuses


def test_equal_weight_is_exactly_one_over_n_at_every_rebalance(risk_prices, wf_settings):
    experiment = BacktestEngine(risk_prices, wf_settings).run(
        make_strategies(wf_settings.lookback_days)
    )
    weights = experiment["ew"].weights_history
    assert np.allclose(weights.to_numpy(), 1.0 / weights.shape[1])


def test_risk_aversion_changes_realised_risk_over_a_walk_forward(risk_prices, wf_settings):
    """The lambda effect must persist through a whole experiment, not just one date."""
    from src.risk.metrics import annualized_volatility

    lookback = wf_settings.lookback_days
    experiment = BacktestEngine(risk_prices, wf_settings).run(
        {
            "aggressive": MarkowitzOptimizer(0.5, lookback_days=lookback, name="aggressive"),
            "conservative": MarkowitzOptimizer(50.0, lookback_days=lookback, name="conservative"),
        }
    )
    aggressive = annualized_volatility(experiment["aggressive"].daily_returns)
    conservative = annualized_volatility(experiment["conservative"].daily_returns)

    assert conservative < aggressive


# ---------------------------------------------------------------------------
# The frozen research window, on real data
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not DEFAULT_SNAPSHOT.exists(), reason="snapshot not generated")
def test_research_experiment_runs_with_phase_two_models():
    prices = CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)
    settings = BacktestSettings()
    lookback = settings.lookback_days
    classes = DEFAULT_UNIVERSE.asset_class_map()

    experiment = BacktestEngine(prices, settings).run(
        {
            "Equal Weight": EqualWeightOptimizer(lookback_days=lookback),
            "Markowitz": MarkowitzOptimizer(
                2.5,
                lookback_days=lookback,
                asset_class_map=classes,
                constraints=ConstraintSet(max_weight=0.35, asset_class_limits={"Equity": 0.7}),
            ),
        }
    )

    assert len(experiment.rebalance_dates) == 40
    for result in experiment:
        assert len(result.weights_history) == 40
        assert (result.portfolio_values > 0).all()
        weights = result.weights_history
        assert np.allclose(weights.sum(axis=1).to_numpy(), 1.0, atol=TOL)
        assert (weights.to_numpy() >= -TOL).all()

    markowitz = experiment["Markowitz"].weights_history
    assert (markowitz.to_numpy() <= 0.35 + TOL).all()
    equity = markowitz[["SPY", "IJR", "EFA", "EEM"]].sum(axis=1)
    assert (equity.to_numpy() <= 0.7 + TOL).all()


@pytest.mark.skipif(not DEFAULT_SNAPSHOT.exists(), reason="snapshot not generated")
def test_research_window_is_frozen_against_new_data():
    """Appending future data must not change any result in research mode."""
    prices = CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)
    settings = BacktestSettings()
    lookback = settings.lookback_days

    def run(panel):
        return BacktestEngine(panel, settings).run(
            {"mv": MarkowitzOptimizer(2.5, lookback_days=lookback,
                                      constraints=ConstraintSet(max_weight=0.35))}
        )["mv"]

    reference = run(prices)

    # Simulate a snapshot refresh bringing in later sessions.
    extra_index = pd.bdate_range(
        prices.index[-1] + pd.Timedelta(days=1), periods=200, name="date"
    )
    extra = pd.DataFrame(
        np.tile(prices.iloc[-1].to_numpy() * 1.5, (len(extra_index), 1)),
        index=extra_index,
        columns=prices.columns,
    )
    extended = run(pd.concat([prices, extra]))

    pd.testing.assert_frame_equal(extended.weights_history, reference.weights_history)
    pd.testing.assert_series_equal(extended.portfolio_values, reference.portfolio_values)


@pytest.mark.skipif(not DEFAULT_SNAPSHOT.exists(), reason="snapshot not generated")
def test_shortfall_is_reported_across_the_research_window():
    """A demanding target should be unattainable at some dates and met at others."""
    prices = CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)
    settings = BacktestSettings()

    result = BacktestEngine(prices, settings).run(
        {
            "mv": MarkowitzOptimizer(
                2.5,
                lookback_days=settings.lookback_days,
                constraints=ConstraintSet(max_weight=0.35, min_return=0.12),
            )
        }
    )["mv"]

    frame = result.diagnostics_frame()
    assert (frame["return_shortfall"] >= 0).all()
    assert (frame["return_shortfall"] > 0).any(), "expected some dates to be infeasible"
    assert (frame["return_shortfall"] == 0).any(), "expected some dates to be feasible"

    # The defining identity, at every date where the target bound.
    binding = frame[frame["return_shortfall"] > 0]
    assert np.allclose(
        (0.12 - binding["return_shortfall"]).to_numpy(),
        binding["max_attainable_return"].to_numpy(),
        atol=1e-7,
    )

    # And the status always agrees with the shortfall.
    assert (
        (frame["return_shortfall"] > 0)
        == (frame["status"] == "optimal_with_shortfall")
    ).all()
