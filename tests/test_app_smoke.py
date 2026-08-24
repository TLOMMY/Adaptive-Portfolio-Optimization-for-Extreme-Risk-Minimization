"""Smoke tests for the Streamlit demo.

These do not test presentation. They assert the app *runs* -- that every profile
and period combination executes without raising, that the time-machine controls
advance state, and that the numbers shown come from the same code path the
library tests already cover. A demo that crashes on stage is the failure mode
worth guarding against.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.backtest.experiment import COMPARISON_ORDER, ExperimentSpec, run_comparison
from src.config.assets import DEFAULT_UNIVERSE
from src.config.periods import PERIODS
from src.config.settings import DEFAULT_SNAPSHOT, PROJECT_ROOT
from src.data.csv_provider import CsvProvider
from src.profiles.presets import PROFILES
from src.risk.metrics import comparison_table

pytestmark = pytest.mark.skipif(
    not DEFAULT_SNAPSHOT.exists(), reason="snapshot not generated"
)

# AppTest resolves relative paths against the *calling* file, which lives in
# tests/, so the app path must be absolute.
APP_PATH = str(PROJECT_ROOT / "app.py")


def launch():
    """A freshly run instance of the app."""
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(APP_PATH, default_timeout=300).run()


@pytest.fixture(scope="module")
def prices() -> pd.DataFrame:
    return CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)


# ---------------------------------------------------------------------------
# The experiment behind the app
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("profile_key", list(PROFILES))
def test_every_profile_runs_over_the_full_period(profile_key, prices):
    spec = ExperimentSpec(
        profile=PROFILES[profile_key], period=PERIODS["full"], universe=DEFAULT_UNIVERSE
    )
    experiment = run_comparison(prices, spec)

    assert list(experiment.strategy_names) == COMPARISON_ORDER
    for name in COMPARISON_ORDER:
        result = experiment[name]
        assert len(result.weights_history) == len(experiment.rebalance_dates)
        assert (result.portfolio_values > 0).all()
        assert not any(r.status.startswith("error") for r in result.rebalances)


@pytest.mark.parametrize("period_key", list(PERIODS))
def test_every_period_runs_for_the_default_profile(period_key, prices):
    spec = ExperimentSpec(
        profile=PROFILES["balanced"], period=PERIODS[period_key],
        universe=DEFAULT_UNIVERSE,
    )
    experiment = run_comparison(prices, spec)
    period = PERIODS[period_key]

    assert len(experiment.rebalance_dates) > 0
    assert experiment.rebalance_dates[0] >= pd.Timestamp(period.start)
    assert experiment.rebalance_dates[-1] <= pd.Timestamp(period.end)


def test_subperiod_decisions_match_the_full_period_run(prices):
    """A subperiod is a window onto the same causal process, not a re-tuning."""
    balanced = PROFILES["balanced"]
    full = run_comparison(
        prices, ExperimentSpec(balanced, PERIODS["full"], DEFAULT_UNIVERSE)
    )["Markowitz"]
    early = run_comparison(
        prices, ExperimentSpec(balanced, PERIODS["a"], DEFAULT_UNIVERSE)
    )["Markowitz"]

    shared = early.weights_history.index.intersection(full.weights_history.index)
    assert len(shared) > 4
    pd.testing.assert_frame_equal(
        early.weights_history.loc[shared], full.weights_history.loc[shared]
    )


# ---------------------------------------------------------------------------
# Progressive reveal: the time machine
# ---------------------------------------------------------------------------


def test_truncating_a_result_matches_its_prefix(prices):
    experiment = run_comparison(
        prices, ExperimentSpec(PROFILES["growth"], PERIODS["a"], DEFAULT_UNIVERSE)
    )
    result = experiment["Markowitz"]
    as_of = experiment.rebalance_dates[4]

    truncated = result.until(as_of)
    assert truncated.portfolio_values.index[-1] <= as_of
    assert len(truncated.rebalances) == 5
    pd.testing.assert_series_equal(
        truncated.portfolio_values, result.portfolio_values.loc[: truncated.end_date]
    )


def test_metrics_can_be_computed_at_every_step(prices):
    """Every position of the time-machine slider must produce a usable dashboard."""
    experiment = run_comparison(
        prices, ExperimentSpec(PROFILES["downside"], PERIODS["b"], DEFAULT_UNIVERSE)
    )
    for as_of in experiment.rebalance_dates:
        truncated = {n: experiment[n].until(as_of) for n in COMPARISON_ORDER}
        table = comparison_table(truncated)
        assert list(table.index) == COMPARISON_ORDER
        assert not table["cumulative_return"].isna().any()
        assert (table["maximum_drawdown"] <= 0).all()


def test_truncating_at_the_first_decision_still_works(prices):
    """Step 0 must not produce a degenerate one-point series."""
    experiment = run_comparison(
        prices, ExperimentSpec(PROFILES["low_risk"], PERIODS["c"], DEFAULT_UNIVERSE)
    )
    truncated = experiment["Robust Min-Variance"].until(experiment.rebalance_dates[0])
    assert len(truncated.portfolio_values) >= 2
    assert comparison_table({"x": truncated}).shape[0] == 1


# ---------------------------------------------------------------------------
# The app itself
# ---------------------------------------------------------------------------


def test_the_app_runs_without_raising():
    app = launch()

    assert not app.exception, [str(e.value) for e in app.exception]
    assert app.title[0].value.startswith("Adaptive Investor-Specific")
    assert app.radio[0].options == [p.name for p in PROFILES.values()]
    assert app.selectbox[0].options == [p.label for p in PERIODS.values()]
    assert [b.label for b in app.button] == [
        "Advance quarter", "Advance year", "Run full period", "Reset",
    ]


def test_the_time_machine_controls_advance_and_reset():
    app = launch()
    assert app.session_state["step"] == 0

    app.button[0].click().run()          # advance quarter
    assert app.session_state["step"] == 1
    assert not app.exception

    app.button[1].click().run()          # advance year
    assert app.session_state["step"] == 5

    app.button[2].click().run()          # run full period
    assert app.session_state["step"] > 5
    assert not app.exception

    app.button[3].click().run()          # reset
    assert app.session_state["step"] == 0
    assert not app.exception


def test_switching_profile_resets_the_time_machine():
    app = launch()
    app.button[2].click().run()
    assert app.session_state["step"] > 0

    app.radio[0].set_value("Extreme Low Risk").run()
    assert app.session_state["step"] == 0
    assert not app.exception


def test_every_profile_renders_in_the_app():
    app = launch()
    for profile in PROFILES.values():
        app.radio[0].set_value(profile.name).run()
        assert not app.exception, (profile.key, [str(e.value) for e in app.exception])
        labels = {m.label: m.value for m in app.metric}
        assert labels["Return target"] == f"{profile.return_target:.0%}"


def test_every_period_renders_in_the_app():
    app = launch()
    for period in PERIODS.values():
        app.selectbox[0].set_value(period.label).run()
        assert not app.exception, (period.key, [str(e.value) for e in app.exception])
