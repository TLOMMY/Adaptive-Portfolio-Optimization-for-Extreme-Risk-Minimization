"""Fetch, cache and clean market data.

Everything raw lands in data/raw/ (gitignored) so re-runs are free; the cleaned
wide tables are written to data/processed/ as parquet and are what the rest of
the pipeline reads.

Look-ahead safety: this module only *stores* history.  The rule that a model at
date t may only see rows strictly before t is enforced in backtest.py, not here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from .universe import BENCHMARK, CASH, TICKERS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

START = "2008-04-01"          # earliest date every ticker trades (PM listed Mar 2008)
                              # tuning period 2011-2015, journey 2016-2026
TRADING_DAYS = 252


def fetch_prices(tickers: list[str], start: str = START, refresh: bool = False) -> pd.DataFrame:
    """Download daily OHLCV for each ticker (dividend- and split-adjusted).

    Returns a long DataFrame with columns [date, ticker, close, volume].
    """
    RAW.mkdir(parents=True, exist_ok=True)
    frames = []
    for t in tickers:
        path = RAW / f"{t}.parquet"
        if path.exists() and not refresh:
            df = pd.read_parquet(path)
        else:
            hist = yf.Ticker(t).history(start=start, auto_adjust=True, actions=False)
            if hist.empty:
                raise RuntimeError(f"no data returned for {t}")
            df = (
                hist[["Close", "Volume"]]
                .rename(columns={"Close": "close", "Volume": "volume"})
                .rename_axis("date")
                .reset_index()
            )
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
            df["ticker"] = t
            df.to_parquet(path, index=False)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def fetch_tbill(start: str = START, refresh: bool = False) -> pd.Series:
    """Daily 3-month T-bill *annualised* yield in percent, from FRED (series DTB3).

    Falls back to yfinance's ^IRX (13-week bill discount rate) if FRED is down.
    """
    path = RAW / "tbill.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)["rate"]
    try:
        from pandas_datareader import data as pdr

        s = pdr.DataReader("DTB3", "fred", start)["DTB3"]
    except Exception:
        s = yf.Ticker("^IRX").history(start=start)["Close"]
        s.index = pd.to_datetime(s.index).tz_localize(None)
    s = s.rename("rate").rename_axis("date").astype(float)
    s.index = pd.to_datetime(s.index).normalize()
    s.to_frame().to_parquet(path)
    return s


def build_dataset(refresh: bool = False) -> dict[str, pd.DataFrame]:
    """Produce the cleaned wide tables the pipeline consumes and save them.

    prices:  close by date x asset, including a synthetic CASH column that
             compounds at the T-bill rate, and the SPY benchmark.
    volume:  dollar volume (close * shares) by date x ticker, for liquidity caps.
    returns: simple daily returns of `prices`.
    """
    long = fetch_prices(TICKERS + [BENCHMARK], refresh=refresh)
    close = long.pivot(index="date", columns="ticker", values="close").sort_index()
    volume = long.pivot(index="date", columns="ticker", values="volume").sort_index()

    # Keep only dates where every ticker traded (drops a handful of odd days).
    close = close.dropna(how="any")
    volume = volume.loc[close.index]
    dollar_volume = (close * volume).drop(columns=BENCHMARK)

    # Synthetic cash: grows by the daily T-bill rate, forward-filled over gaps.
    tbill = fetch_tbill(refresh=refresh).reindex(close.index).ffill().bfill()
    daily_rf = (1 + tbill / 100) ** (1 / TRADING_DAYS) - 1
    close[CASH] = (1 + daily_rf).cumprod()

    returns = close.pct_change().iloc[1:]
    close = close.iloc[1:]
    dollar_volume = dollar_volume.iloc[1:]

    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = {"prices": close, "volume": dollar_volume, "returns": returns, "rf": daily_rf.iloc[1:].to_frame("rf")}
    for k, v in out.items():
        v.to_parquet(PROCESSED / f"{k}.parquet")
    return out


def load_dataset() -> dict[str, pd.DataFrame]:
    return {k: pd.read_parquet(PROCESSED / f"{k}.parquet") for k in ("prices", "volume", "returns", "rf")}


if __name__ == "__main__":
    d = build_dataset()
    p = d["prices"]
    print(f"{p.shape[0]} trading days x {p.shape[1]} assets, {p.index.min().date()} -> {p.index.max().date()}")
    print("NaNs:", int(p.isna().sum().sum()))
    print("days with |return| > 40%:", int((d["returns"].drop(columns=CASH).abs() > 0.4).sum().sum()))
