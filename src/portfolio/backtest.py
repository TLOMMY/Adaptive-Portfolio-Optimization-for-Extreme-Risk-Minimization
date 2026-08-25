"""Walk-forward backtest of one investor profile under one model.

Timeline convention (the only one that matters for honesty):
  * On trading day t the portfolio first earns day t's returns.
  * Then, if a trigger fires, the model is re-solved using returns STRICTLY
    BEFORE t (see estimate.window_before) and the trades execute at day t's
    close, paying proportional costs (charged pro rata across all positions).
  * The new weights earn returns from day t+1.

Triggers (any one fires a re-solve, subject to a cooldown):
  first day | calendar (max_days_between) | drift (sum |w - target| >= drift_trigger)
  | volatility regime (21-day market vol / 252-day market vol >= vol_trigger)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .estimate import expected_returns, window_before
from .metrics import summarise
from .models import STORY_MODEL, Model, get_model
from .optimiser import Solution
from .profiles import Profile
from .universe import ASSETS, BENCHMARK, CASH, TICKERS


@dataclass
class BacktestResult:
    profile: Profile
    model: Model
    value: pd.Series                      # daily portfolio value
    weights: pd.DataFrame                 # daily weights (date x asset)
    benchmark: pd.Series                  # SPY buy-and-hold, same starting value
    solves: pd.DataFrame                  # one row per re-solve
    trades: pd.DataFrame                  # one row per asset traded per re-solve
    metrics: dict = field(default_factory=dict)
    benchmark_metrics: dict = field(default_factory=dict)


def market_vol_ratio(returns: pd.DataFrame, t: pd.Timestamp) -> float:
    """Short-run vs long-run volatility of the equal-weight universe, data < t."""
    hist = returns.loc[: t - pd.Timedelta(days=1), TICKERS].mean(axis=1)
    short, long = hist.iloc[-21:].std(), hist.iloc[-252:].std()
    return float(short / long) if long > 0 else 1.0


def run_backtest(
    profile: Profile,
    data: dict[str, pd.DataFrame],
    model: Model | str = STORY_MODEL,
    start: str = "2016-01-04",
    end: str = "2025-12-31",
    initial: float = 100_000.0,
    verbose: bool = False,
) -> BacktestResult:
    if isinstance(model, str):
        model = get_model(model)
    returns = data["returns"]
    rf = data["rf"]["rf"]
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    horizon_end = start_ts + pd.DateOffset(years=int(profile.horizon_years))
    end_ts = min(end_ts, horizon_end)
    days = returns.loc[start_ts:end_ts].index

    holdings = pd.Series(0.0, index=ASSETS)
    holdings[CASH] = initial
    target = holdings / initial
    last_solve_day = None
    values, weights, solves, trades = [], [], [], []

    for i, t in enumerate(days):
        if i > 0:                                      # earn today's returns
            holdings = holdings * (1 + returns.loc[t, ASSETS])
        total = holdings.sum()
        w = holdings / total

        # --- decide whether to re-solve -------------------------------------
        reason = None
        since = (i - last_solve_day) if last_solve_day is not None else None
        if last_solve_day is None:
            reason = "start"
        elif since >= profile.min_days_between:
            drift = float((w - target).abs().sum())
            vr = market_vol_ratio(returns, t)
            if since >= profile.max_days_between:
                reason = "calendar"
            elif drift >= profile.drift_trigger:
                reason = "drift"
            elif vr >= profile.vol_trigger:
                reason = "volatility"

        if reason:
            years_left = (horizon_end - t).days / 365.25
            scen = window_before(returns, t, profile.lookback_days)
            mu = expected_returns(scen, profile.shrink)
            params = profile.params_at(years_left)
            sol: Solution = model.solve(scen, mu, params, w_prev=w)
            new_holdings = sol.weights * total
            traded = (new_holdings - holdings).abs().sum()
            cost = profile.cost_rate * traded
            new_holdings *= 1 - cost / total       # costs come out of every position pro rata
            for a in ASSETS:
                if abs(sol.weights[a] - w[a]) > 1e-4:
                    trades.append({"date": t, "asset": a, "from": float(w[a]), "to": float(sol.weights[a])})
            solves.append({
                "date": t, "reason": reason, "years_left": years_left,
                "cvar_limit": params["cvar_limit"], "exp_return_ann": sol.exp_return * 252,
                "cvar": sol.cvar, "risk": sol.risk, "turnover": sol.turnover, "cost": cost,
                "n_holdings": sol.n_holdings, "solve_time": sol.solve_time,
            })
            holdings, target, last_solve_day = new_holdings, sol.weights, i
            total = holdings.sum()
            w = holdings / total
            if verbose:
                print(f"{t.date()} {reason:10s} limit={params['cvar_limit']:.2%} "
                      f"cvar={sol.cvar:.2%} holdings={sol.n_holdings} cost=${cost:,.0f} value=${total:,.0f}")

        values.append(total)
        weights.append(w)

    value = pd.Series(values, index=days, name="value")
    weights_df = pd.DataFrame(weights, index=days)
    bench_r = returns.loc[days, BENCHMARK]
    benchmark = initial * (1 + bench_r).cumprod() / (1 + bench_r.iloc[0])
    res = BacktestResult(
        profile=profile, model=model, value=value, weights=weights_df, benchmark=benchmark,
        solves=pd.DataFrame(solves), trades=pd.DataFrame(trades),
    )
    res.metrics = summarise(value, rf)
    res.benchmark_metrics = summarise(benchmark, rf)
    return res
