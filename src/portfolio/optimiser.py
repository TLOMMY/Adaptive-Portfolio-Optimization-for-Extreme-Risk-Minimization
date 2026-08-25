"""Thin amplpy wrapper around model/portfolio.mod.

solve(...) takes pandas objects in, returns a Solution out, and knows nothing
about dates or backtests.  Everything time-related lives in estimate.py and
backtest.py so the look-ahead rule is enforced in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time

import pandas as pd
from amplpy import AMPL, OutputHandler, modules

from .estimate import realised_cvar
from .universe import CASH, SECTOR

MODEL = Path(__file__).resolve().parents[2] / "model" / "portfolio.mod"

_ampl: AMPL | None = None


class _Quiet(OutputHandler):
    def output(self, kind, msg):
        pass


def _get_ampl() -> AMPL:
    global _ampl
    if _ampl is None:
        modules.load()
        _ampl = AMPL()
        _ampl.set_output_handler(_Quiet())
        _ampl.option["solver"] = "highs"
        _ampl.option["solver_msg"] = 0
        _ampl.option["highs_options"] = "outlev=0 mip_rel_gap=1e-4 timelim=60"
    return _ampl


@dataclass
class Solution:
    weights: pd.Series
    exp_return: float          # expected daily return
    cvar: float                # realised CVaR of these weights over the scenarios
    turnover: float            # sum of |trades| as a fraction of portfolio value
    status: str
    solve_time: float
    n_holdings: int = field(default=0)


def solve(
    mu: pd.Series,
    scenarios: pd.DataFrame,
    params: dict,
    w_prev: pd.Series | None = None,
) -> Solution:
    """Solve one rebalance decision.

    mu:        expected daily return per asset
    scenarios: rows = historical days, columns = assets, values = daily returns
    params:    the investor profile (see profiles.py) with keys
               alpha, cvar_limit, lambda_risk, w_max (float or Series),
               w_min_pos, max_holdings, sector_cap (dict), cash_min, cost_rate, hold_days
    w_prev:    current weights (defaults to all cash)
    """
    assets = list(mu.index)
    sectors = sorted({SECTOR[a] for a in assets})
    if w_prev is None:
        w_prev = pd.Series(0.0, index=assets)
        w_prev[CASH] = 1.0
    w_max = params["w_max"]
    if not isinstance(w_max, pd.Series):
        w_max = pd.Series(float(w_max), index=assets)
    w_max = w_max.copy()
    w_max[CASH] = 1.0
    for a in params.get("exclude", []):
        if a in w_max.index:
            w_max[a] = 0.0

    ampl = _get_ampl()
    ampl.reset()
    ampl.read(str(MODEL))
    ampl.set["ASSETS"] = assets
    ampl.set["SCENARIOS"] = list(range(len(scenarios)))
    ampl.set["SECTORS"] = sectors
    ampl.param["sector"] = {a: SECTOR[a] for a in assets}
    ampl.param["is_cash"] = {a: int(a == CASH) for a in assets}
    ampl.param["mu"] = mu.to_dict()
    ampl.param["r"] = {(s, a): float(v) for s, row in enumerate(scenarios[assets].to_numpy()) for a, v in zip(assets, row)}
    for k in ("alpha", "cvar_limit", "lambda_risk", "w_min_pos", "max_holdings", "cash_min", "cost_rate", "hold_days"):
        ampl.param[k] = params[k]
    ampl.param["w_max"] = w_max.to_dict()
    ampl.param["sector_cap"] = {k: params["sector_cap"].get(k, 1.0) for k in sectors}
    ampl.param["w_prev"] = w_prev.reindex(assets).fillna(0.0).to_dict()

    t0 = time.perf_counter()
    ampl.solve()
    dt = time.perf_counter() - t0
    status = ampl.solve_result
    if status != "solved":
        raise RuntimeError(f"solver returned {status}")

    w = pd.Series(ampl.var["w"].to_dict()).reindex(assets)
    w[w.abs() < 1e-6] = 0.0
    return Solution(
        weights=w,
        exp_return=float(ampl.get_value("exp_return")),
        cvar=realised_cvar(w, scenarios, params["alpha"]),
        turnover=float(ampl.get_value("turnover")),
        status=status,
        solve_time=dt,
        n_holdings=int((w.drop(CASH) > 0).sum()),
    )
