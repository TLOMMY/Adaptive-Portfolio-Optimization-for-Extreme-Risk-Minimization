"""Ex-post performance metrics.

Everything here consumes **realised** series -- portfolio values, realised
returns, executed turnover -- and is therefore entitled to look across the whole
evaluation period.  That is the opposite of ``src.estimation``, whose functions
consume a truncated ``MarketDataView`` and must not.  The two live in separate
packages so the distinction is visible at the import line.

Conventions are stated explicitly for every metric, because most of them admit
more than one defensible definition and a comparison is only meaningful if all
strategies are measured the same way.

Phase 2 scope: cumulative return, annualised return, annualised volatility,
maximum drawdown, turnover. CVaR / expected shortfall and worst monthly return
arrive with the CVaR model in Phase 3.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from src.backtest.results import BacktestResult
from src.config.settings import TRADING_DAYS_PER_YEAR, RebalanceFrequency

MONTHS_PER_YEAR = 12


def cumulative_return(values: pd.Series) -> float:
    r"""Total return over the whole period.

    .. math:: R = \frac{V_T}{V_0} - 1

    Computed from the value path, so it already reflects compounding and any
    transaction costs charged along the way.
    """
    _require_values(values)
    return float(values.iloc[-1] / values.iloc[0] - 1.0)


def annualized_return(values: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    r"""Geometric (compound) annual growth rate.

    .. math:: R_{\text{ann}} = \left(\frac{V_T}{V_0}\right)^{252/n} - 1

    where *n* is the number of return observations, i.e. one fewer than the
    number of value observations.

    Geometric rather than arithmetic: this is the constant annual rate that would
    have produced the observed final value, which is the quantity an investor
    actually experiences. It is not directly comparable to the arithmetic
    annualised ``mu`` used inside the optimizer's objective.
    """
    _require_values(values)
    n_returns = len(values) - 1
    if n_returns <= 0:
        return 0.0
    growth = float(values.iloc[-1] / values.iloc[0])
    if growth <= 0:
        return -1.0
    return float(growth ** (periods_per_year / n_returns) - 1.0)


def annualized_volatility(
    returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float:
    r"""Annualised standard deviation of periodic returns.

    .. math:: \sigma_{\text{ann}} = \sigma_{\text{daily}} \sqrt{252}

    Uses the sample standard deviation (``ddof=1``), consistent with treating
    the realised path as one sample rather than the whole population.
    """
    returns = _require_returns(returns)
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))


def maximum_drawdown(values: pd.Series) -> float:
    r"""Largest peak-to-trough decline in portfolio value.

    .. math:: \text{MDD} = \min_t \left( \frac{V_t}{\max_{s \le t} V_s} - 1 \right)

    Returned as a **negative** decimal (``-0.34`` means a 34% decline), so it
    carries the same sign convention as a return. Presentation layers may show
    the magnitude; the stored value keeps the sign.
    """
    _require_values(values)
    running_peak = values.cummax()
    drawdowns = values / running_peak - 1.0
    return float(drawdowns.min())


def drawdown_series(values: pd.Series) -> pd.Series:
    """Drawdown at every point in time, as negative decimals."""
    _require_values(values)
    return values / values.cummax() - 1.0


def average_turnover(result: BacktestResult, exclude_initial: bool = True) -> float:
    r"""Mean one-way turnover per rebalance.

    One-way turnover at a rebalance is :math:`\tfrac12 \sum_i |x_i^{\text{new}} -
    x_i^{\text{drifted}}|`, measured against drifted weights rather than the
    previous target.

    The first rebalance establishes the position from cash and is excluded by
    default: it is not a rebalance in the usual sense, and including it would
    bias the average by an amount depending only on how many rebalances follow.
    """
    return result.average_turnover(exclude_initial=exclude_initial)


def annualized_turnover(
    result: BacktestResult,
    frequency: RebalanceFrequency = RebalanceFrequency.QUARTERLY,
    exclude_initial: bool = True,
) -> float:
    """One-way turnover per year, at the given rebalancing cadence.

    ``1.0`` means the portfolio is, on average, traded once through per year.
    """
    per_year = MONTHS_PER_YEAR / frequency.months
    return average_turnover(result, exclude_initial=exclude_initial) * per_year


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    """Realised performance of one strategy over the evaluation period.

    Every field is computed from realised series; none is stored from a run.
    """

    strategy_name: str
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    n_observations: int
    initial_value: float
    final_value: float
    cumulative_return: float
    annualized_return: float
    annualized_volatility: float
    maximum_drawdown: float
    average_turnover: float
    annualized_turnover: float
    total_cost: float

    def to_dict(self) -> dict:
        return asdict(self)


def summarize(
    result: BacktestResult,
    frequency: RebalanceFrequency = RebalanceFrequency.QUARTERLY,
) -> PerformanceSummary:
    """Compute every Phase 2 metric for one backtest result."""
    values = result.portfolio_values
    returns = result.daily_returns

    return PerformanceSummary(
        strategy_name=result.strategy_name,
        start_date=result.start_date,
        end_date=result.end_date,
        n_observations=len(values),
        initial_value=float(values.iloc[0]),
        final_value=float(values.iloc[-1]),
        cumulative_return=cumulative_return(values),
        annualized_return=annualized_return(values),
        annualized_volatility=annualized_volatility(returns),
        maximum_drawdown=maximum_drawdown(values),
        average_turnover=average_turnover(result),
        annualized_turnover=annualized_turnover(result, frequency),
        total_cost=result.total_cost,
    )


def comparison_table(
    results: dict[str, BacktestResult] | list[BacktestResult],
    frequency: RebalanceFrequency = RebalanceFrequency.QUARTERLY,
) -> pd.DataFrame:
    """Side-by-side metrics for several strategies, one row each."""
    items = results.values() if isinstance(results, dict) else results
    rows = [summarize(r, frequency).to_dict() for r in items]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("strategy_name")


# -- validation --------------------------------------------------------------


def _require_values(values: pd.Series) -> None:
    if not isinstance(values, pd.Series):
        raise TypeError(f"expected a Series of portfolio values, got {type(values).__name__}")
    if values.empty:
        raise ValueError("portfolio value series is empty")
    if values.isna().any():
        raise ValueError("portfolio value series contains NaN")
    if (values <= 0).any():
        raise ValueError("portfolio value series contains non-positive values")


def _require_returns(returns: pd.Series) -> pd.Series:
    if not isinstance(returns, pd.Series):
        raise TypeError(f"expected a Series of returns, got {type(returns).__name__}")
    cleaned = returns.dropna()
    if cleaned.empty:
        raise ValueError("return series is empty after dropping NaN")
    return cleaned
