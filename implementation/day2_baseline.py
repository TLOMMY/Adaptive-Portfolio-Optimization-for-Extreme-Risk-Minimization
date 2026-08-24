"""Run the Day 2 equal-weight baseline over explicit market periods."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

from data_pipeline import build_market_period_windows, load_adjusted_close_csv, prepare_returns
from portfolio_backtest import equal_weight_model, run_backtest


def run_equal_weight_baseline(
    prices: pd.DataFrame,
    periods: Sequence[tuple[str, str, str]],
    *,
    train_years: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run equal weight on each market period and return standard outputs."""

    returns = prepare_returns(prices)
    windows = build_market_period_windows(returns, periods, train_years=train_years)
    return run_backtest(
        returns,
        windows,
        equal_weight_model,
        model_name="equal_weight",
        profile_name="not_applicable",
    )


def run_equal_weight_csv(
    input_csv: str | Path,
    output_dir: str | Path,
    periods: Sequence[tuple[str, str, str]],
    *,
    train_years: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load cached prices, run the baseline, and save both output tables."""

    prices = load_adjusted_close_csv(input_csv)
    metrics, weights = run_equal_weight_baseline(
        prices, periods, train_years=train_years
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(output / "equal_weight_metrics.csv", index=False)
    weights.to_csv(output / "equal_weight_weights.csv", index=False)
    return metrics, weights
