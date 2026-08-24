"""Static explanatory content for the demo.

Kept out of app.py so the UI layer stays layout-only and the wording can be
reviewed as prose.
"""

from __future__ import annotations

WALKTHROUGH = """\
### What am I looking at?

A **time machine for investment decisions**.

Instead of asking "what should I buy today?", this app rewinds to a date in the
past — say January 2016 — hands a computer program *only* the market data that
existed on that day, and asks it to build a portfolio. Then it plays history
forward and shows what actually happened to that portfolio.

Then it does it again three months later. And again. For up to nine years.

The point isn't to find a money-printing strategy. It's to show that **different
investors, given the exact same data, should rationally build different
portfolios** — and to make that difference visible.

---

### The vocabulary, in one line each

| Term | What it means |
|---|---|
| **Portfolio** | How you split your money across investments |
| **Weights** | The split itself — "35% in SPY" is a weight of 0.35 |
| **Rebalancing** | Periodically adjusting back to your target split. Here: every 3 months |
| **Volatility** | How much the value bounces around, up *or* down |
| **Drawdown** | How far you fell from your highest point. The number that hurts |
| **CVaR** | Your average loss on the worst 5% of days. "When it's bad, how bad?" |
| **Turnover** | How much you traded. Trading costs money and triggers taxes |
| **Lookback** | How much history the program studies before deciding. Here: 3 years |

---

### The four strategies, without the maths

All four get **identical data at the same moment**. They disagree because they
are optimizing for different things.

**Equal Weight** — splits money evenly across all 10 assets. No forecasting, no
cleverness. It's here because it's genuinely hard to beat: it can't be wrong
about a prediction it never made.

**Markowitz** — the classic. Wants high returns and dislikes bouncing around.
Treats its estimate of "how risky is this?" as if it were a known fact.

**CVaR** — only cares about the bad days. Asks "of the worst 5% of days in
history, how painful were they on average?" and minimises that. Completely
indifferent to how wildly things go *up*.

**Robust Min-Variance** — the pessimist. Says "my risk estimate might be wrong,"
computes six different risk estimates from different stretches of history, and
builds the portfolio that holds up under the **worst** of them.

---

### Why "no look-ahead" is the whole ballgame

It's trivially easy to build a backtest that looks amazing and is worthless. You
just let the program peek at what happened next — usually by accident.

This app makes that structurally impossible. At each decision date the optimizer
is handed a sealed data window that physically does not contain later prices.
It's not "we promised not to look" — the future data isn't in the box.

That's why, standing in December 2019, the app will not tell you COVID is
coming. Neither does it tell the optimizer.

---

### How to drive it — five steps

1. **Pick an investor profile** (left sidebar). Each represents a different kind
   of person with different priorities.
2. **Pick a historical period.** Start with the full 2016–2024 run.
3. **Look at the decision date** — the big month/year. That's "today" for the
   optimizer.
4. **Press `Advance quarter`** and watch the portfolio change as the optimizer
   re-decides with three more months of history. Or press `Run full period` to
   jump to the end.
5. **Read the comparison table.** Ask: *did this profile's strategy do what the
   investor actually asked for?*

---

### What to look for (the interesting bits)

- Switch between **Growth** and **Extreme Low Risk**. The portfolios look
  completely different — same data, different objective.
- Watch the **max drawdown** column. The conservative strategies usually fall
  much less in bad periods, and earn less the rest of the time. That trade is
  the entire subject.
- Run the **2019–2021** period and watch what happens in early 2020.
- If a red **return-target** banner appears, that's the optimizer reporting it
  *cannot* reach the investor's goal with the assets available. It says how far
  short it is rather than quietly giving up.

---

### The trap to avoid

**The strategy with the biggest number at the end is not automatically the
winner.** A retiree who wanted to avoid catastrophic losses, and did, got what
they asked for — even if a riskier strategy made more money over this particular
decade. Judge each one against *its own investor's stated objective*.

And remember: this is **one** run of history. It happened once. It is not a
prediction, and nine years is not a large sample.
"""

ASSET_INTRO = """\
**Yes — these are real, and so are the prices.**

All ten are actual exchange-traded funds (ETFs) you can buy today, and the app
uses their genuine historical daily closing prices, adjusted for dividends and
stock splits. Nothing here is synthetic or made up.

What *is* simulated is the trading: no real money was invested, and the
portfolios below never existed. The simulation just reacts to prices that
genuinely happened.

**What's an ETF?** A single fund that holds hundreds or thousands of underlying
investments. Buying one share of SPY gives you a slice of all 500 companies in
the S&P 500. Using ETFs instead of individual stocks keeps the demo about
*portfolio construction* rather than stock picking.

**How these ten were chosen** — and this matters for honesty: they were picked
for **variety** (stocks, bonds, gold, property, from several regions) and for
having price history going back before 2013, which the 3-year lookback needs.
They were emphatically **not** picked for performing well over 2016–2024. Doing
that would be cheating — choosing winners you already know won, then acting
impressed when they win.
"""

ASSET_DESCRIPTIONS = {
    "SPY": "The 500 largest US companies — Apple, Microsoft, Exxon and so on.",
    "IJR": "600 small US companies. Riskier and more volatile than the giants.",
    "EFA": "Large companies in developed markets outside the US — Europe, Japan, Australia.",
    "EEM": "Companies in emerging economies — China, India, Brazil, Taiwan. Highest risk here.",
    "AGG": "A broad basket of US bonds: government, corporate, mortgage. The classic ballast.",
    "TLT": "US government bonds repaid in 20+ years. Very safe from default, very sensitive to interest rates.",
    "SHY": "US government bonds repaid in 1-3 years. The closest thing here to cash.",
    "LQD": "Bonds issued by financially solid companies. More yield than government debt, more risk.",
    "GLD": "Physical gold. Often moves independently of stocks, which is the point of holding it.",
    "VNQ": "US commercial property — offices, malls, warehouses — via real-estate trusts.",
}

METHODOLOGY_FLOW = """\
```
        Investor Profile
                │
                ▼
   Risk Objective + Return Requirement + Liquidity Preference
                │
                ▼
        Optimization Formulation
                │
                ▼
          Portfolio Weights  x*_t
                │
                ▼
      Actual Historical Returns  (t → t+1)
                │
                ▼
       Rebalance / Re-optimize  ──┐
                │                 │
                └─────────────────┘
```
"""

MODEL_FORMULATIONS = {
    "Markowitz": {
        "objective": "maximise   μᵀx − λ·xᵀΣx",
        "reads_as": (
            "Earn as much expected return as possible, penalised by how much the "
            "portfolio's value is expected to swing. λ sets how hard that penalty bites."
        ),
        "variables": "x — the fraction of capital in each asset",
        "notes": (
            "Treats the estimated covariance Σ as if it were known exactly. "
            "Penalises upside and downside swings equally."
        ),
    },
    "CVaR 95%": {
        "objective": "minimise   z + (1/((1−α)N))·Σₛ uₛ,   uₛ ≥ −rₛᵀx − z,  uₛ ≥ 0",
        "reads_as": (
            "Make the average of the worst 5% of days as mild as possible. "
            "z settles at the loss threshold (VaR); uₛ measures how far each bad "
            "day overshoots it."
        ),
        "variables": "x — weights;  z — the loss threshold;  uₛ — excess loss in scenario s",
        "notes": (
            "Indifferent to upside swings — it only looks at the loss tail. "
            "Uses every daily return in the lookback as one equally likely scenario."
        ),
    },
    "Robust Min-Variance": {
        "objective": "minimise   z    subject to   xᵀQₛx ≤ z  for every scenario s",
        "reads_as": (
            "Assume the covariance estimate might be wrong. Pick the portfolio "
            "whose variance is lowest under the least favourable of several "
            "covariance estimates taken from different stretches of the lookback."
        ),
        "variables": "x — weights;  z — the worst-case variance being minimised",
        "notes": (
            "Protects against uncertainty in the covariance estimate — not against "
            "market regimes absent from the lookback entirely."
        ),
    },
    "Equal Weight": {
        "objective": "xᵢ = 1/N",
        "reads_as": "Split the money evenly. No estimation, no optimization.",
        "variables": "none",
        "notes": (
            "Uses no estimated parameters, so it cannot be wrong about any of them. "
            "A genuinely hard benchmark, included for that reason. It ignores the "
            "return target and turnover limit by construction."
        ),
    },
}

SHARED_CONSTRAINTS = """\
- Weights sum to 1 (fully invested)
- No short selling (x ≥ 0)
- No single asset above 35%
- Minimum expected return ≥ the profile's target
- One-way turnover per rebalance ≤ the profile's limit
"""

ASSUMPTIONS = """\
**This is an educational Operations Research demonstration, not investment advice.**

- The four investor profiles are **illustrative academic presets**. Their parameter
  values — return targets, risk-aversion levels, turnover limits — are prototype
  assumptions chosen to make the comparison legible, not calibrated to any real
  investor or recommended to anyone.
- **No look-ahead bias.** At each decision date the optimizer receives a data
  window truncated at that date and holds no reference to anything after it. This
  is enforced structurally, not by convention, and verified by tests that corrupt
  all post-decision data and assert the decisions come out bit-identical.
- **Real historical market data**: adjusted closing prices, dividends reinvested,
  splits applied. Taxes are not modelled. Transaction costs are zero in this
  baseline.
- **Expected returns and covariances are estimates**, not known quantities. They
  are computed from a 3-year trailing window by sample mean and Ledoit–Wolf
  shrinkage, using one fixed method throughout.
- **Historical outcomes do not guarantee future outcomes.**
- **One historical path does not prove generalisability.** Every result here is a
  single realised trajectory. Differences between strategies over one decade are
  not statistically significant on their own, and no significance testing is
  performed.
- **Subperiod analysis tests robustness across different historical periods** — it
  is not evidence of future performance. The three subperiods are overlapping
  views of the same decade.
- **Fixed methodology.** The asset universe, 3-year lookback, quarterly rebalancing
  and estimator choices were fixed before any results were evaluated, and are not
  retuned per profile or per period.
- The asset universe was selected for asset-class breadth and for having price
  history predating the experiment, **not** for its performance over the
  evaluation window.
"""

TIME_MACHINE_NOTE = (
    "Portfolio decisions use only information available through this date. "
    "What happens next has not been revealed to the optimizer."
)
