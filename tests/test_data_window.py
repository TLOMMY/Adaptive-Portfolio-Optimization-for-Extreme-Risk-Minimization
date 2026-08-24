"""Unit tests for MarketDataView construction, slicing and guards."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import make_prices

from src.config.settings import DataCutoff
from src.data.window import (
    InsufficientHistoryError,
    MarketDataView,
)


def test_view_reports_its_anchor_and_size(prices):
    as_of = prices.index[500]
    view = MarketDataView(prices, as_of)
    assert view.as_of == as_of
    assert view.n_observations == 501  # inclusive of the decision date
    assert view.tickers == list(prices.columns)
    assert view.cutoff is DataCutoff.INCLUSIVE


def test_view_accepts_a_string_date(prices):
    view = MarketDataView(prices, "2016-06-15")
    assert view.as_of == pd.Timestamp("2016-06-15")


def test_view_normalises_intraday_timestamps(prices):
    view = MarketDataView(prices, pd.Timestamp("2016-06-15 14:30:00"))
    assert view.as_of == pd.Timestamp("2016-06-15")


def test_view_rejects_a_non_dataframe():
    with pytest.raises(TypeError, match="must be a DataFrame"):
        MarketDataView([1, 2, 3], "2016-01-01")


def test_view_rejects_a_non_datetime_index():
    frame = pd.DataFrame({"AAA": [1.0, 2.0]}, index=[0, 1])
    with pytest.raises(TypeError, match="DatetimeIndex"):
        MarketDataView(frame, "2016-01-01")


def test_view_rejects_a_date_before_all_history(prices):
    with pytest.raises(InsufficientHistoryError, match="no observations"):
        MarketDataView(prices, "1990-01-01")


def test_returns_length_matches_requested_lookback(prices):
    view = MarketDataView(prices, prices.index[800])
    for lookback in (10, 60, 252):
        assert len(view.returns(lookback)) == lookback


def test_returns_consume_one_extra_price(prices):
    """`lookback_days` counts returns, so n+1 prices are required."""
    view = MarketDataView(prices, prices.index[800])
    assert len(view.prices(61)) == 61
    assert len(view.returns(60)) == 60


def test_returns_match_a_hand_computed_value(prices):
    as_of = prices.index[300]
    view = MarketDataView(prices, as_of)
    returns = view.returns(5)

    expected_last = prices.loc[as_of, "AAA"] / prices.loc[prices.index[299], "AAA"] - 1.0
    assert returns.loc[as_of, "AAA"] == pytest.approx(expected_last)


def test_returns_with_no_lookback_uses_all_visible_history(prices):
    view = MarketDataView(prices, prices.index[100])
    assert len(view.returns()) == 100  # 101 prices -> 100 returns


def test_returns_raise_when_only_one_observation_is_visible(prices):
    view = MarketDataView(prices, prices.index[0])
    with pytest.raises(InsufficientHistoryError, match="at least 2 price observations"):
        view.returns()


def test_require_history_enforces_a_minimum(prices):
    view = MarketDataView(prices, prices.index[30])
    with pytest.raises(InsufficientHistoryError, match="required"):
        view.require_history(minimum=60)
    view.require_history(minimum=10)  # must not raise


def test_incomplete_asset_raises_by_default():
    panel = make_prices(n_days=200, tickers=["AAA", "BBB"], seed=3)
    panel.loc[panel.index[:150], "BBB"] = np.nan  # BBB starts late

    view = MarketDataView(panel, panel.index[160])
    with pytest.raises(InsufficientHistoryError, match="BBB"):
        view.returns(100)


def test_incomplete_asset_can_be_dropped_explicitly():
    panel = make_prices(n_days=200, tickers=["AAA", "BBB"], seed=3)
    panel.loc[panel.index[:150], "BBB"] = np.nan

    view = MarketDataView(panel, panel.index[160])
    returns = view.returns(100, require_complete=False)
    assert list(returns.columns) == ["AAA"]


def test_interior_gap_is_forward_filled_to_a_zero_return():
    panel = make_prices(n_days=100, tickers=["AAA"], seed=11)
    gapped = panel.copy()
    gapped.loc[panel.index[50], "AAA"] = np.nan

    view = MarketDataView(gapped, panel.index[80])
    returns = view.returns(60)

    assert returns.loc[panel.index[50], "AAA"] == pytest.approx(0.0)
    assert not returns["AAA"].isna().any()


def test_latest_prices_returns_the_boundary_observation(prices):
    as_of = prices.index[400]
    view = MarketDataView(prices, as_of)
    pd.testing.assert_series_equal(
        view.latest_prices(), prices.loc[as_of], check_names=False
    )


def test_repr_is_informative(prices):
    view = MarketDataView(prices, prices.index[100])
    text = repr(view)
    assert "MarketDataView" in text and "inclusive" in text
