"""Robust mean-variance: worst case over an ellipsoid of plausible expected returns
(model/robust.mod).  Same variance cap as Markowitz; Ledoit-Wolf covariance.

kappa (the ellipsoid radius in standard errors) was checked on 2011-2015 like the other
hyperparameters (see data/processed/tuning_robust.json): Sharpe falls monotonically as
kappa grows, so the selection rule would choose kappa -> 0, i.e. plain Markowitz.  We keep
the conventional kappa = 1 so the lab shows what one standard error of caution costs."""

from __future__ import annotations

import math

import pandas as pd

from ..estimate import covariance, cvar_to_vol
from ..optimiser import MODEL_DIR, Solution, ampl_solve
from .base import SCALE2, Model


class RobustModel(Model):
    key = "robust"
    name = "Robust mean-variance"
    blurb = ("Assumes the expected-return estimates are wrong by up to one standard error in the "
             "least favourable direction and maximises that worst case, under the same variance cap.")
    solver = "gurobi"

    def __init__(self, kappa: float = 1.0, cov_method: str = "ledoit_wolf"):
        self.kappa = kappa
        self.cov_method = cov_method

    def solve(self, scenarios: pd.DataFrame, mu: pd.Series, params: dict, w_prev: pd.Series) -> Solution:
        sets, p = self.common_sets_and_params(mu, params, w_prev)
        sigma = covariance(scenarios, self.cov_method).loc[sets["ASSETS"], sets["ASSETS"]]
        p["Sigma"] = self.matrix_param(sigma * SCALE2)          # percent^2 units, see base.SCALE2
        p["Omega"] = self.matrix_param(sigma * SCALE2 / len(scenarios))
        p["kappa"] = self.kappa
        p["var_limit"] = cvar_to_vol(params["cvar_limit"], params["alpha"]) ** 2 * SCALE2
        w, vals, status, dt = ampl_solve(MODEL_DIR / "robust.mod", self.solver, sets, p, ("variance", "turnover"))
        return self.finish(w, mu, scenarios, params, math.sqrt(max(vals["variance"], 0.0) / SCALE2), vals["turnover"], status, dt)
