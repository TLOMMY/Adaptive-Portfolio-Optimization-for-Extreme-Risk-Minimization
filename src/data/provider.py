"""Market-data provider abstraction.

A provider's single responsibility is to return a *validated panel of adjusted
closing prices*.  Providers know nothing about estimation, optimization or
backtesting; conversely nothing downstream knows where prices came from.

The panel contract
------------------
Every provider returns a ``pandas.DataFrame`` with:

* a ``DatetimeIndex`` named ``date``, timezone-naive, sorted strictly ascending,
  with no duplicates;
* one float64 column per requested ticker, in the order requested;
* adjusted closing prices (dividends reinvested, splits applied);
* no negative or zero prices.

Leading NaNs are permitted (an instrument may not have existed yet).  Interior
NaNs are permitted at this layer and are resolved downstream, where the decision
date is known -- filling them here would require deciding *how* to fill without
knowing whether the fill would cross a decision boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

DATE_INDEX_NAME = "date"


class DataProviderError(RuntimeError):
    """Raised when a provider cannot satisfy a request."""


class MarketDataProvider(ABC):
    """Base class for all sources of adjusted price history."""

    name: str = "abstract"

    @abstractmethod
    def _fetch(self, tickers: list[str], start: date | None, end: date | None) -> pd.DataFrame:
        """Return a raw adjusted-close panel. Subclass responsibility."""

    def get_adjusted_prices(
        self,
        tickers: list[str],
        start: date | None = None,
        end: date | None = None,
    ) -> pd.DataFrame:
        """Fetch and validate an adjusted-close panel.

        Parameters
        ----------
        tickers
            Instruments to fetch. The returned column order matches this list.
        start, end
            Inclusive date bounds. ``None`` means "as far back / forward as the
            source provides".
        """
        if not tickers:
            raise ValueError("tickers must be a non-empty list")
        if len(set(tickers)) != len(tickers):
            raise ValueError(f"duplicate tickers requested: {tickers}")
        if start is not None and end is not None and end < start:
            raise ValueError(f"end ({end}) precedes start ({start})")

        panel = self._fetch(list(tickers), start, end)
        return validate_price_panel(panel, expected_tickers=list(tickers), source=self.name)


def validate_price_panel(
    panel: pd.DataFrame,
    expected_tickers: list[str],
    source: str = "unknown",
) -> pd.DataFrame:
    """Enforce the panel contract, returning a normalised copy.

    Raises ``DataProviderError`` on any violation. This is deliberately strict:
    a malformed panel that slips through here becomes a silently wrong backtest
    much later, where it is far harder to diagnose.
    """
    if not isinstance(panel, pd.DataFrame):
        raise DataProviderError(f"[{source}] expected a DataFrame, got {type(panel).__name__}")
    if panel.empty:
        raise DataProviderError(f"[{source}] returned an empty panel")

    missing = [t for t in expected_tickers if t not in panel.columns]
    if missing:
        raise DataProviderError(f"[{source}] missing columns for tickers: {missing}")

    out = panel.loc[:, expected_tickers].copy()

    if not isinstance(out.index, pd.DatetimeIndex):
        try:
            out.index = pd.DatetimeIndex(out.index)
        except Exception as exc:  # pragma: no cover - defensive
            raise DataProviderError(f"[{source}] index is not date-like: {exc}") from exc

    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    out.index = out.index.normalize()
    out.index.name = DATE_INDEX_NAME

    if out.index.has_duplicates:
        dupes = out.index[out.index.duplicated()].unique().tolist()
        raise DataProviderError(f"[{source}] duplicate dates in index: {dupes[:5]}")

    if not out.index.is_monotonic_increasing:
        out = out.sort_index()

    out = out.astype("float64")

    non_positive = (out <= 0).to_numpy().sum()
    if non_positive:
        raise DataProviderError(f"[{source}] panel contains {non_positive} non-positive prices")

    all_nan = [c for c in out.columns if out[c].isna().all()]
    if all_nan:
        raise DataProviderError(f"[{source}] no data at all for: {all_nan}")

    return out


def to_simple_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Convert an adjusted-price panel to simple daily returns.

    ``r_t = P_t / P_{t-1} - 1`` (see ``settings.RETURN_CONVENTION``).

    The first row is dropped: a return needs two prices, so a panel of ``n``
    prices yields ``n - 1`` returns. Callers that need returns over a specific
    window must therefore request one extra price observation.
    """
    if prices.empty:
        raise ValueError("cannot compute returns from an empty price panel")
    return prices.pct_change().iloc[1:]
