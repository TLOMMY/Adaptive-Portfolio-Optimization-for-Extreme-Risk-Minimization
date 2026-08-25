"""Performance metrics from a daily value series.  All annualisation uses 252 days."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def summarise(value: pd.Series, rf_daily: pd.Series | None = None) -> dict:
    r = value.pct_change().dropna()
    years = (value.index[-1] - value.index[0]).days / 365.25
    cagr = (value.iloc[-1] / value.iloc[0]) ** (1 / years) - 1
    vol = r.std() * np.sqrt(TRADING_DAYS)
    excess = r - (rf_daily.reindex(r.index).fillna(0.0) if rf_daily is not None else 0.0)
    sharpe = excess.mean() / r.std() * np.sqrt(TRADING_DAYS) if r.std() > 0 else 0.0
    downside = r[r < 0].std() * np.sqrt(TRADING_DAYS)
    sortino = excess.mean() * TRADING_DAYS / downside if downside > 0 else 0.0
    dd = value / value.cummax() - 1
    monthly = value.resample("ME").last().pct_change().dropna()
    k = max(1, int(round(0.05 * len(r))))
    return {
        "start_value": float(value.iloc[0]),
        "end_value": float(value.iloc[-1]),
        "total_return": float(value.iloc[-1] / value.iloc[0] - 1),
        "cagr": float(cagr),
        "volatility": float(vol),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": float(dd.min()),
        "max_drawdown_date": str(dd.idxmin().date()),
        "worst_month": float(monthly.min()),
        "best_month": float(monthly.max()),
        "cvar_95_daily": float((-r).nlargest(k).mean()),
        "years": float(years),
    }
