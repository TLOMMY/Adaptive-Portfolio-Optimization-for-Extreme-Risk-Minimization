# Review Findings

## Findings

- No critical correctness findings in the Day 1 scope.
- The framework intentionally does not model transaction costs, turnover constraints, sector limits, or quarterly rebalancing yet; these require the convention sheet from Yeshwanth.
- A future rolling backtest should create explicit windows and continue to preserve the same train/test separation.

## Follow-up

Add the selected optimizer only after its input/output contract is agreed. Do not silently change annualization, asset universe, or window definitions between models.
