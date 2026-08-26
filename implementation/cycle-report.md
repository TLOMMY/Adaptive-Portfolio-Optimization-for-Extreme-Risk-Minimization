# Final Integration Cycle Report

## Completed

- discovery and scope boundary;
- model-independent backtest API;
- equal-weight baseline;
- out-of-sample metrics;
- unit tests and handoff messages.
- cached CSV loader and optional Yahoo Finance adapter;
- multiple market-period window builder;
- Day 2 equal-weight baseline runner.

## Final boundary

- `implementation/` remains the research and validation layer.
- Yesh's `src/portfolio/`, `model/`, `site/`, and static JSON remain the frozen
  presentation layer.
- The research Robust MVO adapter is not substituted for Yesh's presentation
  Robust model.

## Integration update

- Refactored Mana's MVO and CVaR concepts into common model adapters.
- Added Kenta profile-export adaptation.
- Passed 15 research unit tests.
- Confirmed 6 profiles, 5 models, and 30 frozen website runs.
- Confirmed the Svelte type check and production build.
- Target-return and turnover are enforced by the CVXPY research adapters,
  while cardinality remains in Yesh's AMPL model.

## Remaining presentation check

The frozen website ends on 2025-12-31. If the final poster describes the
period as 2016-2024, the presenters should explain which exact period each
figure uses.
