"""Day 2 data and evaluation-window helpers.

The loader keeps the project's data contract explicit: one date column and
one adjusted-close column per asset in the wide DataFrame used by the
backtester. Yahoo Finance is optional; cached CSV input is the reproducible
path for the team repository.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from portfolio_backtest import BacktestWindow, compute_returns, validate_prices


DEFAULT_TICKERS = ("SPY", "QQQ", "IWM", "EFA", "EEM", "IEF", "TLT", "GLD", "VNQ")


def load_adjusted_close_csv(
    path: str | Path,
    *,
    date_column: str = "date",
    assets: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Load a cached wide adjusted-close CSV and validate it."""

    frame = pd.read_csv(path)
    if date_column not in frame.columns:
        raise ValueError(f"CSV must contain a '{date_column}' column")
    frame[date_column] = pd.to_datetime(frame[date_column], errors="raise")
    prices = frame.set_index(date_column).sort_index()
    if assets is not None:
        missing = sorted(set(assets) - set(prices.columns))
        if missing:
            raise ValueError(f"CSV is missing requested assets: {missing}")
        prices = prices.loc[:, list(assets)]
    return validate_prices(prices)


def save_adjusted_close_csv(prices: pd.DataFrame, path: str | Path) -> Path:
    """Validate and save a wide adjusted-close table."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = validate_prices(prices)
    normalized.rename_axis("date").to_csv(target, date_format="%Y-%m-%d")
    return target


def download_adjusted_close(
    tickers: Iterable[str],
    *,
    start: str,
    end: str,
    cache_path: str | Path | None = None,
) -> pd.DataFrame:
    """Download adjusted close prices using optional yfinance.

    The function fails with an actionable message when yfinance is not
    installed. If `cache_path` exists, it is loaded without network access.
    """

    if cache_path is not None and Path(cache_path).exists():
        return load_adjusted_close_csv(cache_path, assets=list(tickers))
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance is required for a network download; install it or provide a cached CSV"
        ) from exc

    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        raise ValueError("at least one ticker is required")
    downloaded = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        group_by="column",
    )
    if downloaded.empty:
        raise ValueError("Yahoo Finance returned no price data")
    if isinstance(downloaded.columns, pd.MultiIndex):
        level = "Adj Close" if "Adj Close" in downloaded.columns.get_level_values(0) else "Close"
        prices = downloaded[level].copy()
    else:
        level = "Adj Close" if "Adj Close" in downloaded.columns else "Close"
        prices = downloaded[[level]].rename(columns={level: tickers[0]})
    prices = prices.reindex(columns=tickers).dropna(how="any")
    prices = validate_prices(prices)
    if cache_path is not None:
        save_adjusted_close_csv(prices, cache_path)
    return prices


def build_market_period_windows(
    returns: pd.DataFrame,
    periods: Sequence[tuple[str, str, str]],
    *,
    train_years: int = 3,
) -> list[BacktestWindow]:
    """Build leakage-safe windows for multiple market evaluation periods.

    Each tuple is `(name, test_start, test_end)`. The training end equals the
    test start and is exclusive, so the test period is never used for fitting.
    """

    if train_years < 1:
        raise ValueError("train_years must be at least one")
    returns = returns.sort_index()
    windows: list[BacktestWindow] = []
    for name, test_start, test_end in periods:
        test_start_ts = pd.Timestamp(test_start)
        train_start_ts = test_start_ts - pd.DateOffset(years=train_years)
        windows.append(
            BacktestWindow(
                name=name,
                train_start=train_start_ts,
                train_end=test_start_ts,
                test_start=test_start_ts,
                test_end=pd.Timestamp(test_end),
            )
        )
    return windows


def prepare_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Convenience wrapper used by the Day 2 baseline."""

    return compute_returns(validate_prices(prices))
