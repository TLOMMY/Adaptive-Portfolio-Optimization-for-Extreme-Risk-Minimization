import numpy as np
import pandas as pd
import pytest

from portfolio.data import load_dataset
from portfolio.estimate import covariance, cvar_to_vol, expected_returns, ledoit_wolf, window_before
from portfolio.models import MODELS
from portfolio.universe import CASH

BASE = dict(alpha=0.95, lambda_risk=0.0, w_max=0.10, w_min_pos=0.02, max_holdings=15,
            sector_cap={"Energy": 0.05}, cash_min=0.0, cost_rate=0.001, hold_days=21, exclude=["PM"])
OPTIMISERS = [k for k, m in MODELS.items() if m.solver is not None]


@pytest.fixture(scope="module")
def inputs():
    d = load_dataset()
    scen = window_before(d["returns"], pd.Timestamp("2016-01-04"), 756)
    return expected_returns(scen), scen


def all_cash(mu):
    w = pd.Series(0.0, index=mu.index)
    w[CASH] = 1.0
    return w


def test_no_lookahead(inputs):
    _, scen = inputs
    assert scen.index.max() < pd.Timestamp("2016-01-04")
    assert len(scen) == 756


def test_cvar_to_vol_normal_factor():
    assert cvar_to_vol(0.02, 0.95) == pytest.approx(0.02 / 2.0627, rel=1e-3)


def test_ledoit_wolf_is_valid_covariance(inputs):
    _, scen = inputs
    cov, shrinkage = ledoit_wolf(scen.drop(columns=CASH).to_numpy())
    assert 0.0 < shrinkage < 1.0
    assert np.allclose(cov, cov.T)
    assert np.linalg.eigvalsh(cov).min() > 0
    lw = covariance(scen, "ledoit_wolf")
    assert lw.loc[CASH].abs().sum() == 0 and lw[CASH].abs().sum() == 0


@pytest.mark.parametrize("key", OPTIMISERS)
def test_solution_respects_constraints(inputs, key):
    mu, scen = inputs
    sol = MODELS[key].solve(scen, mu, {**BASE, "cvar_limit": 0.015}, all_cash(mu))
    w = sol.weights
    assert abs(w.sum() - 1) < 1e-6
    assert (w.drop(CASH) <= 0.10 + 1e-6).all()
    held = w.drop(CASH)[w.drop(CASH) > 0]
    assert (held >= 0.02 - 1e-6).all() and len(held) <= 15
    assert w["PM"] == 0
    assert w[["XOM", "CVX", "SLB", "COP"]].sum() <= 0.05 + 1e-6
    if key == "cvar":
        assert sol.cvar <= 0.015 + 1e-6
    else:
        assert sol.risk <= cvar_to_vol(0.015) + 1e-6


@pytest.mark.parametrize("key", OPTIMISERS)
def test_tighter_limit_means_less_risk_and_return(inputs, key):
    mu, scen = inputs
    tight = MODELS[key].solve(scen, mu, {**BASE, "cvar_limit": 0.010}, all_cash(mu))
    loose = MODELS[key].solve(scen, mu, {**BASE, "cvar_limit": 0.020}, all_cash(mu))
    assert tight.risk <= loose.risk + 1e-6
    assert tight.exp_return <= loose.exp_return + 1e-9


def test_equal_weight_ignores_everything_but_exclusions(inputs):
    mu, scen = inputs
    sol = MODELS["equal"].solve(scen, mu, {**BASE, "cvar_limit": 0.001}, all_cash(mu))
    held = sol.weights.drop(CASH)
    assert sol.weights[CASH] == 0 and sol.weights["PM"] == 0
    assert held[held > 0].nunique() == 1 and len(held[held > 0]) == 52
    assert sol.turnover == pytest.approx(2.0)


def test_robust_is_more_cautious_than_markowitz(inputs):
    mu, scen = inputs
    p = {**BASE, "cvar_limit": 0.015}
    mk = MODELS["markowitz_lw"].solve(scen, mu, p, all_cash(mu))
    rb = MODELS["robust"].solve(scen, mu, p, all_cash(mu))
    assert rb.exp_return <= mk.exp_return + 1e-9
