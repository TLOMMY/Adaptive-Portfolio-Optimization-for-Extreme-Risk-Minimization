"""``MarketDataView`` -- the look-ahead firewall.

Motivation
----------
Look-ahead bias is the central methodological risk in a historical replay study.
Tests can *detect* it after the fact; the goal here is to make it structurally
unrepresentable.

The mechanism is deliberately blunt.  A ``MarketDataView`` is constructed for a
single decision date ``as_of``.  At construction it slices the price panel to
that date and **retains only the slice**.  It holds no reference of any kind to
the full panel, so data after ``as_of`` is not merely forbidden to estimators --
it is not present in the object graph they can reach.

Every consumer of market data during a decision (parameter estimation,
optimization, constraint construction) receives a ``MarketDataView`` and never
the raw panel.  The backtest engine is the only component that holds the full
history, and it uses the post-``as_of`` portion for exactly one purpose:
recording realised performance *after* the decision has been made and locked.

Cutoff convention
-----------------
``DataCutoff.INCLUSIVE`` (default) admits observations with ``date <= as_of``:
the decision maker observes the closing price on the decision date and is
assumed to transact at it.  ``DataCutoff.EXCLUSIVE`` admits ``date < as_of``
strictly.  The convention is recorded on the view so downstream code and
diagnostics can report which was used.
"""

from __future__ import annotations

import pandas as pd

from src.config.settings import (
    MIN_OBSERVATIONS_FOR_ESTIMATION,
    DataCutoff,
)


class LookAheadError(RuntimeError):
    """Raised when data at or beyond the decision boundary is requested.

    Any occurrence of this exception is a methodological defect, not a
    recoverable runtime condition. It should never be caught and suppressed.
    """


class InsufficientHistoryError(RuntimeError):
    """Raised when the estimation window contains too little usable data."""


class MarketDataView:
    """An immutable window of market data truncated at a decision date.

    Parameters
    ----------
    prices
        Full adjusted-price panel. It is sliced immediately and **not retained**.
    as_of
        The decision date.
    cutoff
        Whether ``as_of`` itself is admissible (see module docstring).

    Notes
    -----
    Instances are treated as immutable. The frames returned by :meth:`prices`
    and :meth:`returns` are copies, so a consumer cannot mutate the view's state.
    """

    __slots__ = ("_visible", "_as_of", "_cutoff")

    def __init__(
        self,
        prices: pd.DataFrame,
        as_of: pd.Timestamp | str,
        cutoff: DataCutoff = DataCutoff.INCLUSIVE,
    ) -> None:
        if not isinstance(prices, pd.DataFrame):
            raise TypeError(f"prices must be a DataFrame, got {type(prices).__name__}")
        if not isinstance(prices.index, pd.DatetimeIndex):
            raise TypeError("prices must be indexed by a DatetimeIndex")

        as_of = pd.Timestamp(as_of).normalize()

        # The single slicing operation that defines the firewall. `_visible` is
        # a copy; `prices` goes out of scope with the constructor.
        mask = prices.index <= as_of if cutoff is DataCutoff.INCLUSIVE else prices.index < as_of
        visible = prices.loc[mask].copy()

        if visible.empty:
            raise InsufficientHistoryError(
                f"no observations at or before {as_of.date()} "
                f"(panel starts {prices.index.min().date() if len(prices) else 'n/a'})"
            )

        self._visible = visible
        self._as_of = as_of
        self._cutoff = cutoff

    # -- identity ------------------------------------------------------------

    @property
    def as_of(self) -> pd.Timestamp:
        """The decision date this view is anchored to."""
        return self._as_of

    @property
    def cutoff(self) -> DataCutoff:
        return self._cutoff

    @property
    def tickers(self) -> list[str]:
        return list(self._visible.columns)

    @property
    def n_observations(self) -> int:
        """Total number of visible price observations."""
        return len(self._visible)

    @property
    def last_date(self) -> pd.Timestamp:
        """Most recent visible date. Never after ``as_of``, by construction."""
        return self._visible.index[-1]

    def __repr__(self) -> str:
        return (
            f"MarketDataView(as_of={self._as_of.date()}, cutoff={self._cutoff.value}, "
            f"n_obs={self.n_observations}, tickers={len(self.tickers)})"
        )

    # -- data access ---------------------------------------------------------

    def prices(self, lookback_days: int | None = None) -> pd.DataFrame:
        """Visible adjusted prices, optionally limited to the most recent window.

        Parameters
        ----------
        lookback_days
            Number of trailing observations to return. ``None`` returns all
            visible history.
        """
        frame = self._visible if lookback_days is None else self._visible.tail(lookback_days)
        return frame.copy()

    def returns(
        self,
        lookback_days: int | None = None,
        require_complete: bool = True,
    ) -> pd.DataFrame:
        """Simple daily returns over the trailing estimation window.

        ``lookback_days`` counts *returns*, not prices. Because a return needs
        two prices, ``lookback_days + 1`` price observations are consumed.

        Interior gaps are forward-filled within the window before differencing:
        a missing quote is treated as "no new information", which yields a zero
        return for that day rather than an artificial jump. Forward-filling uses
        only data already inside the view, so it cannot cross the decision
        boundary.

        Parameters
        ----------
        require_complete
            If True, raise when any asset still has missing values after
            forward-filling (i.e. the asset has insufficient history in this
            window). If False, such columns are dropped and the caller is
            responsible for handling the reduced universe.
        """
        n_prices = None if lookback_days is None else lookback_days + 1
        window = self.prices(n_prices)

        if len(window) < 2:
            raise InsufficientHistoryError(
                f"need at least 2 price observations to form a return; "
                f"have {len(window)} as of {self._as_of.date()}"
            )

        window = window.ffill()
        returns = window.pct_change().iloc[1:]

        incomplete = [c for c in returns.columns if returns[c].isna().any()]
        if incomplete:
            if require_complete:
                raise InsufficientHistoryError(
                    f"insufficient history as of {self._as_of.date()} for: {incomplete}. "
                    f"Window starts {window.index[0].date()}."
                )
            returns = returns.drop(columns=incomplete)

        return returns

    def latest_prices(self) -> pd.Series:
        """Most recent visible price per asset (forward-filled across gaps)."""
        return self._visible.ffill().iloc[-1].copy()

    # -- guards --------------------------------------------------------------

    def require_history(self, minimum: int = MIN_OBSERVATIONS_FOR_ESTIMATION) -> None:
        """Raise ``InsufficientHistoryError`` unless enough observations exist."""
        if self.n_observations < minimum:
            raise InsufficientHistoryError(
                f"{self.n_observations} observations available as of "
                f"{self._as_of.date()}; {minimum} required"
            )

    def assert_within_boundary(self) -> None:
        """Self-check that no visible observation violates the cutoff.

        Invariant held by construction; asserted explicitly so the guarantee is
        verifiable at runtime and directly testable.
        """
        latest = self._visible.index.max()
        violated = latest > self._as_of if self._cutoff is DataCutoff.INCLUSIVE else latest >= self._as_of
        if violated:
            raise LookAheadError(
                f"view anchored at {self._as_of.date()} (cutoff={self._cutoff.value}) "
                f"exposes an observation dated {latest.date()}"
            )
