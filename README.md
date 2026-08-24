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
| 3 | Scenario-based CVaR optimizer | **Complete** |
| 4 | Robust minimum-variance optimizer | **Complete** |
| 5 | Investor profile system | **Complete** |
| 6 | Streamlit interface | **Complete (MVP)** |
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

streamlit run app.py              # <- launch the interactive demo
```

Other commands:

```bash
python scripts/fetch_data.py      # refresh the price snapshot (optional)
pytest -q                         # run the full suite
```

The application reads the **committed CSV snapshot** at
`data/snapshots/prices_diversified_etf_10.csv` by default, so it runs with no
network access. `scripts/fetch_data.py` regenerates that snapshot.

---

## Investor profiles

Four illustrative presets, differing in **exactly three decision factors** — risk
objective, return requirement, liquidity preference. Universe, weight caps
(35%), lookback, rebalance cadence and estimators are identical across all four,
so differences in outcome are attributable to those three factors and nothing
else.

| Profile | Risk objective | Model | Return target | Turnover limit |
|---|---|---|---|---|
| Growth | Favour return, accept volatility | Markowitz (λ=1.0) | 8% | 50% |
| Balanced | Balance return against volatility | Markowitz (λ=5.0) | 6% | 25% |
| Downside Protection / Retirement | Reduce severe downside losses | CVaR 95% | 4% | 15% |
| Extreme Low Risk | Minimise risk under covariance uncertainty | Robust Min-Variance | 2% | 15% |

**Illustrative academic presets, not investment advice.** The parameter values
are prototype assumptions chosen to make the comparison legible, not calibrated
to any real investor.

All four models run under the *selected profile's* constraints, so the
comparison asks "given this investor's requirements, which formulation best
satisfies their objective?" rather than comparing constraint sets. Equal Weight
is the exception by construction — it uses no estimated parameters and ignores
the return target and turnover limit.

### Turnover limit

`0.5 · Σ|xᵢ − wᵢ^pre| ≤ L`, measured against the **drifted** pre-rebalance
weights, and enforced in the return-shortfall stage too — the attainable-return
frontier is a property of the region the model actually solves over. Skipped at
inception, where the portfolio is established from cash. If drift pushes the
pre-rebalance point outside the box and the region becomes empty, the limit is
dropped and the relaxation is **recorded and displayed**, never silent.

### Evaluation periods

Full (2016–2024), and subperiods 2016–2018, 2019–2021, 2022–2024. The 3-year
estimation lookback extends before each period's start; nothing is retuned per
period. These are **historical subperiod robustness analyses**, not evidence of
future generalisability.

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
| VaR / CVaR | Positive **loss** magnitudes; exact empirical Rockafellar–Uryasev with fractional boundary weight; **never annualised** |
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

### CVaR (Expected Shortfall)

Rockafellar–Uryasev, with loss $L_s(x) = -r_s^\top x$, VaR threshold $z$ and
excess-loss variables $u_s$:

$$\min_{x,z,u} \; z + \frac{1}{(1-\alpha)N}\sum_{s=1}^{N} u_s
\quad \text{s.t.} \quad u_s \ge -r_s^\top x - z, \; u_s \ge 0$$

plus the same structural constraints and optional return target as Markowitz.
Every term is linear — this is an **LP**, solved with **HiGHS**. At the optimum
$z^\star$ is the VaR and the objective value is the CVaR.

The objective penalises only the magnitude of losses in the worst
$(1-\alpha)$ of scenarios and is indifferent to dispersion elsewhere, including
upside dispersion — the substantive difference from a variance objective.

**Scenarios**: each daily return in the lookback window is one equiprobable
scenario (~756 at the default lookback). No bootstrap, no synthetic data, no
distributional assumption. A `MIN_SCENARIOS = 100` guard refuses tail estimates
built from too few points.

**Units**: with `risk_horizon_days = 1` the optimized quantity is a **1-day
historical CVaR**. It is never annualised — tail measures do not obey a
square-root-of-time rule — and a 1-day CVaR does not describe long-horizon risk.
Multi-day horizons are implemented via non-overlapping compounded blocks, but a
3-year lookback only yields `756/h` scenarios, so a 21-day horizon (36 scenarios)
correctly trips the guard.

### Robust minimum variance

Minimise **worst-case** annualised variance over a finite covariance uncertainty
set $\{Q_s\}$, in epigraph form:

$$\min_{x,z} \; z \quad \text{s.t.} \quad x^\top Q_s x \le z \;\; \forall s$$

plus the same structural constraints and optional return target. Each $Q_s$ is
PSD, so every quadratic constraint is convex — a convex QCQP, solved as an SOCP
with **CLARABEL**. The binding epigraph constraint identifies the worst-case
scenario.

**Uncertainty set** (MVP, fixed — *not* a claim of optimality): five overlapping
252-observation subwindows at stride 126 (offsets 0, 126, 252, 378, 504 — the
last ending exactly at the decision date), plus the full 756-observation
estimate: **six** scenarios. Every one uses the same Ledoit–Wolf estimator and
annualisation as Phase 2, so scenarios differ only by data window. The
`CovarianceUncertaintySet` interface exists so box or ellipsoidal sets can
replace scenario enumeration without touching the optimizer.

**Units**: the objective is annualised **variance**. No square root is taken
inside the program; worst-case volatility is reported afterwards as $\sqrt{z}$.

**Validation** is separate from the CVaR `MIN_SCENARIOS` rule, which counts tail
points. Here each scenario is a whole covariance matrix, so each is checked for
consistent ticker order, finiteness, symmetry, PSD-ness, a window ending at or
before the decision date, and at least `MIN_OBSERVATIONS_PER_SCENARIO = 120`
underlying returns. Generating fewer scenarios than required is an error, never
a silent shrink of the uncertainty set.

This protects against *estimation* uncertainty in the covariance — that the
sample window understated co-movement — not against regimes absent from the
lookback entirely.

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
| `test_metrics.py` | Every metric against a hand-computed answer; CVaR vs. RU minimisation |
| `test_scenarios.py` | Scenario construction, non-overlapping blocks, MIN_SCENARIOS guard, boundary invariance |
| `test_cvar.py` | LP feasibility, CVaR vs. independent metric, α monotonicity, shortfall, boundary invariance |
| `test_covariance_scenarios.py` | Uncertainty-set construction, PSD/symmetry/finiteness validation, boundary invariance |
| `test_robust.py` | Worst-case objective identity, grid-search optimality, set monotonicity, singleton reduction |
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
