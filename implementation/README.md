# Portfolio Backtest Handoff

This is Bowen's Day 1 implementation slice. It is deliberately model-independent so Mana can plug in MVO, CVaR, or Robust MVO without changing the evaluation logic.

Day 2 adds `data_pipeline.py` and `day2_baseline.py`: cached adjusted-close CSV input, optional Yahoo Finance downloading, multiple market-period windows, and a runnable equal-weight baseline.

The integration adapters in `models/` use CVXPY with CLARABEL/HiGHS and accept
the same profile configuration shape. They enforce continuous portfolio
constraints and raise an explicit error for infeasible profiles.

## Input contract

Use a `pandas.DataFrame` with:

- a unique, sorted `DatetimeIndex`;
- one column per asset ticker;
- adjusted-close prices before `compute_returns`, or aligned simple returns for `run_backtest`;
- no zero, negative, infinite, or duplicate values.

The recommended future price schema is:

```text
date, ticker, adjusted_close
```

The wide DataFrame passed to this module has dates as its index and tickers as columns.

## Example

```python
from portfolio_backtest import (
    BacktestWindow,
    compute_returns,
    equal_weight_model,
    run_backtest,
)

prices = ...  # adjusted-close DataFrame
returns = compute_returns(prices)
window = BacktestWindow(
    "period_1",
    "2016-01-01",
    "2018-01-01",  # exclusive training end
    "2018-01-01",
    "2018-12-31",
)
metrics, weights = run_backtest(
    returns,
    [window],
    equal_weight_model,
    model_name="equal_weight",
    profile_name="balanced",
)
```

## Model handoff

Mana's adapter should have this signature:

```python
def fit_model(train_returns, profile_config):
    # estimate parameters and solve using train_returns only
    return weights  # Series, mapping, or array with one value per asset
```

The backtester normalizes and validates the weights, then evaluates them on the later test period. It never passes test returns to `fit_model`.

## Current convention

- long-only weights;
- weights sum to one;
- 252 trading periods per year;
- simple returns;
- no transaction costs yet;
- explicit windows so different market periods can be added later.

Yeshwanth owns the final web/export conventions; Bowen owns the executable
framework, adapters, and tests. The exact static JSON contract is documented
in `yesh_backend_contract.md`.

## Day 2 baseline

```python
from day2_baseline import run_equal_weight_baseline

metrics, weights = run_equal_weight_baseline(
    prices,
    [
        ("period_1", "2018-01-01", "2018-12-31"),
        ("period_2", "2020-01-01", "2020-12-31"),
    ],
    train_years=3,
)
```

The periods are explicit and can later be replaced by the team's agreed evaluation periods without changing the backtest engine.
