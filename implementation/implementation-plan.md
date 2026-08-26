# Weekend Day 1 Implementation Plan

## Goal

Create a small, reproducible evaluation layer that accepts any portfolio model and produces comparable out-of-sample metrics.

## Approach

1. Accept a DataFrame of adjusted-close prices indexed by date and with one column per asset.
2. Convert prices to aligned simple daily returns.
3. Define explicit, non-overlapping train/test windows.
4. Fit a model using the training returns only.
5. Evaluate fixed weights on the test returns.
6. Return a long-form metrics table and a long-form weights table.

## Files

- `portfolio_backtest.py`: implementation and public API.
- `test_portfolio_backtest.py`: unit tests for data validation, leakage prevention, weights, and metrics.
- `README.md`: usage contract and handoff notes.
- `team_messages.md`: copy-ready messages for Yeshwanth and Mana.

## Acceptance criteria

- Training and testing date ranges cannot overlap.
- Model fitting receives training rows only.
- Weights are finite, non-negative, and sum to one.
- Metrics are calculated from test returns only.
- Equal-weight baseline runs without a model-specific dependency.
- A simple test suite passes.

## Risks

- Missing or misaligned prices can create accidental look-ahead or inconsistent assets.
- A later optimizer may return a NumPy array rather than a labelled Series.
- Annualized metrics depend on the agreed periods-per-year convention.

## Next handoff

Yeshwanth should confirm the window, rebalance, transaction-cost, and metric conventions. Mana should implement a model adapter that returns a labelled weight vector accepted by `run_backtest`.
