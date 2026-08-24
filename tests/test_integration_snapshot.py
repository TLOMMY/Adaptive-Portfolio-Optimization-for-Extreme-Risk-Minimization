"""End-to-end checks against the committed real-market snapshot.

Synthetic fixtures verify logic; these verify that the same guarantees survive
contact with real data -- holidays, leading gaps, uneven calendars and the actual
2016-2026 experiment window specified for the project.
"""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import RecordingStrategy, TrailingMomentumStrategy, UniformStrategy

from src.backtest.engine import BacktestEngine
from src.config.assets import DEFAULT_UNIVERSE
from src.config.settings import DEFAULT_SNAPSHOT, BacktestSettings, RebalanceFrequency
from src.data.csv_provider import CsvProvider

pytestmark = pytest.mark.skipif(
    not DEFAULT_SNAPSHOT.exists(),
    reason="run `python scripts/fetch_data.py` to generate the snapshot",
)


@pytest.fixture(scope="module")
def real_prices() -> pd.DataFrame:
    return CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)


@pytest.fixture
def default_settings() -> BacktestSettings:
    return BacktestSettings()


def test_default_experiment_runs_end_to_end(real_prices, default_settings):
    experiment = BacktestEngine(real_prices, default_settings).run(
        {"uniform": UniformStrategy(), "momentum": TrailingMomentumStrategy(lookback=120)}
    )
    values = experiment.value_frame()

    assert not values.isna().any().any()
    assert (values > 0).all().all()
    assert len(experiment.rebalance_dates) == 40  # 2016Q1 .. 2025Q4, ten frozen years


def test_default_experiment_spans_the_specified_window(real_prices, default_settings):
    engine = BacktestEngine(real_prices, default_settings)
    first, last = engine.rebalance_dates[0], engine.rebalance_dates[-1]

    assert first == pd.Timestamp("2016-01-04"), "first decision is the first 2016 session"
    assert first >= pd.Timestamp(default_settings.start)
    assert last <= pd.Timestamp(default_settings.end)

    result = engine.run({"uniform": UniformStrategy()})["uniform"]
    assert result.start_date == first
    assert result.end_date == real_prices.index[
        real_prices.index <= pd.Timestamp(default_settings.end)
    ][-1]


def test_decision_dates_fall_on_quarter_boundaries(real_prices, default_settings):
    engine = BacktestEngine(real_prices, default_settings)
    for d in engine.rebalance_dates:
        assert d.month in (1, 4, 7, 10), f"{d.date()} is not a quarter start"


def test_first_estimation_window_is_the_full_configured_lookback(
    real_prices, default_settings
):
    """The 2016-01 decision must see three full years of prior data."""
    engine = BacktestEngine(real_prices, default_settings)
    from src.data.window import MarketDataView

    view = MarketDataView(real_prices, engine.rebalance_dates[0], default_settings.cutoff)
    returns = view.returns(default_settings.lookback_days)

    assert len(returns) == default_settings.lookback_days
    assert returns.index.max() <= engine.rebalance_dates[0]
    assert returns.index.min() >= pd.Timestamp("2012-12-01")
    assert not returns.isna().any().any()


def test_no_lookahead_on_real_data(real_prices, default_settings):
    strategy = RecordingStrategy()
    BacktestEngine(real_prices, default_settings).run({"recording": strategy})

    assert len(strategy.seen) == 40
    for record in strategy.seen:
        assert record["max_visible_date"] <= record["as_of"]


def test_real_data_decisions_survive_a_poisoned_future(real_prices):
    """The flagship invariance check, repeated on genuine market data."""
    settings = BacktestSettings(
        start=pd.Timestamp("2016-01-01").date(),
        end=pd.Timestamp("2019-12-31").date(),
        lookback_years=3.0,
        rebalance_frequency=RebalanceFrequency.QUARTERLY,
    )

    def run(panel):
        return BacktestEngine(panel, settings).run(
            {"momentum": TrailingMomentumStrategy(lookback=250)}
        )["momentum"]

    reference = run(real_prices)

    # Poison everything after a mid-experiment decision date, including the
    # 2020 crash that follows this window.
    boundary = reference.weights_history.index[6]
    poisoned = real_prices.copy()
    poisoned.loc[poisoned.index > boundary] = 111_111.0

    observed = run(poisoned)

    pd.testing.assert_frame_equal(
        observed.weights_history.loc[:boundary],
        reference.weights_history.loc[:boundary],
    )


def test_gld_and_vnq_leading_gaps_do_not_affect_the_experiment(real_prices, default_settings):
    """Two assets start after the panel does; the experiment must be unaffected."""
    first_decision = BacktestEngine(real_prices, default_settings).rebalance_dates[0]
    window = real_prices.loc[real_prices.index <= first_decision].tail(
        default_settings.lookback_days + 1
    )
    assert not window.isna().any().any()


def test_equal_weight_matches_a_hand_computed_first_period(real_prices, default_settings):
    result = BacktestEngine(real_prices, default_settings).run(
        {"uniform": UniformStrategy()}
    )["uniform"]

    t0 = result.start_date
    t1 = real_prices.index[real_prices.index > t0][0]
    expected = float((real_prices.loc[t1] / real_prices.loc[t0] - 1.0).mean())

    assert result.daily_returns.loc[t1] == pytest.approx(expected, rel=1e-10)


@pytest.mark.parametrize("frequency", list(RebalanceFrequency))
def test_every_rebalance_frequency_runs_on_real_data(real_prices, frequency):
    settings = BacktestSettings(rebalance_frequency=frequency)
    result = BacktestEngine(real_prices, settings).run({"uniform": UniformStrategy()})[
        "uniform"
    ]
    assert len(result.weights_history) > 0
    assert (result.portfolio_values > 0).all()


@pytest.mark.parametrize("lookback_years", [1.0, 2.0, 3.0, 5.0])
def test_every_lookback_length_runs_on_real_data(real_prices, lookback_years):
    settings = BacktestSettings(lookback_years=lookback_years)
    engine = BacktestEngine(real_prices, settings)
    result = engine.run({"momentum": TrailingMomentumStrategy(lookback=60)})["momentum"]
    assert len(result.weights_history) == len(engine.rebalance_dates)
