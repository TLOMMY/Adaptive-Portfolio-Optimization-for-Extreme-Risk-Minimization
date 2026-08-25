# Review Findings

## Findings

- No critical correctness findings in the Day 1 scope.
- The framework intentionally does not model transaction costs, turnover constraints, sector limits, or quarterly rebalancing yet; these require the convention sheet from Yeshwanth.
- A future rolling backtest should create explicit windows and continue to preserve the same train/test separation.

## Follow-up

Add the selected optimizer only after its input/output contract is agreed. Do not silently change annualization, asset universe, or window definitions between models.

## Integration benchmark review

- MVO and CVaR adapters run through the shared backtester and produce valid long-only weights.
- Synthetic results are an engineering check only.
- `target_annual_return` and `max_turnover` are now enforced by the CVXPY
  adapters. Infeasible configurations raise explicitly. Cardinality and
  minimum-position constraints remain in Yesh's AMPL/HiGHS MILP.
