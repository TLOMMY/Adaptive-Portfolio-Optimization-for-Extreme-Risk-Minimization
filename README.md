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
| 2 | Equal-weight + Markowitz optimizer, performance metrics | Not started |
| 3 | Scenario-based CVaR optimizer | Not started |
| 4 | Robust minimum-variance optimizer | Not started |
| 5 | Investor profile system | Not started |
| 6 | Streamlit interface | Not started |
| 7 | Polish, documentation, validation | Not started |

No optimization models exist yet, by design: the replay machinery and its
no-look-ahead guarantees were built and validated first, so that a later failure
in an optimizer cannot be confused with a failure in the experiment harness.

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
| Risk horizon | Daily. Reported CVaR is a **daily** figure and is labelled as such |
| Missing quotes | Forward-filled *within* the view → zero return, never an artificial jump |

**Turnover at the first rebalance.** Establishing the position from cash trades
100% of notional, so `traded_fraction = 1.0` and one-way turnover is `0.5`. That
first trade is not a rebalance in the usual sense, so
`BacktestResult.average_turnover()` excludes it by default.

---

## Default experiment

* **Universe** — 10 ETFs spanning equity, fixed income, commodities, real assets
  (`SPY IJR EFA EEM AGG TLT SHY LQD GLD VNQ`). Selected for asset-class breadth
  and pre-2013 inception, **not** for realised performance over the evaluation
  window. Concentration constraints apply at asset-class granularity.
* **Window** — first decision **2016-01-04**, through **2026-08-21**
* **Lookback** — 3 years of daily data before each decision date
* **Rebalancing** — quarterly (43 decision dates)
* **Snapshot** — 5,695 sessions, 2004-01-02 → 2026-08-21, no interior gaps

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
| `test_integration_snapshot.py` | The real 2016–2026 experiment end to end |

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
