"""Turn history into model inputs, using only data strictly before a date.

This is the ONLY place that decides what the model is allowed to see, so the
no-look-ahead rule is enforced here: `window_before(t)` never returns the row
for t itself or anything after it.
"""

from __future__ import annotations

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


def realised_cvar(weights: pd.Series, scenarios: pd.DataFrame, alpha: float) -> float:
    """Average portfolio loss over the worst (1-alpha) share of scenarios."""
    losses = -(scenarios[weights.index] @ weights)
    k = max(1, int(round((1 - alpha) * len(losses))))
    return float(losses.nlargest(k).mean())
