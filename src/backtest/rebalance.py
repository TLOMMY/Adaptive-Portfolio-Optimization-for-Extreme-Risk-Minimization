"""Rebalance-date generation.

Decision dates are derived from the *actual trading calendar implied by the price
data*, never from a synthetic calendar.  A scheduled date that falls on a weekend
or market holiday is snapped forward to the next real trading day, so the engine
never attempts to make a decision on a date for which no price exists.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.config.settings import RebalanceFrequency


def generate_rebalance_dates(
    trading_days: pd.DatetimeIndex,
    start: date | pd.Timestamp,
    end: date | pd.Timestamp,
    frequency: RebalanceFrequency = RebalanceFrequency.QUARTERLY,
) -> list[pd.Timestamp]:
    """Decision dates within ``[start, end]``, snapped onto the trading calendar.

    Scheduled dates are anchored at ``start`` and advanced by the frequency's
    month step. Each is snapped *forward* to the first available trading day;
    snapping forward rather than backward guarantees the decision date is never
    earlier than scheduled, which would silently shorten the first holding period.

    Parameters
    ----------
    trading_days
        The available trading calendar, typically the price panel's index.
    start, end
        Inclusive bounds for decision dates.
    frequency
        Rebalancing cadence.

    Returns
    -------
    list[pandas.Timestamp]
        Strictly increasing, duplicate-free decision dates. Empty if no
        scheduled date has a trading day at or after it within ``end``.
    """
    if not isinstance(trading_days, pd.DatetimeIndex):
        raise TypeError("trading_days must be a DatetimeIndex")
    if len(trading_days) == 0:
        raise ValueError("trading_days is empty")

    calendar = trading_days.sort_values().normalize().unique()
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    if end_ts < start_ts:
        raise ValueError(f"end ({end_ts.date()}) precedes start ({start_ts.date()})")

    step = pd.DateOffset(months=frequency.months)

    dates: list[pd.Timestamp] = []
    scheduled = start_ts
    seen: set[pd.Timestamp] = set()

    while scheduled <= end_ts:
        position = calendar.searchsorted(scheduled, side="left")
        if position >= len(calendar):
            break  # no trading day remains at or after this scheduled date
        actual = calendar[position]
        if actual > end_ts:
            break
        if actual not in seen:
            seen.add(actual)
            dates.append(actual)
        scheduled = scheduled + step

    return dates


def holding_periods(
    rebalance_dates: list[pd.Timestamp],
    trading_days: pd.DatetimeIndex,
    end: date | pd.Timestamp,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Return ``(first_day, last_day)`` of the holding period for each decision.

    Weights chosen at decision date ``t`` earn returns from the **next** trading
    day through the following decision date inclusive. The half-open convention
    ``(t, t_next]`` on decision dates is what prevents a portfolio from being
    credited with the return of the day it was formed on -- a subtle but real
    form of look-ahead.

    The final period runs to ``end`` (or the last available trading day).
    """
    if not rebalance_dates:
        return []

    calendar = trading_days.sort_values().normalize().unique()
    end_ts = pd.Timestamp(end).normalize()
    last_available = calendar[calendar <= end_ts]
    if len(last_available) == 0:
        raise ValueError(f"no trading days at or before end ({end_ts.date()})")
    final_day = last_available[-1]

    periods: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for i, decision in enumerate(rebalance_dates):
        position = calendar.searchsorted(decision, side="right")
        if position >= len(calendar):
            continue  # decision on the last trading day: no holding period follows
        first_day = calendar[position]
        last_day = rebalance_dates[i + 1] if i + 1 < len(rebalance_dates) else final_day
        if first_day > last_day:
            continue
        periods.append((first_day, last_day))
    return periods
