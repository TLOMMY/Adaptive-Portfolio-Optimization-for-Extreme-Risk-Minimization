# Adaptive Investor-Specific Portfolio Optimization

An operations-research project that turns investor preferences into a
constraint-aware portfolio and evaluates the result through a historical
walk-forward backtest. The project combines portfolio optimization, risk
measurement, and a deterministic interactive presentation.

<p align="center">
  <img src="docs/assets/system-architecture.png" width="100%" alt="End-to-end system architecture">
</p>

## Project Overview

The central research question is:

> How should a portfolio change when an investor's risk tolerance, time
> horizon, liquidity needs, and investment restrictions change?

The investor is represented by a profile rather than a single risk score. A
profile controls a daily tail-loss limit, maximum position size, minimum cash,
sector caps, exclusions, maximum holdings, and the horizon-dependent tightening
of risk limits. The same historical market data is then passed through several
optimization models so that the trade-offs are comparable.

This repository contains two deliberately separated layers:

- **Research layer (`implementation/`)**: Bowen's reusable Python backtester,
  CVXPY model adapters, profile constraints, and tests.
- **Presentation layer (`src/portfolio/`, `model/`, `site/`)**: Yesh's frozen
  AMPL/Svelte pipeline and the static JSON used by the final Netlify demo.

The presentation layer is the source of truth for the published figures. The
research adapters are included to make the methodology inspectable and
reproducible; they do not overwrite the website's precomputed results.

## Final Demo and Poster

- Live demo: [adaptive-portfolio-optimization.netlify.app](https://adaptive-portfolio-optimization.netlify.app/)
- Poster: [SharePoint link](https://ncku365-my.sharepoint.com/:p:/g/personal/m16137010_ncku_edu_tw/IQAQXAs6NEEJQI9FSPpfYWA3AXic066vsgwCOuby8XqODZ8?e=jG5WaV)

The frozen website contains 54 assets (51 stocks, AGG, GLD, and CASH), SPY as
the comparison benchmark, six investor profiles, five model views, and 30
profile-model runs covering `2016-01-04` through `2025-12-31`.

## End-to-End Pipeline

<p align="center">
  <img src="docs/assets/walk-forward-pipeline.png" width="100%" alt="Walk-forward portfolio pipeline">
</p>

The six stages correspond to the workflow presented in the poster:

1. **Estimate** - load adjusted-close prices and compute aligned daily simple
   returns.
2. **Parameterize** - map the selected investor profile to model parameters;
   the CVaR limit glides as the remaining horizon changes.
3. **Solve** - optimize portfolio weights with the selected risk model under
   long-only, concentration, cash, sector, exclusion, and turnover rules.
4. **Hold** - apply the next trading day's returns, track drift, and charge
   proportional transaction costs.
5. **Re-solve** - trigger a new optimization at the calendar limit, after
   sufficient allocation drift, or during a volatility regime change.
6. **Measure** - report CAGR, volatility, Sharpe, Sortino, maximum drawdown,
   daily CVaR, end value, turnover, and benchmark comparisons.

The look-ahead rule is explicit: at date `t`, the optimizer sees observations
strictly before `t`; newly solved weights start earning returns on `t + 1`.

## Models

The frozen presentation displays five model views:

| Model | Risk interpretation | Implementation location |
| --- | --- | --- |
| CVaR limit | Controls the average loss in the worst 5% of historical days | `model/cvar.mod`, `src/portfolio/models/cvar.py` |
| Markowitz | Trades expected return against portfolio variance | `model/markowitz.mod`, `src/portfolio/models/markowitz.py` |
| Markowitz + Ledoit-Wolf | Uses a shrunk covariance estimate to reduce estimation noise | `src/portfolio/models/markowitz.py` |
| Robust mean-variance | Protects against uncertainty in estimated returns | `model/robust.mod`, `src/portfolio/models/robust.py` |
| Equal weight (1/N) | Transparent no-estimate baseline | `src/portfolio/models/equal.py` |

The research directory also contains independent CVXPY adapters in
`implementation/models/`. In particular, `implementation/models/robust_mvo.py`
is a research comparison model and is not substituted for Yesh's AMPL Robust
model in the website.

## Data and Experimental Design

The final presentation pipeline uses a frozen processed dataset:

- **Investable universe**: 51 stocks plus AGG, GLD, and synthetic CASH.
- **Benchmark**: SPY, held separately for comparison.
- **History shown**: 2016-01-04 to 2025-12-31.
- **Estimation window**: 756 prior trading days (approximately three years).
- **Rebalancing**: quarterly maximum interval, with drift and volatility
  triggers plus a ten-day cooldown.
- **Returns**: adjusted-close daily simple returns, annualized with 252 trading
  periods.
- **Outputs**: portfolio value, benchmark value, weekly weights, solve logs,
  trades, and summary metrics.

`src/portfolio/data.py` documents the upstream data process: market history is
cached under `data/raw/` (ignored), cleaned tables are written to
`data/processed/`, and the website exporter writes JSON under
`site/static/data/`. The committed site data is intentionally static so the
demo can be replayed without a network connection or an optimization solver.

## Repository Structure

```text
Adaptive-Portfolio-Optimization/
|-- data/
|   `-- processed/             Frozen parquet inputs and tuning artifacts
|-- docs/
|   |-- assets/                README architecture and pipeline figures
|   |-- final_architecture.md  Research/presentation boundary
|   |-- research_backend.md    Bowen implementation guide
|   |-- presentation_guide.md  Five-person presentation order
|   `-- reproducibility.md     Verification commands
|-- implementation/            Independent Python research and validation
|   |-- portfolio_backtest.py  Walk-forward windows and metrics
|   |-- data_pipeline.py       Cached price/return preparation
|   |-- models/                 MVO, CVaR, Robust MVO adapters and registry
|   `-- investor_model_inputs/ Profile schema, examples, and tests
|-- model/                      Frozen AMPL model definitions
|-- src/portfolio/              Frozen production data/export pipeline
|   |-- data.py                 Market-data loading and cleaning
|   |-- profiles.py             Six investor archetypes and constraints
|   |-- backtest.py             Triggered re-solving and transaction costs
|   |-- models/                 Five displayed model implementations
|   `-- export.py                Writes the site's static JSON contract
|-- site/                       Frozen Svelte presentation and Strategy Lab
|   `-- static/data/             6 profiles x 5 models = 30 runs
|-- tests/                      Tests for the production portfolio pipeline
`-- pyproject.toml              Python package and AMPL dependencies
```

## Quick Start

### Run the research checks

Python 3.11+ is required. Install the research dependencies, then run:

```powershell
python -m pip install -r implementation/requirements.txt
python -m unittest discover -s implementation -p "test_*.py"
```

The tests verify train/test separation, no-look-ahead behavior, finite
out-of-sample metrics, normalized weights, profile constraints, and model
registry behavior.

### Check and build the website

Node.js is required for the Svelte site:

```powershell
cd site
npm ci
npm run check
npm run build
```

The build reads committed files in `site/static/data/`; it does not fetch live
prices or call the research backend.

## Presentation Story

The recommended order follows the poster and the live demo:

1. **Research question - Mana**: why investor profiles create an OR decision
   problem.
2. **Models - Kenta**: one equation and intuition for each risk definition.
3. **Methodology/backtest - Bowen**: the six-stage pipeline, asset-universe
   definition, lookback, quarterly rebalance, and no leakage.
4. **Results - Raymond**: Growth versus Balanced trade-offs in return, risk,
   drawdown, and turnover; avoid naming a universal winner.
5. **Live demo - Yeshwanth**: choose a profile and period, run the time
   machine, and open Strategy Diagnostics.

Close with:

> The preferred portfolio depends on the investor's objective and constraints,
> not just on which model has the highest return.

## Limitations

This is an educational research prototype, not investment advice. Historical
backtests do not guarantee future performance. The universe is subject to
survivorship and selection bias, and results depend on the chosen dates,
solver settings, transaction-cost assumptions, and profile constraints. The
poster draft may describe a 2016-2024 narration while the frozen website data
ends in 2025; presenters should state the exact period shown in each figure.

## Contributors

Mana (research question), Kenta (model framing), Bowen (methodology and
research implementation), Raymond (results), Jia Qi (model research), and
Yeshwanth (presentation website and live demo).
