# Review Findings

## Findings

- No critical correctness findings in the Day 1 scope.
- The research framework models transaction costs, turnover constraints, and
  explicit walk-forward windows. Cardinality and minimum-position constraints
  remain specific to the frozen AMPL presentation model.
- Future experiments should continue to preserve the same train/test
  separation and document any convention changes.

## Follow-up

Add the selected optimizer only after its input/output contract is agreed. Do not silently change annualization, asset universe, or window definitions between models.

## Integration benchmark review

- MVO, CVaR, and Robust MVO adapters run through the shared backtester and
  produce valid long-only weights.
- Synthetic results are an engineering check only.
- `target_annual_return` and `max_turnover` are now enforced by the CVXPY
  adapters. Infeasible configurations raise explicitly. Cardinality and
  minimum-position constraints remain in Yesh's AMPL/HiGHS MILP.
