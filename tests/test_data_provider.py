"""Tests for the provider contract, the CSV snapshot and the cache.

Nothing here touches the network. The Yahoo provider's *transport* is out of
scope for the test suite by design -- what matters for reproducibility is that
the snapshot loads and satisfies the panel contract.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import make_prices

from src.config.assets import DEFAULT_UNIVERSE
from src.config.settings import DEFAULT_SNAPSHOT
from src.data.cache import ParquetCache, cache_key
from src.data.csv_provider import CsvProvider
from src.data.provider import (
    DataProviderError,
    MarketDataProvider,
    to_simple_returns,
    validate_price_panel,
)


class StubProvider(MarketDataProvider):
    """Returns a canned panel, so the base-class contract can be tested alone."""

    name = "stub"

    def __init__(self, panel: pd.DataFrame) -> None:
        self.panel = panel

    def _fetch(self, tickers, start, end):
        frame = self.panel.loc[:, [t for t in tickers if t in self.panel.columns]]
        if start is not None:
            frame = frame.loc[frame.index >= pd.Timestamp(start)]
        if end is not None:
            frame = frame.loc[frame.index <= pd.Timestamp(end)]
        return frame


@pytest.fixture
def stub_panel() -> pd.DataFrame:
    return make_prices(n_days=300, tickers=["AAA", "BBB", "CCC"], seed=99)


# ---------------------------------------------------------------------------
# Panel contract
# ---------------------------------------------------------------------------


def test_provider_returns_columns_in_requested_order(stub_panel):
    provider = StubProvider(stub_panel)
    panel = provider.get_adjusted_prices(["CCC", "AAA"])
    assert list(panel.columns) == ["CCC", "AAA"]


def test_provider_rejects_an_empty_ticker_list(stub_panel):
    with pytest.raises(ValueError, match="non-empty"):
        StubProvider(stub_panel).get_adjusted_prices([])


def test_provider_rejects_duplicate_tickers(stub_panel):
    with pytest.raises(ValueError, match="duplicate"):
        StubProvider(stub_panel).get_adjusted_prices(["AAA", "AAA"])


def test_provider_rejects_reversed_date_bounds(stub_panel):
    with pytest.raises(ValueError, match="precedes start"):
        StubProvider(stub_panel).get_adjusted_prices(
            ["AAA"], start=pd.Timestamp("2016-01-01").date(),
            end=pd.Timestamp("2015-01-01").date(),
        )


def test_provider_reports_a_missing_ticker(stub_panel):
    with pytest.raises(DataProviderError, match="missing columns"):
        StubProvider(stub_panel).get_adjusted_prices(["AAA", "ZZZ"])


def test_validation_rejects_non_positive_prices(stub_panel):
    bad = stub_panel.copy()
    bad.iloc[10, 0] = -1.0
    with pytest.raises(DataProviderError, match="non-positive"):
        validate_price_panel(bad, list(bad.columns))


def test_validation_rejects_duplicate_dates(stub_panel):
    doubled = pd.concat([stub_panel, stub_panel.iloc[[5]]])
    with pytest.raises(DataProviderError, match="duplicate dates"):
        validate_price_panel(doubled, list(stub_panel.columns))


def test_validation_rejects_an_all_nan_column(stub_panel):
    bad = stub_panel.copy()
    bad["BBB"] = np.nan
    with pytest.raises(DataProviderError, match="no data at all"):
        validate_price_panel(bad, list(bad.columns))


def test_validation_rejects_an_empty_panel():
    with pytest.raises(DataProviderError, match="empty panel"):
        validate_price_panel(pd.DataFrame(), [])


def test_validation_sorts_and_normalises_the_index(stub_panel):
    shuffled = stub_panel.iloc[::-1].copy()
    shuffled.index = shuffled.index + pd.Timedelta(hours=14, minutes=30)
    out = validate_price_panel(shuffled, list(stub_panel.columns))

    assert out.index.is_monotonic_increasing
    assert (out.index == out.index.normalize()).all()
    assert out.index.name == "date"


def test_validation_strips_timezone_information(stub_panel):
    tz_aware = stub_panel.copy()
    tz_aware.index = tz_aware.index.tz_localize("UTC")
    out = validate_price_panel(tz_aware, list(stub_panel.columns))
    assert out.index.tz is None


def test_validation_permits_leading_gaps(stub_panel):
    late = stub_panel.copy()
    late.loc[late.index[:50], "BBB"] = np.nan
    out = validate_price_panel(late, list(late.columns))
    assert out["BBB"].isna().sum() == 50


# ---------------------------------------------------------------------------
# Return conversion
# ---------------------------------------------------------------------------


def test_simple_returns_match_the_definition(stub_panel):
    returns = to_simple_returns(stub_panel)
    assert len(returns) == len(stub_panel) - 1
    expected = stub_panel["AAA"].iloc[5] / stub_panel["AAA"].iloc[4] - 1.0
    assert returns["AAA"].iloc[4] == pytest.approx(expected)


def test_simple_returns_reject_an_empty_panel():
    with pytest.raises(ValueError, match="empty price panel"):
        to_simple_returns(pd.DataFrame())


# ---------------------------------------------------------------------------
# CSV snapshot
# ---------------------------------------------------------------------------


def test_snapshot_round_trips_through_the_provider(tmp_path, stub_panel):
    path = tmp_path / "snap.csv"
    CsvProvider.write_snapshot(stub_panel, path)
    reloaded = CsvProvider(path).get_adjusted_prices(list(stub_panel.columns))

    pd.testing.assert_index_equal(reloaded.index, stub_panel.index)
    assert np.allclose(reloaded.to_numpy(), stub_panel.to_numpy(), rtol=1e-6)


def test_csv_provider_slices_inclusively(tmp_path, stub_panel):
    path = tmp_path / "snap.csv"
    CsvProvider.write_snapshot(stub_panel, path)

    start, end = stub_panel.index[10], stub_panel.index[20]
    sliced = CsvProvider(path).get_adjusted_prices(
        ["AAA"], start=start.date(), end=end.date()
    )
    assert sliced.index.min() == start
    assert sliced.index.max() == end
    assert len(sliced) == 11


def test_csv_provider_reports_a_missing_file(tmp_path):
    with pytest.raises(DataProviderError, match="snapshot not found"):
        CsvProvider(tmp_path / "absent.csv").get_adjusted_prices(["AAA"])


def test_csv_provider_reports_a_missing_column(tmp_path, stub_panel):
    path = tmp_path / "snap.csv"
    CsvProvider.write_snapshot(stub_panel, path)
    with pytest.raises(DataProviderError, match="no column"):
        CsvProvider(path).get_adjusted_prices(["AAA", "NOPE"])


def test_csv_provider_reports_an_empty_slice(tmp_path, stub_panel):
    path = tmp_path / "snap.csv"
    CsvProvider.write_snapshot(stub_panel, path)
    with pytest.raises(DataProviderError, match="no rows"):
        CsvProvider(path).get_adjusted_prices(
            ["AAA"], start=pd.Timestamp("2030-01-01").date(),
            end=pd.Timestamp("2031-01-01").date(),
        )


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def test_cache_round_trips_a_panel(tmp_path, stub_panel):
    cache = ParquetCache(tmp_path)
    assert cache.load("missing") is None

    cache.store("k", stub_panel)
    # `check_freq=False`: parquet stores dates, not the synthetic BusinessDay
    # frequency this fixture happens to carry. The panel contract does not
    # include a frequency, and real vendor panels have none.
    pd.testing.assert_frame_equal(cache.load("k"), stub_panel, check_freq=False)


def test_cache_key_is_stable_and_order_insensitive():
    from datetime import date

    a = cache_key("yahoo", ["AAA", "BBB"], date(2016, 1, 1), None)
    b = cache_key("yahoo", ["BBB", "AAA"], date(2016, 1, 1), None)
    c = cache_key("yahoo", ["AAA", "BBB"], date(2017, 1, 1), None)
    assert a == b
    assert a != c


def test_cache_clear_removes_files(tmp_path, stub_panel):
    cache = ParquetCache(tmp_path)
    cache.store("a", stub_panel)
    cache.store("b", stub_panel)
    assert cache.clear() == 2
    assert cache.load("a") is None


# ---------------------------------------------------------------------------
# The committed snapshot must support the configured experiment
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not DEFAULT_SNAPSHOT.exists(), reason="snapshot not generated")
def test_committed_snapshot_covers_the_default_universe():
    panel = CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)
    assert list(panel.columns) == DEFAULT_UNIVERSE.tickers
    assert panel.index.is_monotonic_increasing
    assert not panel.index.has_duplicates


@pytest.mark.skipif(not DEFAULT_SNAPSHOT.exists(), reason="snapshot not generated")
def test_committed_snapshot_supports_the_default_experiment():
    """Every asset must have a full estimation window before the first decision."""
    from src.config.settings import BacktestSettings

    settings = BacktestSettings()
    panel = CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)

    first_decision = panel.index[panel.index >= pd.Timestamp(settings.start)][0]
    window = panel.loc[panel.index <= first_decision]

    assert len(window) >= settings.lookback_days + 1, (
        f"only {len(window)} observations before {first_decision.date()}; "
        f"{settings.lookback_days + 1} needed"
    )
    estimation_window = window.tail(settings.lookback_days + 1)
    assert not estimation_window.isna().any().any(), (
        "an asset has missing data inside the first estimation window"
    )


@pytest.mark.skipif(not DEFAULT_SNAPSHOT.exists(), reason="snapshot not generated")
def test_committed_snapshot_has_no_interior_gaps():
    panel = CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)
    for ticker in panel.columns:
        series = panel[ticker]
        first = series.first_valid_index()
        assert series.loc[first:].isna().sum() == 0, f"{ticker} has interior gaps"
