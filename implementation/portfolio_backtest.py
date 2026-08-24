"""Small, model-independent portfolio backtesting utilities.

The module intentionally separates fitting from evaluation. A model receives
only training returns and returns one weight per asset. The backtester then
evaluates those fixed weights on a later test period.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


PERIODS_PER_YEAR = 252


@dataclass(frozen=True)
class BacktestWindow:
    """A half-open training interval followed by an inclusive test interval."""

    name: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def validate_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize an adjusted-close price table."""

    if not isinstance(prices, pd.DataFrame) or prices.empty:
        raise ValueError("prices must be a non-empty pandas DataFrame")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise TypeError("prices.index must be a pandas DatetimeIndex")
    if prices.index.has_duplicates:
        raise ValueError("prices.index must not contain duplicate dates")
    if prices.columns.empty or prices.columns.duplicated().any():
        raise ValueError("prices must have unique asset columns")

    normalized = prices.copy().sort_index()
    normalized = normalized.apply(pd.to_numeric, errors="raise")
    if not np.isfinite(normalized.to_numpy(dtype=float)).all():
        raise ValueError("prices must contain only finite values")
    if (normalized <= 0).any().any():
        raise ValueError("prices must be strictly positive")
    return normalized


def compute_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute aligned simple returns from adjusted-close prices."""

    normalized = validate_prices(prices)
    returns = normalized.pct_change().dropna(how="any")
    if returns.empty:
        raise ValueError("prices do not contain enough rows to compute returns")
    return returns


def _select_range(
    returns: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    inclusive_end: bool,
) -> pd.DataFrame:
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if end < start:
        raise ValueError("range end must not precede range start")
    if inclusive_end:
        selected = returns.loc[(returns.index >= start) & (returns.index <= end)]
    else:
        selected = returns.loc[(returns.index >= start) & (returns.index < end)]
    if selected.empty:
        raise ValueError(f"no returns available in range {start.date()} to {end.date()}")
    return selected


def split_train_test(
    returns: pd.DataFrame,
    train_start: str | pd.Timestamp,
    train_end: str | pd.Timestamp,
    test_start: str | pd.Timestamp,
    test_end: str | pd.Timestamp,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return non-overlapping train and test returns.

    The training end is exclusive. The test start must be on or after it,
    preventing a row from being used both to fit and to evaluate a model.
    """

    if pd.Timestamp(test_start) < pd.Timestamp(train_end):
        raise ValueError("test_start must be on or after the exclusive train_end")
    train = _select_range(returns, train_start, train_end, inclusive_end=False)
    test = _select_range(returns, test_start, test_end, inclusive_end=True)
    if train.index.intersection(test.index).size:
        raise ValueError("training and testing returns overlap")
    return train, test


def equal_weight_weights(assets: Sequence[str]) -> pd.Series:
    """Return a labelled equal-weight portfolio."""

    assets = list(assets)
    if not assets:
        raise ValueError("at least one asset is required")
    return pd.Series(1.0 / len(assets), index=assets, dtype=float)


def normalize_weights(
    weights: Mapping[str, float] | Sequence[float] | pd.Series,
    assets: Sequence[str],
    *,
    allow_short: bool = False,
) -> pd.Series:
    """Align, validate, and normalize a model's output weights."""

    assets = list(assets)
    if isinstance(weights, pd.Series):
        series = weights.astype(float).reindex(assets)
    elif isinstance(weights, Mapping):
        series = pd.Series(weights, dtype=float).reindex(assets)
    else:
        values = np.asarray(weights, dtype=float).reshape(-1)
        if len(values) != len(assets):
            raise ValueError("weight vector length does not match the asset universe")
        series = pd.Series(values, index=assets, dtype=float)

    if series.isna().any() or not np.isfinite(series.to_numpy()).all():
        raise ValueError("weights must contain one finite value per asset")
    if not allow_short and (series < -1e-10).any():
        raise ValueError("negative weights are not allowed for a long-only backtest")
    total = float(series.sum())
    if total <= 0:
        raise ValueError("weights must have a positive total")
    series = series / total
    if not np.isclose(series.sum(), 1.0, atol=1e-8):
        raise ValueError("weights could not be normalized to one")
    return series


def max_drawdown(portfolio_returns: pd.Series) -> float:
    """Return the maximum peak-to-trough loss as a negative fraction."""

    wealth = (1.0 + portfolio_returns).cumprod()
    drawdowns = wealth / wealth.cummax() - 1.0
    return float(drawdowns.min())


def conditional_value_at_risk(
    portfolio_returns: pd.Series, alpha: float = 0.95
) -> float:
    """Return historical CVaR as a positive average loss fraction."""

    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    losses = -portfolio_returns.to_numpy(dtype=float)
    quantile = float(np.quantile(losses, alpha))
    tail = losses[losses >= quantile]
    return float(tail.mean()) if len(tail) else quantile


def evaluate_weights(
    weights: Mapping[str, float] | Sequence[float] | pd.Series,
    test_returns: pd.DataFrame,
    *,
    risk_free_rate: float = 0.0,
    periods_per_year: int = PERIODS_PER_YEAR,
    cvar_alpha: float = 0.95,
) -> dict[str, float]:
    """Evaluate fixed weights using test-period returns only."""

    if test_returns.empty:
        raise ValueError("test_returns must not be empty")
    aligned = normalize_weights(weights, test_returns.columns)
    portfolio = test_returns.loc[:, aligned.index].dot(aligned)
    cumulative_return = float((1.0 + portfolio).prod() - 1.0)
    volatility = float(portfolio.std(ddof=1) * np.sqrt(periods_per_year))
    annualized_return = float((1.0 + cumulative_return) ** (periods_per_year / len(portfolio)) - 1.0)
    excess = portfolio - risk_free_rate / periods_per_year
    std = float(portfolio.std(ddof=1))
    sharpe = float(excess.mean() / std * np.sqrt(periods_per_year)) if std > 0 else 0.0
    return {
        "cumulative_return": cumulative_return,
        "annualized_return": annualized_return,
        "annualized_volatility": volatility,
        "maximum_drawdown": max_drawdown(portfolio),
        "sharpe_ratio": sharpe,
        "cvar": conditional_value_at_risk(portfolio, alpha=cvar_alpha),
        "test_observations": float(len(portfolio)),
    }


FitModel = Callable[[pd.DataFrame, Optional[Mapping[str, object]]], object]


def equal_weight_model(
    train_returns: pd.DataFrame,
    profile_config: Optional[Mapping[str, object]] = None,
) -> pd.Series:
    """Adapter matching the future optimizer interface."""

    del profile_config
    return equal_weight_weights(train_returns.columns)


def run_backtest(
    returns: pd.DataFrame,
    windows: Iterable[BacktestWindow],
    fit_model: FitModel,
    *,
    model_name: str,
    profile_name: str = "not_applicable",
    profile_config: Optional[Mapping[str, object]] = None,
    risk_free_rate: float = 0.0,
    periods_per_year: int = PERIODS_PER_YEAR,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run one model over explicit windows and return metrics and weights.

    `fit_model` is called once per window with only the corresponding
    training returns. The returned weights are never refit on test data.
    """

    if not isinstance(returns, pd.DataFrame) or returns.empty:
        raise ValueError("returns must be a non-empty DataFrame")
    if not isinstance(returns.index, pd.DatetimeIndex):
        raise TypeError("returns.index must be a DatetimeIndex")
    returns = returns.sort_index().copy()
    metric_rows: list[dict[str, object]] = []
    weight_rows: list[dict[str, object]] = []

    for window in windows:
        train, test = split_train_test(
            returns,
            window.train_start,
            window.train_end,
            window.test_start,
            window.test_end,
        )
        raw_weights = fit_model(train, profile_config)
        weights = normalize_weights(raw_weights, train.columns)
        metrics = evaluate_weights(
            weights,
            test,
            risk_free_rate=risk_free_rate,
            periods_per_year=periods_per_year,
        )
        metric_rows.append(
            {
                "model": model_name,
                "profile": profile_name,
                "evaluation_period": window.name,
                "train_start": train.index.min(),
                "train_end_exclusive": pd.Timestamp(window.train_end),
                "test_start": test.index.min(),
                "test_end": test.index.max(),
                **metrics,
            }
        )
        for asset, weight in weights.items():
            weight_rows.append(
                {
                    "model": model_name,
                    "profile": profile_name,
                    "evaluation_period": window.name,
                    "rebalance_date": test.index.min(),
                    "asset": asset,
                    "weight": float(weight),
                }
            )

    return pd.DataFrame(metric_rows), pd.DataFrame(weight_rows)
