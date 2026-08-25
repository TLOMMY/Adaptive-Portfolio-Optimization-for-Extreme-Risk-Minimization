# Day 1 Cycle Report

## Completed

- discovery and scope boundary;
- model-independent backtest API;
- equal-weight baseline;
- out-of-sample metrics;
- unit tests and handoff messages.
- cached CSV loader and optional Yahoo Finance adapter;
- multiple market-period window builder;
- Day 2 equal-weight baseline runner.

## Deferred

- MVO/CVaR/Robust MVO implementation;
- investor-factor parameter selection;
- transaction costs and turnover;
- Streamlit interface;
- multi-period result aggregation.

## Next cycle

Integrate Yeshwanth's convention sheet and Mana's selected optimizer adapter, then run a first unseen-period comparison against equal weight.

## Integration update

- Refactored Mana's MVO and CVaR concepts into common model adapters.
- Added Kenta profile-export adaptation.
- Passed the synthetic multi-period benchmark and nine unit tests.
- Proceed to real-data final integration; target-return and turnover are now
  enforced by the CVXPY adapters, while cardinality remains in Yesh's MILP.
