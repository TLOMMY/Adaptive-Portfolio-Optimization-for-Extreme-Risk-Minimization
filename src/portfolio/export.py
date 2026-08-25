"""Run every profile and write the JSON the site consumes.

Outputs (site/static/data/):
  universe.json          asset names, sectors, benchmark
  prices.json            daily closes normalised to 1.0 at the journey start (for
                         stock charts and the user's own buy-and-hold picks)
  profiles/<key>.json    value series, weekly weights, solve log, trades, metrics
  summary.json           one row of headline metrics per profile
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

from .backtest import BacktestResult, run_backtest
from .data import load_dataset
from .profiles import PROFILES, Profile
from .universe import ASSETS, BENCHMARK, CASH, NAME, SECTOR, TICKERS

OUT = Path(__file__).resolve().parents[2] / "site" / "static" / "data"
START, END = "2016-01-04", "2025-12-31"


def _r(x: float, nd: int = 4) -> float:
    return float(round(x, nd))


def profile_meta(p: Profile) -> dict:
    return {
        "key": p.key, "name": p.name, "tagline": p.tagline,
        "horizon_years": p.horizon_years, "cvar_start": p.cvar_start, "cvar_end": p.cvar_end,
        "max_holdings": p.max_holdings, "w_max": p.w_max, "cash_min": p.cash_min,
        "sector_cap": p.sector_cap, "exclude": list(p.exclude),
    }


def result_json(res: BacktestResult) -> dict:
    dates = [d.strftime("%Y-%m-%d") for d in res.value.index]
    weekly = res.weights.resample("W-FRI").last().dropna(how="all")
    held = [a for a in ASSETS if (res.weights[a] > 0).any()]
    return {
        "profile": profile_meta(res.profile),
        "dates": dates,
        "value": [_r(v, 2) for v in res.value],
        "benchmark": [_r(v, 2) for v in res.benchmark],
        "weights": {
            "dates": [d.strftime("%Y-%m-%d") for d in weekly.index],
            "assets": held,
            "rows": [[_r(x) for x in row] for row in weekly[held].to_numpy()],
        },
        "solves": [
            {**{k: (v.strftime("%Y-%m-%d") if k == "date" else _r(v, 6) if isinstance(v, float) else v)
                for k, v in row.items()}}
            for row in res.solves.to_dict("records")
        ],
        "trades": [
            {"date": r["date"].strftime("%Y-%m-%d"), "asset": r["asset"], "from": _r(r["from"]), "to": _r(r["to"])}
            for r in res.trades.to_dict("records")
        ],
        "metrics": {k: (_r(v, 6) if isinstance(v, float) else v) for k, v in res.metrics.items()},
        "benchmark_metrics": {k: (_r(v, 6) if isinstance(v, float) else v) for k, v in res.benchmark_metrics.items()},
    }


def export_static(data: dict[str, pd.DataFrame]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "universe.json").write_text(json.dumps({
        "assets": [{"ticker": a, "name": NAME[a], "sector": SECTOR[a], "kind": "cash" if a == CASH else "etf" if a not in NAME or SECTOR[a] in ("Bonds", "Gold") else "stock"} for a in ASSETS],
        "benchmark": BENCHMARK, "start": START, "end": END,
    }, indent=1))
    p = data["prices"].loc[START:END, TICKERS + [BENCHMARK, CASH]]
    norm = p / p.iloc[0]
    (OUT / "prices.json").write_text(json.dumps({
        "dates": [d.strftime("%Y-%m-%d") for d in norm.index],
        "assets": list(norm.columns),
        "rows": [[_r(x) for x in row] for row in norm.to_numpy()],
    }))


def main(keys: list[str] | None = None) -> None:
    data = load_dataset()
    export_static(data)
    (OUT / "profiles").mkdir(exist_ok=True)
    (OUT / "profiles" / "index.json").write_text(json.dumps([profile_meta(p) for p in PROFILES.values()], indent=1))
    spath = OUT / "summary.json"
    summary = {r["key"]: r for r in json.loads(spath.read_text())} if spath.exists() else {}
    for key in keys or PROFILES:
        t0 = time.time()
        res = run_backtest(PROFILES[key], data, START, END)
        (OUT / "profiles" / f"{key}.json").write_text(json.dumps(result_json(res)))
        m, b = res.metrics, res.benchmark_metrics
        summary[key] = ({"key": key, "name": res.profile.name, "solves": len(res.solves),
                        **{k: _r(m[k], 6) for k in ("cagr", "volatility", "sharpe", "max_drawdown", "cvar_95_daily", "end_value")},
                        **{f"spy_{k}": _r(b[k], 6) for k in ("cagr", "volatility", "sharpe", "max_drawdown", "end_value")}})
        print(f"{res.profile.name:22s} {time.time()-t0:4.0f}s solves={len(res.solves):3d} "
              f"CAGR {m['cagr']:6.1%} vol {m['volatility']:5.1%} sharpe {m['sharpe']:4.2f} "
              f"maxDD {m['max_drawdown']:6.1%} cvar {m['cvar_95_daily']:5.2%} | SPY CAGR {b['cagr']:5.1%} maxDD {b['max_drawdown']:6.1%}")
    spath.write_text(json.dumps([summary[k] for k in PROFILES if k in summary], indent=1))


if __name__ == "__main__":
    main(sys.argv[1:] or None)
