"""Run a local synthetic benchmark for the final integration contract."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from models import fit_cvar, fit_mvo
from portfolio_backtest import BacktestWindow, compute_returns, equal_weight_model, run_backtest


def build_synthetic_prices() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2013-01-01", "2025-12-31", freq="B")
    n_assets = 9
    market = rng.normal(0.00025, 0.008, len(dates))
    noise = rng.normal(0.0, 0.006, size=(len(dates), n_assets))
    returns = market[:, None] * 0.35 + noise
    returns[:, 5:] += rng.normal(0.00008, 0.004, size=(len(dates), 4))
    return pd.DataFrame(100.0 * np.exp(np.cumsum(returns, axis=0)), index=dates, columns=[f"ETF{i}" for i in range(n_assets)])


def main() -> None:
    prices = build_synthetic_prices()
    returns = compute_returns(prices)
    windows = [
        BacktestWindow("2018", "2015-01-01", "2018-01-01", "2018-01-01", "2018-12-31"),
        BacktestWindow("2020", "2017-01-01", "2020-01-01", "2020-01-01", "2020-12-31"),
        BacktestWindow("2022", "2019-01-01", "2022-01-01", "2022-01-01", "2022-12-31"),
    ]
    profiles = {
        "Growth": {"risk_aversion": 5.0, "confidence_level": 0.95, "max_weight": 0.35, "iterations": 500},
        "Retirement": {"risk_aversion": 10.0, "confidence_level": 0.99, "max_weight": 0.30, "iterations": 500},
    }
    for profile, config in profiles.items():
        for name, model in [("equal_weight", equal_weight_model), ("mvo", fit_mvo), ("cvar", fit_cvar)]:
            metrics, weights = run_backtest(
                returns, windows, model, model_name=name, profile_name=profile,
                profile_config=config,
            )
            print(f"{profile:10} {name:12} windows={len(metrics)} weights={len(weights)}")
            print(metrics[["evaluation_period", "cumulative_return", "annualized_volatility", "maximum_drawdown", "cvar"]].to_string(index=False))


if __name__ == "__main__":
    main()
