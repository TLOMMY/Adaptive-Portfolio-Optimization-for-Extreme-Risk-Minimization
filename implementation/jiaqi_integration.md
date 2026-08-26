# Jia Qi Model Integration Note

## What was integrated

Jia Qi's branch is a separate Streamlit application with a different Git
history, 10-ETF universe, four profiles, and its own backtest engine. It was
therefore not merged wholesale. The portable mathematical contribution was
adapted into the current `main` contract:

- `fit_robust_mvo(train_returns, profile_config)` implements worst-case
  annualised variance over rolling covariance scenarios;
- `models/registry.py` exposes MVO, CVaR, and Robust MVO through one registry;
- all models use the same continuous constraints and current-weight convention;
- the existing Bowen backtester remains responsible for train/test separation.

The existing local MVO and CVaR adapters were retained rather than duplicated:
they already use CVXPY, expose the same hard constraints, and have passing
tests. Jia Qi's Robust MVO is the genuinely new model in this integration.

## Robust MVO convention

The default adapter uses five rolling covariance windows plus the full training
window (six scenarios, matching Jia Qi's MVP). Each covariance is annualised and
repaired to positive semidefinite form before the convex epigraph problem is
solved. `scenario_count`,
`scenario_window`, `scenario_stride`, and `include_full_scenario` are explicit
configuration values so the experiment can freeze them.

This is a research comparison adapter. `max_holdings` and minimum positive
position size remain mixed-integer constraints and are still enforced only by
Yesh's AMPL/HiGHS presentation backend.

## Model-selection decision

| Model | Current integration source | Reason |
|---|---|---|
| MVO | Bowen adapter, aligned with Jia Qi's formulation | Avoid duplicate implementations; both are convex QPs |
| CVaR | Bowen adapter, aligned with Jia Qi's formulation | Same Rockafellar–Uryasev LP and shared constraints |
| Robust MVO | Jia Qi formulation adapted to Bowen interface | New model not previously available in Bowen's branch |

This leaves both Plan A and Plan B open: the three adapters can be benchmarked
together, while Yesh's CVaR MILP remains a separate final-presentation option.

## Known convention differences

- Jia Qi's full application measures one-way turnover as
  `0.5 * sum(abs(new - previous))`. The current Kenta export and Bowen
  backtester define `max_turnover` as the full L1 distance. Until the team
  freezes one convention, do not compare turnover numbers across the two apps.
- Jia Qi's full application computes an explicit minimum return shortfall and
  solves at the closest attainable target. The current lightweight adapters
  raise on an infeasible hard target. This is intentional for the integration
  gate, but the final experiment must choose one policy and report it clearly.
