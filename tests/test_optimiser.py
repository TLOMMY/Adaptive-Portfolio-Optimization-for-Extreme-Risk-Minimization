import pandas as pd
import pytest

from portfolio.data import load_dataset
from portfolio.estimate import expected_returns, window_before
from portfolio.optimiser import solve
from portfolio.universe import CASH

BASE = dict(alpha=0.95, lambda_risk=0.0, w_max=0.10, w_min_pos=0.02, max_holdings=15,
            sector_cap={}, cash_min=0.0, cost_rate=0.001, hold_days=21)


@pytest.fixture(scope="module")
def inputs():
    d = load_dataset()
    scen = window_before(d["returns"], pd.Timestamp("2016-01-04"), 756)
    return expected_returns(scen), scen


def test_no_lookahead(inputs):
    _, scen = inputs
    assert scen.index.max() < pd.Timestamp("2016-01-04")
    assert len(scen) == 756


def test_solution_respects_constraints(inputs):
    mu, scen = inputs
    sol = solve(mu, scen, {**BASE, "cvar_limit": 0.015})
    w = sol.weights
    assert abs(w.sum() - 1) < 1e-6
    assert (w.drop(CASH) <= 0.10 + 1e-6).all()
    held = w.drop(CASH)[w.drop(CASH) > 0]
    assert (held >= 0.02 - 1e-6).all() and len(held) <= 15
    assert sol.cvar <= 0.015 + 1e-6


def test_tighter_limit_means_less_risk_and_return(inputs):
    mu, scen = inputs
    tight = solve(mu, scen, {**BASE, "cvar_limit": 0.010})
    loose = solve(mu, scen, {**BASE, "cvar_limit": 0.020})
    assert tight.cvar <= loose.cvar + 1e-6
    assert tight.exp_return <= loose.exp_return + 1e-9
