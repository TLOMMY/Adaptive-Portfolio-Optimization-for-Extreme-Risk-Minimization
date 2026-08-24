"""Expected-return estimation.

The project uses **one** estimator for the main experiment: the sample mean of
daily simple returns over the configured lookback window, annualised by the
convention in ``config.settings``.  Alternative estimators (EWMA, James-Stein
shrinkage) are deferred to a sensitivity analysis and are deliberately absent
here, so that every model in the comparison is fed identically constructed
inputs and no result depends on an estimator choice made mid-experiment.

Estimators take a :class:`~src.data.window.MarketDataView`, never a price panel.
That is what makes them incapable of observing data after the decision date.
"""

from __future__ import annotations

import pandas as pd

from src.config.settings import TRADING_DAYS_PER_YEAR
from src.data.window import MarketDataView

ESTIMATOR_NAME = "sample_mean"


def sample_mean_returns(
    view: MarketDataView,
    lookback_days: int,
    annualize: bool = True,
) -> pd.Series:
    r"""Annualised expected returns from the sample mean of daily returns.

    .. math::
        \hat\mu_i = \frac{252}{T} \sum_{t=1}^{T} r_{i,t}

    where :math:`r_{i,t}` are the simple daily returns of asset *i* over the
    ``lookback_days`` sessions ending at the view's decision date.

    Annualisation is arithmetic (``daily mean x 252``), matching the covariance
    convention so that :math:`\mu` and :math:`\Sigma` are expressed in
    consistent units. Note this is *not* a compounded (geometric) annual return;
    it is the annualised expectation of the one-period return, which is the
    quantity a mean-variance objective is defined over.

    Parameters
    ----------
    view
        Market data truncated at the decision date.
    lookback_days
        Number of daily returns to estimate from.
    annualize
        When False, returns the daily mean instead.
    """
    if lookback_days < 2:
        raise ValueError(f"lookback_days must be at least 2, got {lookback_days}")

    returns = view.returns(lookback_days)
    mu = returns.mean()

    if annualize:
        mu = mu * TRADING_DAYS_PER_YEAR
    return mu.rename("expected_return").astype("float64")
