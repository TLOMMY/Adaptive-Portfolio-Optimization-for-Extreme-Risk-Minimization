import pandas as pd

from portfolio.data import load_dataset
from portfolio.universe import ASSETS, BENCHMARK, CASH


def test_dataset_shape_and_coverage():
    d = load_dataset()
    p = d["prices"]
    assert set(ASSETS + [BENCHMARK]) == set(p.columns)
    assert p.index.min() <= pd.Timestamp("2008-04-02")
    assert p.index.max() >= pd.Timestamp("2026-01-01")
    assert p.isna().sum().sum() == 0
    assert d["returns"].index.equals(p.index)


def test_cash_is_smooth_and_positive():
    r = load_dataset()["returns"][CASH]
    assert r.min() > -1e-5  # T-bills went slightly negative in March 2020
    assert r.max() < 0.001  # never more than 0.1% per day
