"""Poster experiments on top of the exported backtest grid.

Reads  site/static/data/runs/<profile>__<model>.json (6 x 5 runs)
Writes poster/experiments/out/
    daily_returns.csv      one column per run + SPY
    subperiods.csv         metrics per run per regime window
    bootstrap_runs.csv     bootstrap CI per run per metric
    bootstrap_pairs.csv    paired differences (model vs markowitz, model vs equal) per profile
    bootstrap_models.csv   per-model averages over profiles, with CI
    corr_est.csv / corr_real.csv   correlation matrices for the heatmap figure

Run from the repo root:  uv run python poster/experiments/run_experiments.py  [n_bootstrap=5000]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PORTFOLIO = HERE.parent.parent          # repo root
RUNS = PORTFOLIO / "site" / "static" / "data" / "runs"
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(PORTFOLIO / "src"))
from portfolio.universe import SECTOR, TICKERS  # noqa: E402

TRADING_DAYS = 252
MODELS = ["markowitz", "markowitz_lw", "robust", "cvar", "equal"]
PROFILES = ["preserver", "steady", "builder", "maverick", "ethical"]   # Sprinter (3y horizon, ends Jan 2019) excluded: not comparable over the decade

PERIODS = {
    "2016-19 bull": ("2016-01-04", "2019-12-31"),
    "2020 COVID": ("2020-01-01", "2020-12-31"),
    "2021-22 rate shock": ("2021-01-01", "2022-12-31"),
    "2023-25 AI rally": ("2023-01-01", "2025-12-31"),
}

# --------------------------------------------------------------------------- load
def load_returns() -> tuple[pd.DataFrame, pd.Series]:
    cols, bench = {}, None
    for p in PROFILES:
        for m in MODELS:
            d = json.loads((RUNS / f"{p}__{m}.json").read_text())
            idx = pd.to_datetime(d["dates"])
            v = pd.Series(d["value"], index=idx, dtype=float)
            cols[f"{p}__{m}"] = v.pct_change()
            if bench is None:
                bench = pd.Series(d["benchmark"], index=idx, dtype=float).pct_change()
    df = pd.DataFrame(cols)
    df["SPY"] = bench
    return df.iloc[1:], pd.read_parquet(PORTFOLIO / "data/processed/rf.parquet")["rf"]


# --------------------------------------------------------------------------- metrics
def metrics(r: np.ndarray, rf: np.ndarray) -> dict:
    """r, rf: 1-d daily returns. Same definitions as portfolio.metrics.summarise."""
    if np.isnan(r).any():
        raise ValueError("NaN in return series")
    n = len(r)
    growth = np.cumprod(1 + r)
    cagr = growth[-1] ** (TRADING_DAYS / n) - 1
    sd = r.std(ddof=1)
    sharpe = (r - rf).mean() / sd * np.sqrt(TRADING_DAYS) if sd > 0 else 0.0
    dd = growth / np.maximum.accumulate(growth) - 1
    k = max(1, int(round(0.05 * n)))
    cvar = np.sort(-r)[-k:].mean()
    return {"cagr": cagr, "sharpe": sharpe, "max_drawdown": dd.min(), "cvar_95_daily": cvar,
            "volatility": sd * np.sqrt(TRADING_DAYS)}


METRIC_KEYS = ["cagr", "sharpe", "max_drawdown", "cvar_95_daily", "volatility"]


# --------------------------------------------------------------------------- experiment 1
def subperiods(ret: pd.DataFrame, rf: pd.Series) -> pd.DataFrame:
    rows = []
    for name, (a, b) in PERIODS.items():
        sl = ret.loc[a:b]
        rfs = rf.reindex(sl.index).fillna(0.0).to_numpy()
        for col in sl.columns:
            m = metrics(sl[col].to_numpy(), rfs)
            prof, _, mod = col.partition("__")
            rows.append({"period": name, "run": col, "profile": prof if mod else "benchmark",
                         "model": mod or "SPY", **m})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- experiment 2
def stationary_bootstrap_indices(n: int, mean_block: float, B: int, rng: np.random.Generator) -> np.ndarray:
    """Politis & Romano (1994). Returns B x n index arrays; blocks of geometric length."""
    p = 1.0 / mean_block
    out = np.empty((B, n), dtype=np.int64)
    for b in range(B):
        starts = rng.integers(0, n, size=n)
        new_block = rng.random(n) < p
        new_block[0] = True
        idx = np.empty(n, dtype=np.int64)
        cur = 0
        for t in range(n):
            cur = starts[t] if new_block[t] else (cur + 1) % n
            idx[t] = cur
        out[b] = idx
    return out


def bootstrap(ret: pd.DataFrame, rf: pd.Series, B: int = 5000, mean_block: float = 21.0, seed: int = 0):
    R = ret.to_numpy()                      # n x runs, SAME resample applied to every column (paired)
    rfv = rf.reindex(ret.index).fillna(0.0).to_numpy()
    n, K = R.shape
    rng = np.random.default_rng(seed)
    IDX = stationary_bootstrap_indices(n, mean_block, B, rng)
    stats = np.empty((B, K, len(METRIC_KEYS)))
    for b in range(B):
        Rb, rfb = R[IDX[b]], rfv[IDX[b]]
        for k in range(K):
            m = metrics(Rb[:, k], rfb)
            stats[b, k] = [m[key] for key in METRIC_KEYS]
        if b % 500 == 0:
            print(f"bootstrap {b}/{B}", flush=True)

    cols = list(ret.columns)
    point = {c: metrics(R[:, i], rfv) for i, c in enumerate(cols)}

    # per-run CI
    rows = []
    for i, c in enumerate(cols):
        prof, _, mod = c.partition("__")
        for j, key in enumerate(METRIC_KEYS):
            lo, hi = np.percentile(stats[:, i, j], [2.5, 97.5])
            rows.append({"run": c, "profile": prof if mod else "benchmark", "model": mod or "SPY",
                         "metric": key, "point": point[c][key], "boot_mean": stats[:, i, j].mean(),
                         "lo": lo, "hi": hi})
    runs_df = pd.DataFrame(rows)

    # paired differences within profile: model - reference
    pair_rows = []
    for prof in PROFILES:
        for ref in ["markowitz", "equal"]:
            ir = cols.index(f"{prof}__{ref}")
            for mod in MODELS:
                if mod == ref:
                    continue
                im = cols.index(f"{prof}__{mod}")
                for j, key in enumerate(METRIC_KEYS):
                    d = stats[:, im, j] - stats[:, ir, j]
                    lo, hi = np.percentile(d, [2.5, 97.5])
                    pair_rows.append({"profile": prof, "model": mod, "reference": ref, "metric": key,
                                      "point_diff": point[f"{prof}__{mod}"][key] - point[f"{prof}__{ref}"][key],
                                      "lo": lo, "hi": hi, "p_gt0": float((d > 0).mean())})
    pairs_df = pd.DataFrame(pair_rows)

    # per-model average over the six profiles (each bootstrap draw averaged, then CI)
    model_rows = []
    for mod in MODELS + ["SPY"]:
        ids = [cols.index("SPY")] if mod == "SPY" else [cols.index(f"{p}__{mod}") for p in PROFILES]
        for j, key in enumerate(METRIC_KEYS):
            avg = stats[:, ids, j].mean(axis=1)
            lo, hi = np.percentile(avg, [2.5, 97.5])
            model_rows.append({"model": mod, "metric": key,
                               "point": float(np.mean([point[cols[i]][key] for i in ids])),
                               "lo": lo, "hi": hi})
    models_df = pd.DataFrame(model_rows)
    return runs_df, pairs_df, models_df


# --------------------------------------------------------------------------- heatmap data
def correlation_pair():
    r = pd.read_parquet(PORTFOLIO / "data/processed/returns.parquet")[TICKERS]
    order = sorted(TICKERS, key=lambda t: (SECTOR[t], t))
    r = r[order]
    est = r.loc["2017-01-01":"2019-12-31"].corr()
    real = r.loc["2020-01-02":"2020-03-31"].corr()
    est.to_csv(OUT / "corr_est.csv")
    real.to_csv(OUT / "corr_real.csv")
    pd.Series({t: SECTOR[t] for t in order}).to_csv(OUT / "corr_sectors.csv", header=["sector"])
    print("mean off-diagonal corr: est %.2f, realised %.2f"
          % (est.values[np.triu_indices(len(order), 1)].mean(), real.values[np.triu_indices(len(order), 1)].mean()))


if __name__ == "__main__":
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    ret, rf = load_returns()
    ret.to_csv(OUT / "daily_returns.csv")
    print("loaded", ret.shape)

    sp = subperiods(ret, rf)
    sp.to_csv(OUT / "subperiods.csv", index=False)
    print("subperiods done")

    correlation_pair()

    runs_df, pairs_df, models_df = bootstrap(ret, rf, B=B)
    runs_df.to_csv(OUT / "bootstrap_runs.csv", index=False)
    pairs_df.to_csv(OUT / "bootstrap_pairs.csv", index=False)
    models_df.to_csv(OUT / "bootstrap_models.csv", index=False)
    print("bootstrap done")
    print(models_df[models_df.metric == "sharpe"].to_string(index=False))
