"""Markowitz mean-variance with the investor's constraints (model/markowitz.mod).

The investor's CVaR limit is translated to a variance cap with estimate.cvar_to_vol.
Two variants differ only in the covariance estimate: plain sample covariance, or
Ledoit-Wolf shrinkage toward a scaled identity.
"""

from __future__ import annotations

import math

import pandas as pd

from ..estimate import covariance, cvar_to_vol
from ..optimiser import MODEL_DIR, Solution, ampl_solve
from .base import SCALE2, Model


class MarkowitzModel(Model):
    solver = "gurobi"

    def __init__(self, cov_method: str = "sample"):
        self.cov_method = cov_method
        if cov_method == "sample":
            self.key, self.name = "markowitz", "Markowitz"
            self.blurb = ("Classic mean-variance: maximises expected return subject to a cap on portfolio "
                          "variance, using the plain sample covariance of the last three years.")
        else:
            self.key, self.name = "markowitz_lw", "Markowitz + Ledoit-Wolf"
            self.blurb = ("Mean-variance with a Ledoit-Wolf shrunk covariance, which pulls the noisy "
                          "sample covariance toward a simpler structure before optimising.")

    def solve(self, scenarios: pd.DataFrame, mu: pd.Series, params: dict, w_prev: pd.Series) -> Solution:
        sets, p = self.common_sets_and_params(mu, params, w_prev)
        sigma = covariance(scenarios, self.cov_method).loc[sets["ASSETS"], sets["ASSETS"]]
        p["Sigma"] = self.matrix_param(sigma * SCALE2)          # percent^2 units, see base.SCALE2
        p["var_limit"] = cvar_to_vol(params["cvar_limit"], params["alpha"]) ** 2 * SCALE2
        w, vals, status, dt = ampl_solve(MODEL_DIR / "markowitz.mod", self.solver, sets, p, ("variance", "turnover"))
        return self.finish(w, mu, scenarios, params, math.sqrt(max(vals["variance"], 0.0) / SCALE2), vals["turnover"], status, dt)
