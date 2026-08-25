"""Hyperparameter tuning on the pre-journey period (April 2011 - December 2015).

Everything here is chosen WITHOUT looking at 2016-2025.  The grid is small and
the selection rule is deliberately simple:
  keep configurations whose realised daily CVaR stayed within ~10% of the
  profile's average limit (the risk promise was kept), then take the highest
  Sharpe ratio; ties go to the configuration that traded least.
"""

from __future__ import annotations

import itertools
import json
import sys
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

from .backtest import run_backtest
from .data import load_dataset
from .profiles import PROFILES

TUNE_START, TUNE_END = "2011-04-01", "2015-12-31"
OUT = Path(__file__).resolve().parents[2] / "data" / "processed" / "tuning.json"

GRID = {
    "lookback_days": [504, 756],
    "shrink": [0.5, 0.75, 1.0],
    "drift_trigger": [0.10, 0.20],
    "vol_trigger": [1.5, 2.0, 99.0],       # 99 = volatility trigger effectively off
}


def _run(args):
    key, cfg = args
    data = load_dataset()
    prof = replace(PROFILES[key], **cfg)
    res = run_backtest(prof, data, TUNE_START, TUNE_END)
    m = res.metrics
    avg_limit = float(res.solves.cvar_limit.mean())
    return {
        "profile": key, **cfg, "solves": len(res.solves),
        "cagr": m["cagr"], "sharpe": m["sharpe"], "max_drawdown": m["max_drawdown"],
        "cvar": m["cvar_95_daily"], "avg_limit": avg_limit, "cvar_ratio": m["cvar_95_daily"] / avg_limit,
        "turnover": float(res.solves.turnover.sum()),
    }


def main(keys: list[str]) -> None:
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    jobs = [(k, c) for k in keys for c in combos]
    print(f"{len(jobs)} backtests on {TUNE_START}..{TUNE_END}")
    with Pool(4) as pool:
        rows = pool.map(_run, jobs)
    df = pd.DataFrame(rows)
    OUT.write_text(json.dumps(rows, indent=1))
    for k in keys:
        d = df[df.profile == k]
        ok = d[d.cvar_ratio <= 1.10]
        best = (ok if len(ok) else d).sort_values(["sharpe", "turnover"], ascending=[False, True]).iloc[0]
        print(f"\n== {k}: {len(ok)}/{len(d)} configs kept the risk promise; best:")
        print(best.to_string())
    print("\nmarginal means of Sharpe by setting:")
    for g in GRID:
        print(" ", g, df.groupby(g).sharpe.mean().round(3).to_dict())


if __name__ == "__main__":
    main(sys.argv[1:] or ["builder", "preserver"])
