"""The single entry point for turning a market view into optimizer inputs.

Every optimizer estimates its parameters through :func:`estimate_parameters`, so
all models in a comparison are fed identically constructed inputs from the same
window.  A difference in realised outcome between two models is then attributable
to the models, not to how their inputs were built.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.data.window import MarketDataView
from src.estimation import covariance as cov_module
from src.estimation import expected_returns as mu_module


@dataclass(frozen=True, slots=True)
class EstimatedParameters:
    """Parameters estimated at one decision date, in annualised units.

    Attributes
    ----------
    expected_returns
        Annualised expected returns, indexed by ticker.
    covariance
        Annualised covariance matrix, symmetric and positive semidefinite.
    tickers
        Asset order. ``expected_returns`` and ``covariance`` share it.
    n_observations
        Number of daily returns the estimates were computed from.
    window_start, window_end
        First and last date of the estimation window. ``window_end`` never
        exceeds the decision date.
    as_of
        The decision date these parameters belong to.
    shrinkage
        Ledoit-Wolf shrinkage intensity actually applied.
    """

    expected_returns: pd.Series
    covariance: pd.DataFrame
    tickers: list[str]
    n_observations: int
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    as_of: pd.Timestamp
    shrinkage: float

    @property
    def mu(self) -> np.ndarray:
        """Expected returns as a 1-D array in ``tickers`` order."""
        return self.expected_returns.reindex(self.tickers).to_numpy(dtype="float64")

    @property
    def sigma(self) -> np.ndarray:
        """Covariance as a 2-D array in ``tickers`` order."""
        return self.covariance.reindex(
            index=self.tickers, columns=self.tickers
        ).to_numpy(dtype="float64")

    @property
    def volatilities(self) -> pd.Series:
        """Annualised standard deviation per asset."""
        return pd.Series(
            np.sqrt(np.diag(self.sigma)), index=self.tickers, name="volatility"
        )

    def portfolio_return(self, weights: pd.Series | np.ndarray) -> float:
        """Estimated annualised portfolio return for a weight vector."""
        w = self._as_array(weights)
        return float(self.mu @ w)

    def portfolio_variance(self, weights: pd.Series | np.ndarray) -> float:
        """Estimated annualised portfolio variance for a weight vector."""
        w = self._as_array(weights)
        return float(w @ self.sigma @ w)

    def portfolio_volatility(self, weights: pd.Series | np.ndarray) -> float:
        return float(np.sqrt(max(self.portfolio_variance(weights), 0.0)))

    def _as_array(self, weights: pd.Series | np.ndarray) -> np.ndarray:
        if isinstance(weights, pd.Series):
            return weights.reindex(self.tickers).to_numpy(dtype="float64")
        return np.asarray(weights, dtype="float64")

    def summary(self) -> dict[str, Any]:
        """Compact record for the diagnostics audit trail."""
        return {
            "n_observations": self.n_observations,
            "window_start": str(self.window_start.date()),
            "window_end": str(self.window_end.date()),
            "shrinkage": round(self.shrinkage, 6),
            "mu_estimator": mu_module.ESTIMATOR_NAME,
            "covariance_estimator": cov_module.ESTIMATOR_NAME,
        }


def estimate_parameters(view: MarketDataView, lookback_days: int) -> EstimatedParameters:
    """Estimate annualised mu and Sigma from a truncated market view.

    The window is the ``lookback_days`` daily returns ending at the view's
    decision date. Because the view contains nothing after that date, neither
    estimate can incorporate future information.
    """
    returns = view.returns(lookback_days)
    mu = mu_module.sample_mean_returns(view, lookback_days, annualize=True)
    sigma, shrinkage = cov_module.ledoit_wolf_covariance(
        view, lookback_days, annualize=True
    )

    return EstimatedParameters(
        expected_returns=mu,
        covariance=sigma,
        tickers=list(returns.columns),
        n_observations=len(returns),
        window_start=returns.index[0],
        window_end=returns.index[-1],
        as_of=view.as_of,
        shrinkage=shrinkage,
    )
