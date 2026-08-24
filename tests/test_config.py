"""Tests for configuration objects and their validation."""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from src.config.assets import (
    DEFAULT_UNIVERSE,
    UNIVERSES,
    AssetClass,
    AssetSpec,
    Universe,
)
from src.config.settings import (
    TRADING_DAYS_PER_YEAR,
    BacktestSettings,
    DataCutoff,
    RebalanceFrequency,
)

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_default_settings_match_the_specified_experiment():
    s = BacktestSettings()
    assert s.start == date(2016, 1, 1)
    assert s.lookback_years == 3.0
    assert s.rebalance_frequency is RebalanceFrequency.QUARTERLY
    assert s.cutoff is DataCutoff.INCLUSIVE
    assert s.transaction_cost_bps == 0.0, "the validated baseline must be cost-free"
    assert s.risk_horizon_days == 1, "MVP reports daily CVaR"


def test_lookback_days_derive_from_the_trading_year():
    assert BacktestSettings(lookback_years=3.0).lookback_days == 3 * TRADING_DAYS_PER_YEAR
    assert BacktestSettings(lookback_years=0.5).lookback_days == TRADING_DAYS_PER_YEAR // 2


def test_settings_are_immutable():
    s = BacktestSettings()
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.start = date(2017, 1, 1)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"start": date(2020, 1, 1), "end": date(2019, 1, 1)}, "must be after"),
        ({"lookback_years": 0}, "lookback_years must be positive"),
        ({"lookback_years": -1}, "lookback_years must be positive"),
        ({"transaction_cost_bps": -5}, "non-negative"),
        ({"initial_capital": 0}, "initial_capital must be positive"),
        ({"risk_horizon_days": 0}, "risk_horizon_days must be >= 1"),
    ],
)
def test_invalid_settings_are_rejected(kwargs, match):
    with pytest.raises(ValueError, match=match):
        BacktestSettings(**kwargs)


def test_rebalance_frequency_month_steps():
    assert RebalanceFrequency.MONTHLY.months == 1
    assert RebalanceFrequency.QUARTERLY.months == 3
    assert RebalanceFrequency.SEMIANNUAL.months == 6
    assert RebalanceFrequency.ANNUAL.months == 12


def test_risk_horizon_is_configurable_for_later_extension():
    """Daily is the MVP default, but the field must accept a longer horizon."""
    assert BacktestSettings(risk_horizon_days=21).risk_horizon_days == 21


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------


def test_default_universe_has_ten_unique_assets():
    assert len(DEFAULT_UNIVERSE.assets) == 10
    assert len(set(DEFAULT_UNIVERSE.tickers)) == 10


def test_every_asset_predates_the_earliest_estimation_window():
    """A three-year lookback from 2016-01 opens in 2013-01."""
    earliest_window_open = date(2013, 1, 1)
    for asset in DEFAULT_UNIVERSE.assets:
        assert asset.inception < earliest_window_open, (
            f"{asset.ticker} began {asset.inception}, too late for the experiment"
        )


def test_universe_spans_multiple_asset_classes():
    classes = DEFAULT_UNIVERSE.asset_class_map()
    assert set(classes) == {
        AssetClass.EQUITY,
        AssetClass.FIXED_INCOME,
        AssetClass.COMMODITY,
        AssetClass.REAL_ASSETS,
    }
    assert sum(len(v) for v in classes.values()) == len(DEFAULT_UNIVERSE.assets)


def test_asset_class_map_partitions_the_universe():
    classes = DEFAULT_UNIVERSE.asset_class_map()
    flattened = [t for tickers in classes.values() for t in tickers]
    assert sorted(flattened) == sorted(DEFAULT_UNIVERSE.tickers)


def test_lookup_by_ticker():
    assert DEFAULT_UNIVERSE.by_ticker("SPY").display_name == "S&P 500"
    with pytest.raises(KeyError, match="not in universe"):
        DEFAULT_UNIVERSE.by_ticker("NOPE")


def test_universes_registry_contains_the_default():
    assert DEFAULT_UNIVERSE.name in UNIVERSES
    assert UNIVERSES[DEFAULT_UNIVERSE.name] is DEFAULT_UNIVERSE


def test_a_custom_universe_needs_no_code_change():
    """The application must be usable with another universe by configuration alone."""
    custom = Universe(
        name="Two Asset",
        description="test",
        assets=(
            AssetSpec("XXX", "X", AssetClass.EQUITY, "Test", date(2000, 1, 1)),
            AssetSpec("YYY", "Y", AssetClass.FIXED_INCOME, "Test", date(2001, 1, 1)),
        ),
    )
    assert custom.tickers == ["XXX", "YYY"]
    assert custom.earliest_common_inception() == date(2001, 1, 1)
    assert set(custom.asset_class_map()) == {AssetClass.EQUITY, AssetClass.FIXED_INCOME}


def test_asset_specs_are_immutable():
    asset = DEFAULT_UNIVERSE.assets[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        asset.ticker = "OTHER"  # type: ignore[misc]
