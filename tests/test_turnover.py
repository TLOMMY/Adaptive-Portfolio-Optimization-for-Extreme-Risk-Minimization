"""Tests for the one-way turnover constraint.

The constraint is
``0.5 * sum_i |x_i - w_i^pre| <= max_turnover`` against the *drifted*
pre-rebalance weights the engine supplies, which is the same quantity
``BacktestResult`` reports as realised turnover -- so a limit that binds must
show up in the reported metric.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import DISTINCT_ASSET_CLASSES

from src.backtest.engine import BacktestEngine
from src.config.settings import BacktestSettings, RebalanceFrequency
from src.portfolio.constraints import ConstraintError, ConstraintSet
from src.portfolio.cvar import CVaROptimizer
from src.portfolio.markowitz import MarkowitzOptimizer
from src.portfolio.robust_variance import RobustMinimumVarianceOptimizer

TOL = 1e-6


@pytest.fixture
def tw_settings() -> BacktestSettings:
    return BacktestSettings(
        start=pd.Timestamp("2016-01-01").date(),
        end=pd.Timestamp("2018-12-31").date(),
        lookback_years=1.0,
        rebalance_frequency=RebalanceFrequency.QUARTERLY,
        transaction_cost_bps=0.0,
    )


def markowitz(lookback: int, limit: float | None, **kwargs) -> MarkowitzOptimizer:
    return MarkowitzOptimizer(
        1.0, lookback_days=lookback, asset_class_map=DISTINCT_ASSET_CLASSES,
        constraints=ConstraintSet(max_weight=0.5, max_turnover=limit, **kwargs),
    )


# ---------------------------------------------------------------------------
# Declaration
# ---------------------------------------------------------------------------


def test_no_limit_by_default():
    assert ConstraintSet().max_turnover is None


@pytest.mark.parametrize("bad", [0.0, -0.1])
def test_a_non_positive_limit_is_rejected(bad):
    with pytest.raises(ConstraintError, match="max_turnover"):
        ConstraintSet(max_turnover=bad)


# ---------------------------------------------------------------------------
# The limit binds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [0.30, 0.15, 0.05])
def test_realised_turnover_never_exceeds_the_limit(limit, risk_prices, tw_settings):
    result = BacktestEngine(risk_prices, tw_settings).run(
        {"mv": markowitz(tw_settings.lookback_days, limit)}
    )["mv"]

    # The first rebalance establishes the position from cash and is exempt.
    for record in result.rebalances[1:]:
        assert record.turnover <= limit + TOL, (
            f"turnover {record.turnover:.4f} exceeds limit {limit} "
            f"at {record.as_of.date()}"
        )


def test_a_tighter_limit_produces_less_trading(risk_prices, tw_settings):
    lookback = tw_settings.lookback_days
    turnovers = []
    for limit in (None, 0.30, 0.10):
        result = BacktestEngine(risk_prices, tw_settings).run(
            {"mv": markowitz(lookback, limit)}
        )["mv"]
        turnovers.append(result.average_turnover())

    assert turnovers == sorted(turnovers, reverse=True), turnovers
    assert turnovers[0] > turnovers[-1], "the limit must actually bind on this fixture"


def test_the_limit_is_measured_against_drifted_weights(risk_prices, tw_settings):
    """Not against the previous *target* -- positions move with the market."""
    result = BacktestEngine(risk_prices, tw_settings).run(
        {"mv": markowitz(tw_settings.lookback_days, 0.15)}
    )["mv"]

    for record in result.rebalances[1:]:
        computed = 0.5 * float((record.weights_after - record.weights_before).abs().sum())
        assert computed == pytest.approx(record.turnover)
        assert computed <= 0.15 + TOL


def test_the_first_rebalance_is_exempt(risk_prices, tw_settings):
    """A limit at inception would forbid investing at all."""
    result = BacktestEngine(risk_prices, tw_settings).run(
        {"mv": markowitz(tw_settings.lookback_days, 0.05)}
    )["mv"]
    first = result.rebalances[0]
    assert first.weights_before.sum() == pytest.approx(0.0)
    assert first.turnover == pytest.approx(0.5)  # the establishment trade
    assert first.weights_after.sum() == pytest.approx(1.0)


def test_an_unbound_limit_leaves_the_solution_unchanged(risk_prices, tw_settings):
    """A limit above what the model would trade anyway must change nothing."""
    lookback = tw_settings.lookback_days
    free = BacktestEngine(risk_prices, tw_settings).run(
        {"mv": markowitz(lookback, None)}
    )["mv"]
    generous = BacktestEngine(risk_prices, tw_settings).run(
        {"mv": markowitz(lookback, 0.99)}
    )["mv"]
    pd.testing.assert_frame_equal(
        generous.weights_history, free.weights_history, atol=1e-6
    )


# ---------------------------------------------------------------------------
# Every model honours it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory", ["markowitz", "cvar", "robust"])
def test_every_optimizer_honours_the_limit(factory, risk_prices, tw_settings):
    from src.estimation.covariance_scenarios import RollingWindowUncertaintySet

    lookback = tw_settings.lookback_days
    constraints = ConstraintSet(max_weight=0.5, max_turnover=0.12)
    shared = dict(
        lookback_days=lookback, asset_class_map=DISTINCT_ASSET_CLASSES,
        constraints=constraints,
    )
    optimizer = {
        "markowitz": lambda: MarkowitzOptimizer(1.0, **shared),
        "cvar": lambda: CVaROptimizer(0.95, **shared),
        "robust": lambda: RobustMinimumVarianceOptimizer(
            uncertainty_set=RollingWindowUncertaintySet(
                window_length=126, stride=31, n_subwindows=5, min_observations=120
            ),
            **shared,
        ),
    }[factory]()

    result = BacktestEngine(risk_prices, tw_settings).run({"s": optimizer})["s"]
    for record in result.rebalances[1:]:
        assert record.turnover <= 0.12 + TOL


def test_diagnostics_report_the_limit_and_whether_it_was_relaxed(
    risk_prices, tw_settings
):
    result = BacktestEngine(risk_prices, tw_settings).run(
        {"mv": markowitz(tw_settings.lookback_days, 0.20)}
    )["mv"]
    frame = result.diagnostics_frame()

    assert (frame["turnover_limit"] == 0.20).all()
    assert "turnover_limit_relaxed" in frame.columns
    # On this fixture the limit is always satisfiable, so nothing is relaxed.
    assert not frame["turnover_limit_relaxed"].any()


def test_the_limit_interacts_correctly_with_a_return_target(risk_prices, tw_settings):
    """Both constraints must hold, and the shortfall must reflect both."""
    result = BacktestEngine(risk_prices, tw_settings).run(
        {"mv": markowitz(tw_settings.lookback_days, 0.15, min_return=0.03)}
    )["mv"]

    for record in result.rebalances[1:]:
        assert record.turnover <= 0.15 + TOL
    frame = result.diagnostics_frame()
    assert (frame["return_shortfall"] >= 0).all()
    assert not any(r.status.startswith("error") for r in result.rebalances)


def test_weights_stay_valid_under_a_tight_limit(risk_prices, tw_settings):
    result = BacktestEngine(risk_prices, tw_settings).run(
        {"mv": markowitz(tw_settings.lookback_days, 0.05)}
    )["mv"]
    weights = result.weights_history
    assert np.allclose(weights.sum(axis=1).to_numpy(), 1.0, atol=TOL)
    assert (weights.to_numpy() >= -TOL).all()
    assert (weights.to_numpy() <= 0.5 + TOL).all()
