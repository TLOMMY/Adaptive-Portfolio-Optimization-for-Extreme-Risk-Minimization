# Yesh Frontend Integration Contract

## Decision

The Svelte page is currently static-data driven. The final backend should
export the JSON files below rather than introduce a separate HTTP API. This
keeps the existing page unchanged and allows the optimizer implementation to
be swapped behind the exporter.

## Required files

| File | Required top-level fields |
|---|---|
| `site/static/data/universe.json` | `assets`, `benchmark`, `start`, `end` |
| `site/static/data/prices.json` | `dates`, `assets`, `rows` |
| `site/static/data/events.json` | array of `{date,title,blurb,side,kind,image?,credit?}` |
| `site/static/data/profiles/index.json` | array of profile metadata |
| `site/static/data/profiles/{key}.json` | one `ProfileResult` per profile |
| `site/static/data/summary.json` | headline metric rows |

## Profile result contract

Each profile result must contain:

```json
{
  "profile": {"key":"builder","name":"Builder","horizon_years":10,
    "cvar_start":0.02,"cvar_end":0.01,"max_holdings":12,
    "w_max":0.12,"cash_min":0.02,"sector_cap":{},"exclude":[]},
  "dates": ["YYYY-MM-DD"],
  "value": [100000.0],
  "benchmark": [100000.0],
  "weights": {"dates": [], "assets": [], "rows": []},
  "solves": [{"date":"YYYY-MM-DD","reason":"calendar",
    "years_left":9.0,"cvar_limit":0.02,"exp_return_ann":0.08,
    "cvar":0.01,"turnover":0.2,"cost":20.0,
    "n_holdings":8,"solve_time":0.2}],
  "trades": [{"date":"YYYY-MM-DD","asset":"AAA",
    "from":0.1,"to":0.12}],
  "metrics": {},
  "benchmark_metrics": {}
}
```

The TypeScript definitions in `site/src/lib/data.ts` are authoritative for
the complete `Metrics` and metadata fields. Dates are ISO strings, weights and
returns are decimal fractions, and `value`/`benchmark` are portfolio values.

## Model-to-export mapping

The local MVO/CVaR adapters return a labelled weight vector. The exporter must
convert it to the `weights.rows` matrix and use the same vector to populate
`solves`, `trades`, and the daily portfolio value series. The optimizer must
receive only observations strictly before each rebalance date. The current
Yesh backtester already enforces this rule and applies new weights from the
following day.

Supported by the local CVXPY adapters:

- fully invested, long-only weights;
- per-asset `max_weight`;
- minimum annual target return;
- maximum L1 turnover from `current_weights`;
- excluded assets, cash minimum, and sector caps.

`max_holdings` and minimum positive position size are cardinality/disjunctive
constraints. They require the mixed-integer AMPL/HiGHS model already present
in Yesh's branch; they should not be approximated in the local continuous
MVO/CVaR comparison.

## Conventions

- Use adjusted close prices and daily **simple returns** (`P_t/P_{t-1}-1`).
- Annualized mean and covariance use 252 trading periods.
- CVaR confidence is the non-tail probability (0.95 means the worst 5% of
  daily losses are averaged).
- `max_turnover` is `sum(abs(new_weight-current_weight))`.
- An infeasible profile is an explicit failed solve, not a silently relaxed
  target. The final report should show the profile and solver status.

## Final integration sequence

1. Agree on one asset universe, date range, and return convention.
2. Run MVO, CVaR, and Yesh's constrained optimizer on the same walk-forward
   windows.
3. Export every profile through this schema.
4. Load the generated JSON in the Svelte page and check charts, units, and
   disclaimers before presenting results.
