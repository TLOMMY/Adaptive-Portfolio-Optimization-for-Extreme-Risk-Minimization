"""Turn history into model inputs, using only data strictly before a date.

This is the ONLY place that decides what the model is allowed to see, so the
no-look-ahead rule is enforced here: `window_before(t)` never returns the row
for t itself or anything after it.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .universe import ASSETS, CASH


def window_before(returns: pd.DataFrame, t: pd.Timestamp, lookback_days: int) -> pd.DataFrame:
    """The last `lookback_days` trading days of returns strictly before t."""
    hist = returns.loc[: t - pd.Timedelta(days=1)]
    if len(hist) < lookback_days:
        raise ValueError(f"only {len(hist)} days of history before {t.date()}, need {lookback_days}")
    return hist.iloc[-lookback_days:][ASSETS]


def expected_returns(scenarios: pd.DataFrame, shrink: float = 0.5) -> pd.Series:
    """Sample mean daily return, shrunk toward the cross-asset average.

    Raw sample means are the noisiest input to any portfolio optimiser; pulling
    every asset's estimate part-way toward the common mean (shrink=1 means all
    assets get the same expected return) is the standard, cheap defence.
    """
    m = scenarios.mean()
    risky = m.drop(CASH)
    out = (1 - shrink) * risky + shrink * risky.mean()
    out[CASH] = m[CASH]                     # cash is not a noisy estimate; leave it alone
    return out.reindex(m.index)


def ledoit_wolf(x: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf (2004) shrinkage of the sample covariance toward a scaled identity.

    x: n observations x p assets, NOT yet centred.  Returns (covariance, shrinkage
    intensity in [0, 1]).  Same estimator as sklearn.covariance.ledoit_wolf.
    """
    x = np.asarray(x, dtype=float)
    x = x - x.mean(axis=0)
    n, p = x.shape
    emp = x.T @ x / n
    mu = np.trace(emp) / p
    delta = ((emp - mu * np.eye(p)) ** 2).sum() / p           # ||S - mu I||_F^2 / p
    x2 = x ** 2
    beta = ((x2.T @ x2) / n - emp ** 2).sum() / (n * p)        # estimation-error term
    beta = min(beta, delta)
    shrinkage = 0.0 if delta == 0 else beta / delta
    return (1 - shrinkage) * emp + shrinkage * mu * np.eye(p), float(shrinkage)


def covariance(scenarios: pd.DataFrame, method: str = "sample") -> pd.DataFrame:
    """Daily return covariance over the window, with CASH's row and column set to 0.

    method: "sample" (population covariance) or "ledoit_wolf".  Cash is excluded
    from the estimate for the same reason it is excluded from shrinkage: its
    variance is known to be ~0 and must not be pulled toward the stock average.
    """
    risky = scenarios.drop(columns=CASH)
    if method == "sample":
        x = risky.to_numpy() - risky.to_numpy().mean(axis=0)
        cov = x.T @ x / len(x)
    elif method == "ledoit_wolf":
        cov, _ = ledoit_wolf(risky.to_numpy())
    else:
        raise ValueError(f"unknown covariance method {method!r}")
    out = pd.DataFrame(0.0, index=scenarios.columns, columns=scenarios.columns)
    out.loc[risky.columns, risky.columns] = cov
    return out


def cvar_to_vol(cvar_limit: float, alpha: float = 0.95) -> float:
    """Daily volatility with the same CVaR under a normal distribution with zero mean.

    For a normal variable, CVaR_alpha = sigma * phi(z_alpha) / (1 - alpha), where phi
    is the standard normal density and z_alpha its alpha-quantile.  At 95% the
    factor is about 2.06, so a 2% CVaR limit is roughly a 0.97% daily volatility cap.
    """
    z = math.sqrt(2) * _erfinv(2 * alpha - 1)
    phi = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
    return cvar_limit * (1 - alpha) / phi


def _erfinv(y: float) -> float:
    """Inverse error function by Newton's method (enough precision for a quantile)."""
    x = 0.0
    for _ in range(50):
        err = math.erf(x) - y
        if abs(err) < 1e-14:
            break
        x -= err / (2 / math.sqrt(math.pi) * math.exp(-x * x))
    return x


def realised_cvar(weights: pd.Series, scenarios: pd.DataFrame, alpha: float) -> float:
    """Average portfolio loss over the worst (1-alpha) share of scenarios."""
    losses = -(scenarios[weights.index] @ weights)
    k = max(1, int(round((1 - alpha) * len(losses))))
    return float(losses.nlargest(k).mean())
