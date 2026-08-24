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
maximum drawdown, turnover. Phase 3 adds historical VaR and CVaR / expected
shortfall. Worst monthly return arrives with the profile system.

Sign conventions differ between metrics *on purpose*, and each is stated at its
own definition:

* returns and drawdowns keep their natural sign, so a loss is negative;
* VaR and CVaR are reported as **positive loss magnitudes**, matching the
  quantity the CVaR optimizer minimises. This makes an optimizer's reported
  in-sample CVaR and this module's realised CVaR the same kind of number and
  directly comparable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from src.backtest.results import BacktestResult
from src.config.settings import TRADING_DAYS_PER_YEAR, RebalanceFrequency

MONTHS_PER_YEAR = 12

DEFAULT_CONFIDENCE = 0.95
"""Default tail confidence level for VaR and CVaR."""


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


# ---------------------------------------------------------------------------
# Tail risk: historical VaR and CVaR / Expected Shortfall
#
# Both are computed on the **empirical** distribution of the supplied returns.
# No distributional assumption is made, and no rescaling of any kind is applied:
# a VaR or CVaR computed from daily returns is a ONE-DAY figure and stays one.
# Tail measures do not obey a square-root-of-time rule, so a daily CVaR is never
# annualised anywhere in this project.
# ---------------------------------------------------------------------------


def _losses_from_returns(returns: pd.Series | np.ndarray) -> np.ndarray:
    """Convert a return series to losses: ``L = -r``. Positive means a loss."""
    if isinstance(returns, pd.Series):
        cleaned = _require_returns(returns).to_numpy(dtype="float64")
    else:
        cleaned = np.asarray(returns, dtype="float64")
        cleaned = cleaned[~np.isnan(cleaned)]
        if cleaned.size == 0:
            raise ValueError("return series is empty after dropping NaN")
    if not np.all(np.isfinite(cleaned)):
        raise ValueError("return series contains non-finite values")
    return -cleaned


def _check_confidence(confidence: float) -> None:
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must lie in (0, 1), got {confidence}")


def historical_var(
    returns: pd.Series | np.ndarray, confidence: float = DEFAULT_CONFIDENCE
) -> float:
    r"""Historical Value-at-Risk, as a positive loss magnitude.

    VaR is a **quantile** of the loss distribution: the loss that is exceeded in
    at most :math:`(1-\alpha)` of scenarios. It says nothing about how bad the
    exceedances are -- that is CVaR's job, and conflating the two understates
    tail risk precisely when it matters.

    With :math:`N` observations and :math:`m = (1-\alpha)N`, this returns the
    :math:`k`-th largest loss where :math:`k = \lceil m \rceil`, which is the
    minimiser of the Rockafellar-Uryasev objective for the empirical sample.

    Returns
    -------
    float
        Positive means a loss (``0.023`` = a 2.3% loss). Negative is possible
        when even the tail of the distribution is profitable.

    Notes
    -----
    Units are those of the input. Daily returns give a **1-day** VaR.
    """
    _check_confidence(confidence)
    losses = _losses_from_returns(returns)
    n = losses.size

    m = (1.0 - confidence) * n
    k = max(1, min(n, int(np.ceil(m))))

    ordered = np.sort(losses)[::-1]  # worst loss first
    return float(ordered[k - 1])


def historical_cvar(
    returns: pd.Series | np.ndarray, confidence: float = DEFAULT_CONFIDENCE
) -> float:
    r"""Historical CVaR / Expected Shortfall, as a positive loss magnitude.

    CVaR is the **average** loss in the worst :math:`(1-\alpha)` fraction of
    scenarios, and is by construction at least as large as VaR.

    This is the exact empirical Rockafellar-Uryasev value. When
    :math:`m = (1-\alpha)N` is not an integer the boundary observation carries a
    *fractional* weight rather than being included or dropped whole:

    .. math::
        \mathrm{CVaR}_\alpha
        = \frac{1}{m}\left[\sum_{i=1}^{k-1} L_{(i)}
                            + \bigl(m - (k-1)\bigr) L_{(k)}\right],
        \qquad k = \lceil m \rceil

    with :math:`L_{(1)} \ge L_{(2)} \ge \dots` the losses in decreasing order.
    Taking a plain mean of the worst :math:`\lceil m \rceil` losses instead
    would understate CVaR, and would not coincide with the optimum of the scalar
    Rockafellar-Uryasev expression -- which matters here, because that optimum is
    exactly what :class:`~src.portfolio.cvar.CVaROptimizer` minimises.

    Returns
    -------
    float
        Positive means a loss. Never less than :func:`historical_var` on the
        same inputs.

    Notes
    -----
    Units are those of the input. Daily returns give a **1-day** CVaR. This is
    not a drawdown: CVaR averages single-period losses, whereas a drawdown
    measures a cumulative peak-to-trough decline over many periods.
    """
    _check_confidence(confidence)
    losses = _losses_from_returns(returns)
    n = losses.size

    m = (1.0 - confidence) * n
    if m >= n:
        return float(losses.mean())

    k = max(1, int(np.ceil(m)))
    ordered = np.sort(losses)[::-1]

    whole = ordered[: k - 1].sum() if k > 1 else 0.0
    fractional = (m - (k - 1)) * ordered[k - 1]
    return float((whole + fractional) / m)


def rockafellar_uryasev_objective(
    losses: np.ndarray | pd.Series,
    threshold: float,
    confidence: float = DEFAULT_CONFIDENCE,
) -> float:
    r"""The scalar Rockafellar-Uryasev objective evaluated at a threshold.

    .. math::
        F_\alpha(z) = z + \frac{1}{(1-\alpha)N} \sum_{s=1}^{N} \max(L_s - z, 0)

    Minimising this over :math:`z` yields :math:`\mathrm{CVaR}_\alpha`, with the
    minimiser at :math:`\mathrm{VaR}_\alpha`. Exposed so that
    :func:`historical_cvar` can be verified against the definition the optimizer
    actually solves, rather than the two being assumed equivalent.

    Takes **losses** (positive = loss), not returns.
    """
    _check_confidence(confidence)
    values = np.asarray(losses, dtype="float64")
    if values.size == 0:
        raise ValueError("loss sample is empty")
    n = values.size
    excess = np.maximum(values - threshold, 0.0).sum()
    return float(threshold + excess / ((1.0 - confidence) * n))


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
    cvar_confidence: float
    daily_var: float
    """1-day historical VaR, positive = loss. Not annualised."""
    daily_cvar: float
    """1-day historical CVaR / Expected Shortfall, positive = loss. Not annualised."""
    average_turnover: float
    annualized_turnover: float
    total_cost: float

    def to_dict(self) -> dict:
        return asdict(self)


def summarize(
    result: BacktestResult,
    frequency: RebalanceFrequency = RebalanceFrequency.QUARTERLY,
    confidence: float = DEFAULT_CONFIDENCE,
) -> PerformanceSummary:
    """Compute every implemented metric for one backtest result.

    The tail metrics are computed from the realised **daily** return series, so
    they are 1-day figures regardless of the rebalancing cadence.
    """
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
        cvar_confidence=confidence,
        daily_var=historical_var(returns, confidence),
        daily_cvar=historical_cvar(returns, confidence),
        average_turnover=average_turnover(result),
        annualized_turnover=annualized_turnover(result, frequency),
        total_cost=result.total_cost,
    )


def comparison_table(
    results: dict[str, BacktestResult] | list[BacktestResult],
    frequency: RebalanceFrequency = RebalanceFrequency.QUARTERLY,
    confidence: float = DEFAULT_CONFIDENCE,
) -> pd.DataFrame:
    """Side-by-side metrics for several strategies, one row each."""
    items = results.values() if isinstance(results, dict) else results
    rows = [summarize(r, frequency, confidence).to_dict() for r in items]
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
