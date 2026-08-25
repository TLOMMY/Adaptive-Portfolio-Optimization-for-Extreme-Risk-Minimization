"""The project's own model: profile-driven CVaR-constrained MILP (model/cvar.mod)."""

from __future__ import annotations

import pandas as pd

from ..optimiser import MODEL_DIR, Solution, ampl_solve
from .base import Model


class CvarModel(Model):
    key = "cvar"
    name = "CVaR limit"
    blurb = ("Maximises expected return while keeping the average loss on the worst 5% of "
             "historical days under the investor's limit, which tightens as the horizon shrinks.")
    solver = "highs"

    def solve(self, scenarios: pd.DataFrame, mu: pd.Series, params: dict, w_prev: pd.Series) -> Solution:
        sets, p = self.common_sets_and_params(mu, params, w_prev)
        assets = sets["ASSETS"]
        sets["SCENARIOS"] = list(range(len(scenarios)))
        p["r"] = {(s, a): float(v) for s, row in enumerate(scenarios[assets].to_numpy()) for a, v in zip(assets, row)}
        p["alpha"] = params["alpha"]
        p["cvar_limit"] = params["cvar_limit"]
        w, vals, status, dt = ampl_solve(MODEL_DIR / "cvar.mod", self.solver, sets, p, ("cvar", "turnover"))
        return self.finish(w, mu, scenarios, params, vals["cvar"], vals["turnover"], status, dt)
