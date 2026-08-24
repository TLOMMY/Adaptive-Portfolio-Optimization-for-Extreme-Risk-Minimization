# Adaptive Investor-Specific Portfolio Optimization

An interactive historical portfolio **time machine** demonstrating how different
investor objectives lead to different portfolio optimization decisions.

This is an **Operations Research** project. It does not forecast prices. It stands
at a past date, optimizes a portfolio using only information available then,
observes what actually happened next, and repeats.

> Educational research demo. Not investment advice.

---

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 0 | Environment, repo skeleton, data snapshot | **Complete** |
| 1 | Data pipeline, backtest engine, no-look-ahead proofs | **Complete** |
| 2 | Estimation layer, equal-weight + Markowitz, metrics | **Complete** |
| 3 | Scenario-based CVaR optimizer | Not started |
| 4 | Robust minimum-variance optimizer | Not started |
| 5 | Investor profile system | Not started |
| 6 | Streamlit interface | Not started |
| 7 | Polish, documentation, validation | Not started |

The replay machinery and its no-look-ahead guarantees were built and validated
before any optimizer existed, so that a failure in a model could never be
confused with a failure in the experiment harness. Every optimizer added since
is re-checked against the same invariance proofs.

---

## Quick start

```bash
conda activate amazon_or          # Python 3.12
pip install -e ".[dev]"

python scripts/fetch_data.py      # refresh the price snapshot (optional)
pytest -q                         # run the full suite
```

The application reads the **committed CSV snapshot** at
`data/snapshots/prices_diversified_etf_10.csv` by default, so it runs with no
network access. `scripts/fetch_data.py` regenerates that snapshot.

---

## The look-ahead firewall

Look-ahead bias is the central methodological risk in a historical replay study,
so it is prevented **structurally**, not merely tested for.

`MarketDataView` is constructed for one decision date, slices the price panel to
that date, and **retains only the slice**. It holds no reference to the full
panel. Estimators and optimizers receive a view and never a price panel, so data
after the decision date is not forbidden to them — it is not present in the object
graph they can reach.

```
                    ┌─────────────────────────────┐
                    │   full price panel          │  ← engine only
                    └──────────────┬──────────────┘
                                   │  slice at t, copy
                                   ▼
        ┌────────────────────────────────────────────┐
        │  MarketDataView(as_of = t)                 │  ← everything else
        │  holds ONLY observations ≤ t               │
        └──────────────┬─────────────────────────────┘
                       │
                       ▼
              strategy.allocate()  →  weights x*_t   [LOCKED]
                       │
                       ▼
   engine reads realised returns over (t, t_next]  ← only after locking
```

The engine is the only object holding both. All strategies in a run share the
**same view instance** at each decision date, which is what makes cross-strategy
comparison a controlled experiment.

### How the guarantee is verified

The flagship test replaces all history after a decision date with fabricated
values and asserts the decisions taken at or before that date come out
**bit-identical**. If anything reached past the boundary, the corrupted values
would propagate and the comparison would fail.

The test strategy is deliberately *data-dependent* (its weights are a function of
the estimation window's contents) — a strategy that ignored its inputs would pass
such a test vacuously. The check runs on synthetic fixtures and again on real
market data across the 2020 crash.

---

## Conventions

Every convention that could be defined more than one way is defined once, in
`src/config/settings.py`.

| Item | Convention |
|---|---|
| Returns | Simple: `r_t = P_t / P_{t-1} − 1`, from adjusted close |
| Why not log returns | A portfolio's log return is not the weighted sum of asset log returns |
| Dividends / splits | Reinvested and adjusted; **taxes not modelled** |
| Annualisation | `mean × 252`, `var × 252`, `vol × √252` |
| Estimation cutoff | `date ≤ t` (inclusive). Configurable to strict `< t` |
| Holding period | Weights set at `t` earn returns over `(t, t_next]` — never the formation day |
| Drift | Positions drift with the market between rebalances; the next rebalance trades away from **drifted** weights |
| One-way turnover | `0.5 · Σ|w_after − w_before|` — the reported metric |
| Cost base | `Σ|w_after − w_before|` — a sale and the purchase it funds are two chargeable trades |
| Transaction costs | **0 bps** in the validated baseline; mechanism present and configurable |
| Risk horizon | Daily. Reported CVaR will be a **daily** figure and labelled as such (Phase 3) |
| Cumulative return | `V_T / V_0 − 1`, from the value path |
| Annualised return | Geometric: `(V_T/V_0)^(252/n) − 1`, *n* = return count |
| Annualised volatility | Sample stdev (`ddof=1`) of daily returns `× √252` |
| Maximum drawdown | `min_t (V_t / peak_t − 1)`, stored **negative** |
| Return target / shortfall | Annualised decimal, both in the same units |
| Missing quotes | Forward-filled *within* the view → zero return, never an artificial jump |

**Turnover at the first rebalance.** Establishing the position from cash trades
100% of notional, so `traded_fraction = 1.0` and one-way turnover is `0.5`. That
first trade is not a rebalance in the usual sense, so
`BacktestResult.average_turnover()` excludes it by default.

---

## Models

### Estimation layer

One estimator pair is used for the whole main experiment, so every model is fed
identically constructed inputs and no result depends on an estimator choice made
mid-experiment. Alternatives (EWMA, James–Stein) are a sensitivity-analysis
extension and are deliberately absent.

| Parameter | Estimator | Annualisation |
|---|---|---|
| Expected returns `mu` | Sample mean of daily simple returns | `x 252` (arithmetic) |
| Covariance `Sigma` | Ledoit–Wolf shrinkage toward a scaled identity | `x 252` |

Ledoit–Wolf is chosen for conditioning, not fit: its shrinkage intensity is
derived analytically from the data rather than tuned, so nothing about it is
fitted to the evaluation period. The realised intensity is recorded per decision
date. A PSD repair step guards the covariance and logs loudly if it ever fires.

### Markowitz mean-variance

$$\max_x \; \mu^\top x - \lambda\, x^\top \Sigma x$$

subject to $\mathbf{1}^\top x = 1$, $0 \le x_i \le w_{\max}$, asset-class caps
$\sum_{i \in c} x_i \le L_c$, and an optional return target
$\mu^\top x \ge R_{\min}$. Convex QP, solved with **CLARABEL**.

### Equal weight

$x_i = 1/N$. Uses no estimated parameters, so it is immune to estimation error —
a genuinely hard benchmark, not a straw man. It runs through the same interface
and receives the same `MarketDataView` as every optimizer.

### Unattainable return targets

A return target may exceed what any feasible portfolio can deliver. **The
constraint is never dropped.** A nonnegative shortfall variable measures how far
the target is from attainable:

$$\min_{x,s} \; s \quad \text{s.t.} \quad \mu^\top x + s \ge R_{\min}, \; s \ge 0, \; \text{(structural constraints)}$$

The optimal $s^\star$ is the **minimum unavoidable shortfall** — zero when the
target is attainable, otherwise exactly the gap to the best achievable expected
return. The mean-variance problem is then solved with the closest attainable
target $R_{\min} - s^\star$, and $s^\star$ is reported as `return_shortfall` in
annualised decimal units, alongside `max_attainable_return` and
`effective_return_target`.

Preferred to a big-M penalty: no penalty weight to tune, and $s^\star$ is exact
rather than an artefact of penalty scaling. Structural infeasibility — a feasible
region that is empty regardless of objective, such as a weight cap too low to
fill the budget — is a different thing and is raised as an error.

---

## Default experiment

* **Universe** — 10 ETFs spanning equity, fixed income, commodities, real assets
  (`SPY IJR EFA EEM AGG TLT SHY LQD GLD VNQ`). Selected for asset-class breadth
  and pre-2013 inception, **not** for realised performance over the evaluation
  window. Concentration constraints apply at asset-class granularity.
* **Window** — **frozen**: 2016-01-01 → 2025-12-31, first decision **2016-01-04**
* **Lookback** — 3 years of daily data, **required in full** at every decision date
* **Rebalancing** — quarterly (40 decision dates)
* **Snapshot** — 5,695 sessions, 2004-01-02 → 2026-08-21, no interior gaps

### Research mode vs. demo mode

The formal experiment uses a **frozen** window (`RESEARCH_START` / `RESEARCH_END`)
so that refreshing the snapshot cannot alter published results — a test asserts
that appending future data changes nothing. `BacktestSettings.for_demo(latest)`
extends the window to the most recent data for a live presentation; those results
are **not reproducible** and every result carries `mode` and `reproducible` flags
so the two can never be confused.

### Lookback enforcement

A decision made from a shorter-than-configured window is not the experiment that
was configured, so it never happens silently. `LookbackPolicy.REQUIRE` (default)
aborts and names the offending dates; `LookbackPolicy.EXCLUDE` drops them before
the experiment starts and records which were dropped.

All four are configurable; the application works with another universe by
changing configuration alone.

---

## Architecture

```
src/
  config/      assets.py        universe + asset-class metadata
               settings.py      every numerical convention, defined once
  data/        provider.py      MarketDataProvider ABC + panel contract
               yahoo_provider.py  yfinance, falling back to direct HTTP
               csv_provider.py  committed snapshot — the reproducible default
               cache.py         parquet cache
               window.py        MarketDataView — the look-ahead firewall
  estimation/  (Phase 2) ex-ANTE parameters — consume a MarketDataView
  portfolio/   (Phase 2-4) optimizers behind one interface
  backtest/    strategy.py      the contract the engine requires
               rebalance.py     trading-calendar-aware decision dates
               engine.py        the time machine
               results.py       realised series + audit trail
  risk/        (Phase 2) ex-POST metrics — consume realised returns
  profiles/    (Phase 5) investor configuration
  visualization/, ui/  (Phase 6)
```

`estimation/` and `risk/` are separate packages on purpose. Covariance estimation
is an ex-ante optimizer input and must respect the cutoff; performance metrics are
ex-post and legitimately look at realised returns. Keeping them apart makes the
boundary visible in code review: **anything in `estimation/` takes a
`MarketDataView`; anything in `risk/` takes a realised return series.**

The engine defines the strategy contract rather than importing one from the
optimization package, so the dependency points the right way — optimizers conform
to what the backtest needs, and the backtest knows nothing about how any
particular portfolio is computed.

---

## Data sources

`yfinance` is the primary path. A direct call to Yahoo's chart endpoint with an
explicit browser `User-Agent` is the fallback — Yahoo returns HTTP 429 to default
programmatic user agents from some networks. Neither is a dependency of the demo
itself: the application reads the committed snapshot, and network access is only
needed to *regenerate* it.

The snapshot excludes the session in progress, so an incomplete intraday bar
never enters a reproducibility artefact.

---

## Testing

```bash
pytest -q                                  # full suite
pytest tests/test_no_lookahead.py -v       # the methodological proofs
pytest --cov=src --cov-report=term-missing
```

| Suite | Covers |
|---|---|
| `test_no_lookahead.py` | Poisoned-future invariance, truncation invariance, boundary invariants, shared information set |
| `test_data_window.py` | View slicing, cutoff conventions, gap handling, guards |
| `test_backtest.py` | Value arithmetic vs. known answers, drift, turnover, costs, failure handling, dates |
| `test_rebalance.py` | Calendar snapping, frequencies, holding-period contiguity |
| `test_data_provider.py` | Panel contract, snapshot round-trip, cache |
| `test_config.py` | Settings validation, universe integrity |
| `test_estimation.py` | Sample mean, Ledoit–Wolf, PSD repair, boundary invariance |
| `test_constraints.py` | Declaration validity, structural feasibility, the region a solver sees |
| `test_equal_weight.py` | 1/N exactness, parameter independence, constraint conflicts |
| `test_markowitz.py` | Constraint satisfaction, the λ trade-off, the shortfall identity |
| `test_metrics.py` | Every metric against a hand-computed answer |
| `test_walkforward.py` | Optimizers inside the engine: invariance, constraints at every date, frozen window |
| `test_integration_snapshot.py` | The real frozen-window experiment end to end |

Correctness is checked against **analytically known answers** wherever possible —
a 100%-in-one-asset portfolio must reproduce that asset's price path exactly; an
equal-weight portfolio's first-day return must equal the cross-sectional mean —
rather than against previously recorded output.

---

## Methodological commitments

* No future information reaches any portfolio decision.
* Asset universe and model parameters are fixed before evaluation.
* Expected returns and covariances are **estimates**, not known quantities.
* Historical replay is **one realized market path**, not a distribution over
  possible futures; differences between strategies over a single decade are not
  statistically significant on their own.
* Transaction costs and taxes are excluded from the baseline.
* Historical performance does not guarantee future performance.
