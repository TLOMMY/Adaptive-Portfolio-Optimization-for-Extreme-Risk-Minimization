"""Tests for ex-post performance metrics.

Every metric is checked against a value computed by hand on a series whose
answer is known in advance, not against previously recorded output.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine
from src.config.settings import (
    TRADING_DAYS_PER_YEAR,
    RebalanceFrequency,
)
from src.risk.metrics import (
    annualized_return,
    annualized_turnover,
    annualized_volatility,
    average_turnover,
    comparison_table,
    cumulative_return,
    drawdown_series,
    maximum_drawdown,
    summarize,
)


def values(data: list[float], start: str = "2016-01-04") -> pd.Series:
    index = pd.bdate_range(start=start, periods=len(data), name="date")
    return pd.Series(data, index=index, dtype="float64")


# ---------------------------------------------------------------------------
# Cumulative return
# ---------------------------------------------------------------------------


def test_cumulative_return_is_the_total_growth():
    assert cumulative_return(values([100.0, 110.0, 150.0])) == pytest.approx(0.5)


def test_cumulative_return_can_be_negative():
    assert cumulative_return(values([100.0, 50.0])) == pytest.approx(-0.5)


def test_cumulative_return_of_a_flat_path_is_zero():
    assert cumulative_return(values([100.0] * 10)) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Annualised return
# ---------------------------------------------------------------------------


def test_annualized_return_over_exactly_one_year():
    """253 values = 252 returns = one trading year; doubling is +100%/yr."""
    path = values(list(np.linspace(100.0, 200.0, TRADING_DAYS_PER_YEAR + 1)))
    assert annualized_return(path) == pytest.approx(1.0, rel=1e-9)


def test_annualized_return_over_two_years_compounds():
    """Quadrupling over two years is a doubling per year."""
    n = 2 * TRADING_DAYS_PER_YEAR + 1
    path = values(list(np.linspace(100.0, 400.0, n)))
    assert annualized_return(path) == pytest.approx(1.0, rel=1e-9)


def test_annualized_return_is_geometric_not_arithmetic():
    """+50% then -50% leaves 75% of capital: the annual rate must be negative."""
    n = TRADING_DAYS_PER_YEAR + 1
    path = values([100.0] * (n - 1) + [75.0])
    assert annualized_return(path) == pytest.approx(-0.25, rel=1e-9)


def test_annualized_return_of_a_single_observation_is_zero():
    assert annualized_return(values([100.0])) == 0.0


# ---------------------------------------------------------------------------
# Annualised volatility
# ---------------------------------------------------------------------------


def test_annualized_volatility_of_constant_returns_is_zero():
    returns = pd.Series([0.001] * 100)
    assert annualized_volatility(returns) == pytest.approx(0.0)


def test_annualized_volatility_scales_by_the_root_of_the_trading_year():
    rng = np.random.default_rng(0)
    returns = pd.Series(rng.normal(0, 0.01, 1000))
    expected = returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
    assert annualized_volatility(returns) == pytest.approx(expected)


def test_annualized_volatility_uses_the_sample_standard_deviation():
    returns = pd.Series([0.01, -0.01, 0.02, -0.02])
    expected = returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
    assert annualized_volatility(returns) == pytest.approx(expected)
    assert annualized_volatility(returns) != pytest.approx(
        returns.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR)
    )


def test_annualized_volatility_of_one_observation_is_zero():
    assert annualized_volatility(pd.Series([0.01])) == 0.0


def test_annualized_volatility_ignores_nan():
    assert annualized_volatility(pd.Series([0.01, np.nan, -0.01])) == pytest.approx(
        pd.Series([0.01, -0.01]).std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
    )


# ---------------------------------------------------------------------------
# Maximum drawdown
# ---------------------------------------------------------------------------


def test_maximum_drawdown_of_a_hand_computed_path():
    """Peak 120 -> trough 90 is a 25% decline."""
    assert maximum_drawdown(values([100.0, 120.0, 90.0, 150.0])) == pytest.approx(-0.25)


def test_maximum_drawdown_is_measured_from_the_running_peak_not_the_start():
    """The 150 -> 120 fall (-20%) is deeper than 100 -> 90 (-10%)."""
    assert maximum_drawdown(values([100.0, 90.0, 150.0, 120.0])) == pytest.approx(-0.2)


def test_maximum_drawdown_of_a_monotonic_rise_is_zero():
    assert maximum_drawdown(values([100.0, 110.0, 120.0])) == pytest.approx(0.0)


def test_maximum_drawdown_is_negative_by_convention():
    result = maximum_drawdown(values([100.0, 50.0, 100.0]))
    assert result < 0
    assert result == pytest.approx(-0.5)


def test_maximum_drawdown_finds_the_deepest_of_several():
    path = values([100.0, 80.0, 120.0, 60.0, 130.0])
    assert maximum_drawdown(path) == pytest.approx(-0.5)  # 120 -> 60


def test_drawdown_series_matches_its_minimum():
    path = values([100.0, 120.0, 90.0, 150.0])
    series = drawdown_series(path)
    assert series.min() == pytest.approx(maximum_drawdown(path))
    assert (series <= 1e-15).all()
    assert len(series) == len(path)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad", [pd.Series([], dtype="float64"), pd.Series([100.0, np.nan]), pd.Series([100.0, -5.0])]
)
def test_invalid_value_series_are_rejected(bad):
    with pytest.raises(ValueError):
        cumulative_return(bad)


def test_non_series_input_is_rejected():
    with pytest.raises(TypeError):
        cumulative_return([100.0, 110.0])


def test_empty_return_series_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        annualized_volatility(pd.Series([], dtype="float64"))


# ---------------------------------------------------------------------------
# Turnover
# ---------------------------------------------------------------------------


def test_turnover_excludes_the_initial_position_by_default(prices, phase2_settings):
    from src.portfolio.equal_weight import EqualWeightOptimizer

    result = BacktestEngine(prices, phase2_settings).run(
        {"ew": EqualWeightOptimizer(lookback_days=phase2_settings.lookback_days)}
    )["ew"]

    excluding = average_turnover(result, exclude_initial=True)
    including = average_turnover(result, exclude_initial=False)

    assert excluding == pytest.approx(
        np.mean([r.turnover for r in result.rebalances[1:]])
    )
    assert including == pytest.approx(np.mean([r.turnover for r in result.rebalances]))
    assert including > excluding, "the initial trade is the largest; it must be excluded"


def test_annualized_turnover_scales_with_the_rebalancing_cadence(prices, phase2_settings):
    from src.portfolio.equal_weight import EqualWeightOptimizer

    result = BacktestEngine(prices, phase2_settings).run(
        {"ew": EqualWeightOptimizer(lookback_days=phase2_settings.lookback_days)}
    )["ew"]

    per_rebalance = average_turnover(result)
    assert annualized_turnover(result, RebalanceFrequency.QUARTERLY) == pytest.approx(
        per_rebalance * 4
    )
    assert annualized_turnover(result, RebalanceFrequency.MONTHLY) == pytest.approx(
        per_rebalance * 12
    )
    assert annualized_turnover(result, RebalanceFrequency.ANNUAL) == pytest.approx(
        per_rebalance
    )


# ---------------------------------------------------------------------------
# Summary and comparison
# ---------------------------------------------------------------------------


def test_summary_reports_every_phase_two_metric(prices, phase2_settings):
    from src.portfolio.equal_weight import EqualWeightOptimizer

    result = BacktestEngine(prices, phase2_settings).run(
        {"ew": EqualWeightOptimizer(lookback_days=phase2_settings.lookback_days)}
    )["ew"]
    summary = summarize(result, phase2_settings.rebalance_frequency)

    assert summary.strategy_name == "ew"
    assert summary.initial_value == pytest.approx(phase2_settings.initial_capital)
    assert summary.n_observations == len(result.portfolio_values)
    assert summary.maximum_drawdown <= 0
    assert summary.annualized_volatility > 0
    assert summary.total_cost == 0.0

    # Internal consistency with the underlying series.
    assert summary.cumulative_return == pytest.approx(
        cumulative_return(result.portfolio_values)
    )
    assert summary.final_value == pytest.approx(result.portfolio_values.iloc[-1])


def test_comparison_table_has_one_row_per_strategy(prices, phase2_settings):
    from src.portfolio.constraints import ConstraintSet
    from src.portfolio.equal_weight import EqualWeightOptimizer
    from src.portfolio.markowitz import MarkowitzOptimizer

    lookback = phase2_settings.lookback_days
    experiment = BacktestEngine(prices, phase2_settings).run(
        {
            "ew": EqualWeightOptimizer(lookback_days=lookback),
            "mv": MarkowitzOptimizer(
                2.5, lookback_days=lookback, constraints=ConstraintSet(max_weight=0.5)
            ),
        }
    )
    table = comparison_table(experiment.results, phase2_settings.rebalance_frequency)

    assert list(table.index) == ["ew", "mv"]
    for column in (
        "cumulative_return",
        "annualized_return",
        "annualized_volatility",
        "maximum_drawdown",
        "average_turnover",
    ):
        assert column in table.columns
        assert not table[column].isna().any()


def test_comparison_table_of_nothing_is_empty():
    assert comparison_table({}).empty
