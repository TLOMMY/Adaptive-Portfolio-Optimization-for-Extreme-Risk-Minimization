"""Run every profile x model and write the JSON the site consumes.

Outputs (site/static/data/):
  index.json             profiles, models, and one summary row per run (the site's
                         table of contents; also says which model the story uses)
  universe.json          asset names, sectors, benchmark, date range
  prices.json            daily closes normalised to 1.0 at the journey start (for
                         stock charts and the user's own buy-and-hold picks)
  archive.json           what an investor could see on 31 Dec 2015: 2015 and
                         2013-2015 returns and drawdowns per asset and sector,
                         monthly sparklines, the T-bill rate.  Data strictly < 2016.
  runs/<profile>__<model>.json
                         value series, weekly weights, solve log, trades, metrics

Run everything:   python -m portfolio.export
One profile:      python -m portfolio.export --profile sprinter
One model:        python -m portfolio.export --model equal
Serial (debug):   python -m portfolio.export --jobs 1
"""

from __future__ import annotations

import argparse
import json
import time
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

from .backtest import BacktestResult, run_backtest
from .data import load_dataset
from .models import MODELS, STORY_MODEL, model_meta
from .profiles import PROFILES, Profile
from .universe import ASSETS, BENCHMARK, CASH, NAME, SECTOR, TICKERS

OUT = Path(__file__).resolve().parents[2] / "site" / "static" / "data"
START, END = "2016-01-04", "2025-12-31"
ARCHIVE_END = "2015-12-31"
SUMMARY_KEYS = ("cagr", "volatility", "sharpe", "sortino", "max_drawdown", "cvar_95_daily", "end_value")


def _r(x: float, nd: int = 4) -> float:
    return float(round(x, nd))


def _round_dict(d: dict, nd: int = 6) -> dict:
    return {k: (_r(v, nd) if isinstance(v, float) else v) for k, v in d.items()}


def profile_meta(p: Profile) -> dict:
    return {
        "key": p.key, "name": p.name, "tagline": p.tagline,
        "archetype": p.archetype, "personality": p.personality, "risk_tolerance": p.risk_tolerance,
        "horizon_years": p.horizon_years, "cvar_start": p.cvar_start, "cvar_end": p.cvar_end,
        "max_holdings": p.max_holdings, "w_max": p.w_max, "cash_min": p.cash_min,
        "sector_cap": p.sector_cap, "exclude": list(p.exclude),
    }


def run_file(profile: str, model: str) -> str:
    return f"runs/{profile}__{model}.json"


def result_json(res: BacktestResult) -> dict:
    dates = [d.strftime("%Y-%m-%d") for d in res.value.index]
    weekly = res.weights.resample("W-FRI").last().dropna(how="all")
    held = [a for a in ASSETS if (res.weights[a] > 0).any()]
    return {
        "profile": profile_meta(res.profile),
        "model": model_meta(res.model),
        "dates": dates,
        "value": [_r(v, 2) for v in res.value],
        "benchmark": [_r(v, 2) for v in res.benchmark],
        "weights": {
            "dates": [d.strftime("%Y-%m-%d") for d in weekly.index],
            "assets": held,
            "rows": [[_r(x) for x in row] for row in weekly[held].to_numpy()],
        },
        "solves": [
            {k: (v.strftime("%Y-%m-%d") if k == "date" else _r(v, 6) if isinstance(v, float) else v)
             for k, v in row.items()}
            for row in res.solves.to_dict("records")
        ],
        "trades": [
            {"date": r["date"].strftime("%Y-%m-%d"), "asset": r["asset"], "from": _r(r["from"]), "to": _r(r["to"])}
            for r in res.trades.to_dict("records")
        ],
        "metrics": _round_dict(res.metrics),
        "benchmark_metrics": _round_dict(res.benchmark_metrics),
    }


def summary_row(res: BacktestResult) -> dict:
    m, b = res.metrics, res.benchmark_metrics
    return {
        "profile": res.profile.key, "model": res.model.key, "file": run_file(res.profile.key, res.model.key),
        "solves": len(res.solves), "total_cost": _r(float(res.solves.cost.sum()), 2),
        "avg_cvar_limit": _r(float(res.solves.cvar_limit.mean()), 6),
        "metrics": {k: _r(m[k], 6) for k in SUMMARY_KEYS},
        "benchmark_metrics": {k: _r(b[k], 6) for k in SUMMARY_KEYS},
    }


# --- static tables --------------------------------------------------------------

def export_static(data: dict[str, pd.DataFrame]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "universe.json").write_text(json.dumps({
        "assets": [{"ticker": a, "name": NAME[a], "sector": SECTOR[a],
                    "kind": "cash" if a == CASH else "etf" if SECTOR[a] in ("Bonds", "Gold") else "stock"}
                   for a in ASSETS],
        "benchmark": BENCHMARK, "start": START, "end": END,
    }, indent=1))
    p = data["prices"].loc[START:END, TICKERS + [BENCHMARK, CASH]]
    norm = p / p.iloc[0]
    (OUT / "prices.json").write_text(json.dumps({
        "dates": [d.strftime("%Y-%m-%d") for d in norm.index],
        "assets": list(norm.columns),
        "rows": [[_r(x) for x in row] for row in norm.to_numpy()],
    }))


def export_archive(data: dict[str, pd.DataFrame]) -> None:
    """Everything here uses prices dated on or before ARCHIVE_END, nothing later."""
    prices = data["prices"].loc[:ARCHIVE_END]
    cols = TICKERS + [BENCHMARK, CASH]

    def window(first: str) -> pd.DataFrame:
        return prices.loc[first:ARCHIVE_END, cols]

    def stats(px: pd.DataFrame) -> pd.DataFrame:
        base = prices.loc[: px.index[0] - pd.Timedelta(days=1), cols].iloc[-1]   # close before the window
        ret = px.iloc[-1] / base - 1
        dd = (px / px.cummax() - 1).min()
        return pd.DataFrame({"return": ret, "max_drawdown": dd})

    y2015, y3 = stats(window("2015-01-01")), stats(window("2013-01-01"))
    monthly = window("2013-01-01").resample("ME").last()
    spark = monthly / monthly.iloc[0]

    assets = {}
    for a in cols:
        assets[a] = {
            "return_2015": _r(y2015.loc[a, "return"]), "drawdown_2015": _r(y2015.loc[a, "max_drawdown"]),
            "return_3y": _r(y3.loc[a, "return"]), "drawdown_3y": _r(y3.loc[a, "max_drawdown"]),
            "spark": [_r(x, 3) for x in spark[a]],
        }
    sectors = {}
    for sec in sorted({SECTOR[t] for t in TICKERS}):
        members = [t for t in TICKERS if SECTOR[t] == sec]
        ew = window("2015-01-01")[members].pipe(lambda px: (px / px.iloc[0]).mean(axis=1))
        sectors[sec] = {
            "tickers": members,
            "return_2015": _r(float(y2015.loc[members, "return"].mean())),
            "worst_2015": {"ticker": y2015.loc[members, "return"].idxmin(), "return": _r(y2015.loc[members, "return"].min())},
            "best_2015": {"ticker": y2015.loc[members, "return"].idxmax(), "return": _r(y2015.loc[members, "return"].max())},
            "drawdown_2015": _r(float((ew / ew.cummax() - 1).min())),
            "return_3y": _r(float(y3.loc[members, "return"].mean())),
        }
    tbill = data["rf"]["rf"].loc[:ARCHIVE_END].iloc[-1]
    (OUT / "archive.json").write_text(json.dumps({
        "as_of": ARCHIVE_END,
        "spark_dates": [d.strftime("%Y-%m") for d in spark.index],
        "tbill_rate_annual": _r(float((1 + tbill) ** 252 - 1)),
        "assets": assets, "sectors": sectors,
    }, indent=1))


# --- the grid --------------------------------------------------------------------

def _run_one(job: tuple[str, str]) -> tuple[str, str, dict, dict, float]:
    profile, model = job
    t0 = time.time()
    data = load_dataset()
    res = run_backtest(PROFILES[profile], data, model=model, start=START, end=END)
    return profile, model, result_json(res), summary_row(res), time.time() - t0


def main(profiles: list[str] | None = None, models: list[str] | None = None, jobs: int = 4) -> None:
    data = load_dataset()
    export_static(data)
    export_archive(data)
    (OUT / "runs").mkdir(exist_ok=True)

    ipath = OUT / "index.json"
    existing = {(r["profile"], r["model"]): r for r in json.loads(ipath.read_text())["runs"]} if ipath.exists() else {}
    todo = [(p, m) for p in (profiles or PROFILES) for m in (models or MODELS)]
    print(f"{len(todo)} backtests, {jobs} at a time")

    results = Pool(jobs).imap_unordered(_run_one, todo) if jobs > 1 else map(_run_one, todo)
    for profile, model, payload, row, dt in results:
        (OUT / run_file(profile, model)).write_text(json.dumps(payload))
        existing[(profile, model)] = row
        m, b = row["metrics"], row["benchmark_metrics"]
        print(f"{profile:10s} {model:13s} {dt:4.0f}s solves={row['solves']:3d} CAGR {m['cagr']:6.1%} "
              f"sharpe {m['sharpe']:4.2f} maxDD {m['max_drawdown']:6.1%} cvar {m['cvar_95_daily']:5.2%} "
              f"| SPY CAGR {b['cagr']:5.1%}", flush=True)

    runs = [existing[(p, m)] for p in PROFILES for m in MODELS if (p, m) in existing]
    ipath.write_text(json.dumps({
        "start": START, "end": END, "benchmark": BENCHMARK, "story_model": STORY_MODEL,
        "profiles": [profile_meta(p) for p in PROFILES.values()],
        "models": [model_meta(m) for m in MODELS.values()],
        "runs": runs,
    }, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append", help="profile key (repeatable); default all")
    ap.add_argument("--model", action="append", help="model key (repeatable); default all")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    main(a.profile, a.model, a.jobs)
