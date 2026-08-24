#Adaptive Portfolio Optimization for Extreme Risk Minimization

Implementation work for Team KYMBJ's Track 2 Operations Research project.

This repository currently contains Bowen Liu's model-independent backtesting
and Day 2 equal-weight baseline. The code is intentionally separated from the
optimizer so that MVO, CVaR, or Robust MVO can be plugged in later without
changing the evaluation layer.

## Contents

- `implementation/portfolio_backtest.py`: train/test-safe backtesting engine and metrics.
- `implementation/data_pipeline.py`: adjusted-close CSV validation, caching, optional Yahoo Finance loading, and multi-period windows.
- `implementation/day2_baseline.py`: equal-weight baseline runner.
- `implementation/test_portfolio_backtest.py`: unit and leakage checks.
- `implementation/README.md`: input/output contract and model handoff instructions.

## Current contract

Each optimizer receives training returns only and returns one weight per asset:

```python
weights = model.fit(train_returns, profile_config)
```

The returned weights are evaluated on a later, unseen test period. This keeps
the comparison out-of-sample and avoids look-ahead bias.

## Local verification

```powershell
python -m unittest discover -s implementation -p "test_*.py"
```

The current test suite covers data round-tripping, multiple evaluation periods,
weight validation, standard metrics, and train/test leakage prevention.

## Collaboration boundary

- Bowen owns the executable backtesting and data pipeline.
- Yeshwanth owns shared model conventions and testing assumptions.
- Mana owns the optimizer adapter and selected model extension.
- Kenta and Jia own investor-profile factor definitions and rationale.

The repository is for educational research and is not investment advice.
