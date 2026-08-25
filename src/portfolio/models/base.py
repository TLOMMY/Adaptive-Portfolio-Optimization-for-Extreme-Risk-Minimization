"""The interface every portfolio model implements.

A Model turns (scenarios, expected returns, investor parameters, current weights)
into a Solution.  backtest.py depends only on this interface, so adding a model
means one new file here and one line in models/__init__.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from ..estimate import realised_cvar
from ..optimiser import Solution
from ..universe import CASH, SECTOR


# Quadratic models receive covariances in percent^2 (x 1e4).  Daily variances are ~1e-5,
# which is the same order as a solver's absolute feasibility tolerance; in percent units
# they are ~0.1 and the tolerance is negligible.  Only the AMPL side sees scaled numbers.
SCALE2 = 1e4


class Model(ABC):
    key: str                    # used in file names and the site
    name: str                   # shown to users
    blurb: str                  # one plain-language sentence on how it decides
    solver: str | None = None   # None for models that need no solver

    @abstractmethod
    def solve(self, scenarios: pd.DataFrame, mu: pd.Series, params: dict, w_prev: pd.Series) -> Solution:
        """One rebalance decision.  `params` is Profile.params_at(years_left)."""

    # ---- helpers shared by the AMPL-backed models ---------------------------
    @staticmethod
    def common_sets_and_params(mu: pd.Series, params: dict, w_prev: pd.Series) -> tuple[dict, dict]:
        """Fill everything declared in model/common.mod from the profile parameters."""
        assets = list(mu.index)
        sectors = sorted({SECTOR[a] for a in assets})
        w_max = params["w_max"]
        w_max = w_max.copy() if isinstance(w_max, pd.Series) else pd.Series(float(w_max), index=assets)
        w_max[CASH] = 1.0
        for a in params.get("exclude", []):
            if a in w_max.index:
                w_max[a] = 0.0
        sets = {"ASSETS": assets, "SECTORS": sectors}
        p = {
            "sector": {a: SECTOR[a] for a in assets},
            "is_cash": {a: int(a == CASH) for a in assets},
            "mu": mu.to_dict(),
            "w_max": w_max.to_dict(),
            "sector_cap": {k: params["sector_cap"].get(k, 1.0) for k in sectors},
            "w_prev": w_prev.reindex(assets).fillna(0.0).to_dict(),
        }
        for k in ("lambda_risk", "w_min_pos", "max_holdings", "cash_min", "cost_rate", "hold_days"):
            p[k] = params[k]
        return sets, p

    @staticmethod
    def finish(w: pd.Series, mu: pd.Series, scenarios: pd.DataFrame, params: dict,
               risk: float, turnover: float, status: str, dt: float) -> Solution:
        w = w.reindex(mu.index).fillna(0.0)
        return Solution(
            weights=w,
            exp_return=float(mu @ w),
            risk=risk,
            cvar=realised_cvar(w, scenarios, params["alpha"]),
            turnover=turnover,
            status=status,
            solve_time=dt,
            n_holdings=int((w.drop(CASH) > 0).sum()),
        )

    @staticmethod
    def matrix_param(m: pd.DataFrame) -> dict:
        return {(i, j): float(v) for i, row in zip(m.index, m.to_numpy()) for j, v in zip(m.columns, row)}
