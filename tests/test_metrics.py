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
    historical_cvar,
    historical_var,
    maximum_drawdown,
    rockafellar_uryasev_objective,
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


# ---------------------------------------------------------------------------
# Historical VaR and CVaR
#
# Sign convention: inputs are RETURNS, outputs are POSITIVE LOSS MAGNITUDES.
# ---------------------------------------------------------------------------

# Ten returns; losses are the negations, so the worst loss is 0.10.
SAMPLE = pd.Series(
    [-0.10, -0.05, -0.02, 0.01, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08]
)


def test_var_is_a_hand_computed_quantile():
    """alpha=0.8, N=10 -> m=2, so VaR is the 2nd-worst loss, 0.05."""
    assert historical_var(SAMPLE, 0.8) == pytest.approx(0.05)


def test_cvar_is_a_hand_computed_tail_average():
    """alpha=0.8, N=10 -> m=2, so CVaR = mean(0.10, 0.05) = 0.075."""
    assert historical_cvar(SAMPLE, 0.8) == pytest.approx(0.075)


def test_var_and_cvar_are_distinct():
    var, cvar = historical_var(SAMPLE, 0.8), historical_cvar(SAMPLE, 0.8)
    assert cvar > var
    assert var == pytest.approx(0.05)
    assert cvar == pytest.approx(0.075)


def test_cvar_is_never_below_var():
    rng = np.random.default_rng(11)
    for _ in range(20):
        returns = pd.Series(rng.normal(0.0005, 0.012, 400))
        for alpha in (0.90, 0.95, 0.99):
            assert historical_cvar(returns, alpha) >= historical_var(returns, alpha) - 1e-12


def test_fractional_boundary_observation_is_weighted_partially():
    """alpha=0.95, N=10 -> m=0.5: half of one observation, not one whole one."""
    # CVaR = (1/0.5) * (0.5 - 0) * 0.10 = 0.10, the single worst loss.
    assert historical_cvar(SAMPLE, 0.95) == pytest.approx(0.10)

    # alpha=0.75, N=10 -> m=2.5: two whole losses plus half of the third.
    expected = (0.10 + 0.05 + 0.5 * 0.02) / 2.5
    assert historical_cvar(SAMPLE, 0.75) == pytest.approx(expected)


def test_cvar_equals_the_rockafellar_uryasev_minimum():
    """The metric must agree with the expression the optimizer actually solves."""
    losses = -SAMPLE.to_numpy()
    grid = np.unique(
        np.concatenate([losses, np.linspace(losses.min() - 0.05, losses.max() + 0.05, 40001)])
    )
    for alpha in (0.70, 0.75, 0.80, 0.90, 0.95):
        minimum = min(rockafellar_uryasev_objective(losses, z, alpha) for z in grid)
        assert historical_cvar(SAMPLE, alpha) == pytest.approx(minimum, abs=1e-9)


def test_cvar_matches_rockafellar_uryasev_on_a_random_sample():
    rng = np.random.default_rng(5)
    returns = pd.Series(rng.normal(0.0004, 0.011, 250))
    losses = -returns.to_numpy()
    grid = np.unique(np.concatenate([losses, np.linspace(losses.min(), losses.max(), 20001)]))

    for alpha in (0.90, 0.95, 0.99):
        minimum = min(rockafellar_uryasev_objective(losses, z, alpha) for z in grid)
        assert historical_cvar(returns, alpha) == pytest.approx(minimum, abs=1e-9)


def test_the_minimiser_of_the_ru_objective_is_var():
    losses = -SAMPLE.to_numpy()
    alpha = 0.8
    at_var = rockafellar_uryasev_objective(losses, historical_var(SAMPLE, alpha), alpha)
    assert at_var == pytest.approx(historical_cvar(SAMPLE, alpha), abs=1e-12)


def test_cvar_increases_with_confidence():
    rng = np.random.default_rng(3)
    returns = pd.Series(rng.normal(0.0003, 0.010, 1000))
    values = [historical_cvar(returns, a) for a in (0.80, 0.90, 0.95, 0.99)]
    assert values == sorted(values)
    assert values[-1] > values[0]


def test_tail_measures_of_an_all_gains_sample_are_negative():
    """A distribution with no losses has a negative 'loss', i.e. a gain."""
    gains = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05])
    assert historical_var(gains, 0.8) < 0
    assert historical_cvar(gains, 0.8) < 0


def test_tail_measures_are_not_annualised():
    """Doubling the sample length must not rescale a per-period tail measure."""
    rng = np.random.default_rng(7)
    short = pd.Series(rng.normal(0, 0.01, 300))
    long = pd.concat([short, pd.Series(rng.normal(0, 0.01, 300))], ignore_index=True)
    # Same distribution, different sample size: the measure should be comparable,
    # not scaled by any horizon factor.
    assert historical_cvar(long, 0.95) == pytest.approx(
        historical_cvar(short, 0.95), rel=0.35
    )


def test_cvar_is_not_maximum_drawdown():
    """A monotonically rising path has zero drawdown but a real per-day CVaR."""
    rng = np.random.default_rng(2)
    daily = pd.Series(np.abs(rng.normal(0.001, 0.002, 300)))  # every day positive
    path = values(list(100.0 * (1 + daily).cumprod()))
    assert maximum_drawdown(path) == pytest.approx(0.0)
    assert historical_cvar(daily, 0.95) != pytest.approx(0.0)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.2])
def test_invalid_confidence_is_rejected(bad):
    with pytest.raises(ValueError, match="confidence must lie"):
        historical_cvar(SAMPLE, bad)
    with pytest.raises(ValueError, match="confidence must lie"):
        historical_var(SAMPLE, bad)


def test_non_finite_returns_are_rejected():
    with pytest.raises(ValueError, match="non-finite"):
        historical_cvar(pd.Series([0.01, np.inf, -0.02]))


def test_empty_sample_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        historical_cvar(pd.Series([], dtype="float64"))
    with pytest.raises(ValueError, match="empty"):
        rockafellar_uryasev_objective(np.array([]), 0.0)


def test_summary_reports_the_tail_metrics(prices, phase2_settings):
    from src.portfolio.equal_weight import EqualWeightOptimizer

    result = BacktestEngine(prices, phase2_settings).run(
        {"ew": EqualWeightOptimizer(lookback_days=phase2_settings.lookback_days)}
    )["ew"]
    summary = summarize(result, phase2_settings.rebalance_frequency)

    assert summary.cvar_confidence == 0.95
    assert summary.daily_cvar >= summary.daily_var
    assert summary.daily_cvar == pytest.approx(
        historical_cvar(result.daily_returns, 0.95)
    )
