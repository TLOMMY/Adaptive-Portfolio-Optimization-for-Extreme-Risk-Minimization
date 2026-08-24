# What Still Needs to Be Added

## Required next decisions

- Yeshwanth: finalize train/test window and rebalance convention.
- Kenta and Jia: provide a small profile configuration table, not a long list of factors.
- Mana: choose the extension model and define its mathematical inputs.
- Team: freeze the asset universe and data source before running comparisons.

## Recommended sequence

1. Run equal weight through the framework.
2. Add constrained MVO as the common model baseline.
3. Add CVaR as the extension if its loss scenarios and alpha are explicit.
4. Add multiple evaluation periods using the same `BacktestWindow` interface.
5. Add turnover and transaction costs only after the first clean comparison.

## Current blocker

The code is ready for a real optimizer, but it cannot produce a meaningful model comparison until the team freezes the asset universe and time-window conventions.
