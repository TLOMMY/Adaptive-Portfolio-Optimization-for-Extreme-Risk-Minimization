"""Tests for decision-date generation against a real trading calendar."""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import make_prices

from src.backtest.rebalance import generate_rebalance_dates, holding_periods
from src.config.settings import RebalanceFrequency


@pytest.fixture
def calendar() -> pd.DatetimeIndex:
    return make_prices(n_days=2000, start="2012-01-02").index


def test_quarterly_dates_land_on_quarter_starts(calendar):
    dates = generate_rebalance_dates(
        calendar, "2016-01-01", "2017-12-31", RebalanceFrequency.QUARTERLY
    )
    assert len(dates) == 8
    assert [d.month for d in dates] == [1, 4, 7, 10, 1, 4, 7, 10]
    assert [d.year for d in dates] == [2016] * 4 + [2017] * 4


def test_dates_snap_forward_to_a_real_trading_day(calendar):
    """2016-01-01 is a holiday; the decision must move forward, never backward."""
    dates = generate_rebalance_dates(
        calendar, "2016-01-01", "2016-12-31", RebalanceFrequency.QUARTERLY
    )
    first = dates[0]
    assert first >= pd.Timestamp("2016-01-01")
    assert first in calendar


def test_every_decision_date_exists_in_the_calendar(calendar):
    for frequency in RebalanceFrequency:
        dates = generate_rebalance_dates(calendar, "2015-01-01", "2018-12-31", frequency)
        assert dates, f"no dates generated for {frequency}"
        assert all(d in calendar for d in dates)


def test_dates_are_strictly_increasing_and_unique(calendar):
    dates = generate_rebalance_dates(
        calendar, "2013-01-01", "2019-12-31", RebalanceFrequency.MONTHLY
    )
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)


def test_frequency_controls_the_number_of_decisions(calendar):
    counts = {
        f: len(generate_rebalance_dates(calendar, "2014-01-01", "2018-12-31", f))
        for f in RebalanceFrequency
    }
    assert counts[RebalanceFrequency.MONTHLY] == 60
    assert counts[RebalanceFrequency.QUARTERLY] == 20
    assert counts[RebalanceFrequency.SEMIANNUAL] == 10
    assert counts[RebalanceFrequency.ANNUAL] == 5


def test_dates_respect_both_bounds(calendar):
    start, end = pd.Timestamp("2015-03-01"), pd.Timestamp("2016-09-30")
    dates = generate_rebalance_dates(calendar, start, end, RebalanceFrequency.QUARTERLY)
    assert dates[0] >= start
    assert dates[-1] <= end


def test_end_before_start_is_rejected(calendar):
    with pytest.raises(ValueError, match="precedes start"):
        generate_rebalance_dates(calendar, "2017-01-01", "2016-01-01")


def test_empty_calendar_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        generate_rebalance_dates(pd.DatetimeIndex([]), "2016-01-01", "2017-01-01")


def test_no_dates_when_the_window_precedes_the_calendar(calendar):
    dates = generate_rebalance_dates(calendar, "1990-01-01", "1991-01-01")
    assert dates == []


def test_holding_periods_start_after_their_decision_date(calendar):
    dates = generate_rebalance_dates(
        calendar, "2016-01-01", "2017-12-31", RebalanceFrequency.QUARTERLY
    )
    periods = holding_periods(dates, calendar, "2017-12-31")
    assert len(periods) == len(dates)
    for decision, (first_day, last_day) in zip(dates, periods, strict=True):
        assert first_day > decision
        assert last_day >= first_day


def test_holding_periods_are_contiguous_and_cover_the_window(calendar):
    dates = generate_rebalance_dates(
        calendar, "2016-01-01", "2017-12-31", RebalanceFrequency.QUARTERLY
    )
    periods = holding_periods(dates, calendar, "2017-12-31")

    # Each period ends on the next decision date, so the following period starts
    # on the very next trading day: no gaps, no overlaps.
    for i in range(len(periods) - 1):
        assert periods[i][1] == dates[i + 1]
        assert periods[i + 1][0] > periods[i][1]

    assert periods[-1][1] <= pd.Timestamp("2017-12-31")


def test_holding_periods_of_no_decisions_is_empty(calendar):
    assert holding_periods([], calendar, "2017-12-31") == []
