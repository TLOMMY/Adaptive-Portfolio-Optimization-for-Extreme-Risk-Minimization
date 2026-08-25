# Final Presentation Integration Plan

## Objective

Connect Kenta's investor profiles, Mana's MVO/CVaR models, Bowen's
out-of-sample backtester, and Yeshwanth's interactive presentation around one
stable contract.

## Stable contract

```python
weights = fit_model(train_returns, profile_config)
```

The model sees training returns only. The backtester evaluates the returned
weights on later returns. Profile parameters are configuration, not hard-coded
inside a model.

## Work sequence

1. Keep Kenta's profile conversion as the source of profile parameters.
2. Refactor Mana's MVO and CVaR prototypes into importable model adapters.
3. Run a local synthetic-data benchmark to validate all interfaces before using
   network data.
4. Freeze the final asset universe, dates, and return convention.
5. Run the same models and profiles over the same historical periods.
6. Export weights, portfolio curves, and metrics for Yeshwanth's presentation.
7. Connect the final outputs to the web demo. The demo should label model-based
   results separately from user-entered portfolios.

## Scope decision

The benchmark is only an engineering gate. The final presentation is the
deliverable. Do not build a separate benchmark product or optimize for a
single historical period.

## Jia Qi selective integration

Jia Qi's repository has no common Git ancestor with this branch and uses a
different Streamlit application. We therefore ported the mathematical Robust
MVO contribution into `models/robust_mvo.py` and registered it alongside the
existing MVO/CVaR adapters. The full Streamlit application and its 10-ETF
snapshot remain outside this branch. This keeps both final options open:
benchmark all three research models, or use Yesh's AMPL CVaR model as the main
web presentation strategy.

## Ownership

- Kenta/Jia: investor-profile definitions and rationale.
- Mana: optimization objective and model math; review the adapters.
- Bowen: integration, data boundary, backtest, metrics, and reproducibility.
- Yeshwanth: visual demo and final model-convention sign-off.

## Acceptance criteria before final demo

- MVO and CVaR both accept the same `fit_model` interface.
- All profiles produce valid long-only weights summing to one.
- No test-period rows reach model fitting.
- The same asset universe and evaluation periods are used for all strategies.
- The demo reports assumptions and does not present historical results as advice.

## Current configuration gap

Kenta's export currently contains risk, return, confidence, and turnover
parameters, but not a maximum asset weight. The adapter therefore requires the
final experiment to provide `max_weight` explicitly rather than silently
assuming a concentration limit.
