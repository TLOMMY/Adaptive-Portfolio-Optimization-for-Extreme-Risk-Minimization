# Investor Category to Portfolio Model Input Conversion

This module converts three-level investor priority scores into input dictionaries for Markowitz mean-variance, CVaR, and robust minimum-variance portfolio models. The parameter values are transparent demonstration scenarios, not estimates derived from investor data.

## Run the module

Python 3.9 or newer is required. No external packages are needed.

```bash
cd "/Users/uedakenta/Documents/Codex/2026-08-24/referenced-chatgpt-conversation-this-is-an/outputs/investor_model_inputs"
python3 investor_inputs.py --output-dir examples
python3 -m unittest -v
```

## Input schema

Each investor category has three integer scores:

- `return_requirement`: required return priority
- `risk_protection`: downside and uncertainty protection priority
- `liquidity_turnover`: liquidity and turnover-control priority

The scale is `1=Low`, `2=Medium`, and `3=High`.

| Category | Return | Risk protection | Liquidity / turnover |
|---|---:|---:|---:|
| Growth | 3 | 2 | 1 |
| Balanced | 2 | 2 | 2 |
| Retirement | 1 | 3 | 3 |
| Extreme Low Risk | 1 | 3 | 2 |

## Normalized preference weights

Each weight equals its score divided by the sum of all three scores. For example, Growth is `(3, 2, 1) / 6 = (0.50, 0.333333, 0.166667)`. These weights are for explanation and comparison; they are not inserted directly as optimization coefficients.

## Scenario mappings

All mappings are defined in `SCENARIO_MAPPINGS` so they can be reviewed and changed easily.

| Input score | Low (1) | Medium (2) | High (3) |
|---|---:|---:|---:|
| Return requirement to `target_annual_return` | 4% | 8% | 12% |
| Risk protection to Markowitz `risk_aversion` | 1 | 5 | 10 |
| Risk protection to CVaR `confidence_level` | 90% | 95% | 99% |
| Risk protection to robust `covariance_uncertainty_radius` | 0.05 | 0.10 | 0.20 |
| Turnover control to `max_turnover` | 1.00 | 0.50 | 0.20 |

`max_turnover` is defined as `sum(abs(new_weight - current_weight))`. A smaller value imposes a tighter limit on changes from the current portfolio.

## Model-specific dictionaries

- `markowitz_mean_variance`: maximizes mean-variance utility and receives `risk_aversion`, `target_annual_return`, and `max_turnover`.
- `cvar_optimization`: minimizes CVaR and receives `confidence_level`, `target_annual_return`, and `max_turnover`.
- `robust_minimum_variance`: minimizes worst-case variance and receives `covariance_uncertainty_radius`, `target_annual_return`, and `max_turnover`.

All models use `long_only=true` and `fully_invested=true`. Each dictionary lists the additional market data needed under `required_market_inputs`.

## Outputs

- `examples/model_inputs.json`: structured input for Python or another application
- `examples/model_inputs.csv`: flat table with one row per investor category and model

## Important assumptions

1. The scores are ordinal, but normalization treats them as equally spaced for demonstration purposes.
2. The 4%, 8%, and 12% target returns are scenario assumptions. Production values should be calibrated using capital-market expectations, investment horizon, inflation, and suitability rules.
3. The scale of `covariance_uncertainty_radius` depends on the robust model's uncertainty-set definition. The model developer must use the same definition or recalibrate these values.
4. A high target return combined with strict risk or turnover limits may be infeasible. Run a feasibility check before optimization.
