"""Static explanatory content for the demo.

Kept out of app.py so the UI layer stays layout-only and the wording can be
reviewed as prose.
"""

from __future__ import annotations

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
