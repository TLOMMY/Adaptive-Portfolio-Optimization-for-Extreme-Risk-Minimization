# Adaptive Portfolio Optimization

An operations-research project on investor-specific portfolio selection. The
project asks a practical question: how should an allocation change when an
investor's risk tolerance, time horizon, liquidity needs, and constraints
change?

## Final Demo

Open the deployed presentation site: [adaptive-portfolio-optimization.netlify.app](https://adaptive-portfolio-optimization.netlify.app/)

The poster is available on [SharePoint](https://ncku365-my.sharepoint.com/:p:/g/personal/m16137010_ncku_edu_tw/IQAQXAs6NEEJQI9FSPpfYWA3AXic066vsgwCOuby8XqODZ8?e=jG5WaV).

The website is frozen for the final presentation. It contains six investor
profiles, five model views, and 30 precomputed runs over the date range
2016-01-04 to 2025-12-31. The website data and model configuration are the
presentation source of truth and should not be silently replaced by the
research adapters in this repository.

## Presentation Story

1. **Research question - Mana**: investor-specific portfolio selection as an
   operations-research decision problem.
2. **Models - Kenta**: Markowitz mean-variance, CVaR, robust mean-variance,
   plus the website's Ledoit-Wolf and equal-weight comparators.
3. **Methodology and backtest - Bowen**: ten ETFs, a three-year lookback,
   quarterly rebalancing, walk-forward evaluation, and no-look-ahead bias.
4. **Results and interpretation - Raymond**: compare growth and balanced
   profiles across return, risk, drawdown, and turnover; do not claim a
   universal winner.
5. **Live demo and takeaways - Yeshwanth**: select a profile and period,
   run the time machine, and inspect Strategy Diagnostics.

## Repository Map

```text
implementation/       Bowen's research/backtesting adapters and tests
src/portfolio/        Yesh's frozen data/export pipeline
model/                Yesh's frozen AMPL model definitions
data/processed/       Yesh's frozen processed inputs and tuning artifacts
site/                 Yesh's frozen Svelte presentation and static JSON
docs/                 Final architecture, research, presentation, and replay notes
tests/                Yesh pipeline tests
```

`implementation/` is an independent research section. It demonstrates input
validation, train/test separation, model adapters, profile constraints, and
reproducible checks. It is not an HTTP backend for the deployed site: the final
site remains static-data driven so the presentation is deterministic.

## Reproduce the Research Checks

Use the bundled Python environment or any Python 3.11+ environment with the
packages in `implementation/requirements.txt`:

```powershell
python -m unittest discover -s implementation -p "test_*.py"
```

The checks cover window separation, finite out-of-sample metrics, weight
normalisation, profile constraints, and model-registry behaviour.

## Scope and Limitations

This is an educational research prototype, not investment advice. Historical
backtests do not guarantee future performance. Results depend on the selected
ETF universe, dates, return convention, solver settings, transaction-cost
assumptions, and investor constraints. The poster may use a shortened
2016-2024 narration, while the frozen website data ends in 2025; presenters
should state the exact period shown in each figure.

## Contributors

Mana (research question), Kenta (model framing), Bowen (methodology and
research implementation), Raymond (results), and Yeshwanth (presentation
website and live demo).
