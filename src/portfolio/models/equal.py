"""Equal weight (1/N): the naive benchmark that is famously hard to beat out of sample
(DeMiguel, Garlappi & Uppal 2009).  Ignores every investor rule except exclusions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..optimiser import Solution
from ..universe import CASH
from .base import Model


class EqualWeightModel(Model):
    key = "equal"
    name = "Equal weight (1/N)"
    blurb = ("Puts the same amount in every allowed stock and fund and rebalances back to equal "
             "whenever a trigger fires; no estimates, no optimisation.")
    solver = None

    def solve(self, scenarios: pd.DataFrame, mu: pd.Series, params: dict, w_prev: pd.Series) -> Solution:
        allowed = [a for a in mu.index if a != CASH and a not in params.get("exclude", [])]
        w = pd.Series(0.0, index=mu.index)
        w[allowed] = 1.0 / len(allowed)
        turnover = float((w - w_prev.reindex(mu.index).fillna(0.0)).abs().sum())
        daily = scenarios[mu.index] @ w
        return self.finish(w, mu, scenarios, params, float(np.std(daily)), turnover, "solved", 0.0)
