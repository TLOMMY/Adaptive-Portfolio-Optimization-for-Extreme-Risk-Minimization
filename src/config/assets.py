"""Asset universe configuration.

The application is universe-agnostic: every downstream component (data provider,
estimation, optimization, backtest) reads the universe from here.  Swapping the
traded universe is a configuration change, never a code change.

Selection policy
----------------
Instruments are selected for *asset-class diversity* and for having price history
that predates the earliest estimation window required by the experiment.  They are
deliberately NOT selected on realised performance over the evaluation period --
doing so would leak future information into the experiment design itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class AssetClass:
    """Coarse asset-class labels used for concentration constraints.

    Constraints are applied at asset-class granularity rather than fine sector
    granularity: a ten-instrument universe has too few members per fine sector for
    a sector cap to bind meaningfully.  Fine-grained sector analysis is a documented
    extension, not part of the MVP.
    """

    EQUITY = "Equity"
    FIXED_INCOME = "Fixed Income"
    COMMODITY = "Commodity"
    REAL_ASSETS = "Real Assets"


@dataclass(frozen=True, slots=True)
class AssetSpec:
    """Static metadata for one tradable instrument."""

    ticker: str
    display_name: str
    asset_class: str
    category: str
    inception: date
    """First trading date known to the data vendor. Used to validate that the
    configured universe can actually support the configured experiment window."""


@dataclass(frozen=True, slots=True)
class Universe:
    """A named collection of assets."""

    name: str
    description: str
    assets: tuple[AssetSpec, ...]

    @property
    def tickers(self) -> list[str]:
        return [a.ticker for a in self.assets]

    def by_ticker(self, ticker: str) -> AssetSpec:
        for a in self.assets:
            if a.ticker == ticker:
                return a
        raise KeyError(f"{ticker!r} is not in universe {self.name!r}")

    def asset_class_map(self) -> dict[str, list[str]]:
        """asset_class -> list of tickers, for building concentration constraints."""
        out: dict[str, list[str]] = {}
        for a in self.assets:
            out.setdefault(a.asset_class, []).append(a.ticker)
        return out

    def earliest_common_inception(self) -> date:
        return max(a.inception for a in self.assets)


# ---------------------------------------------------------------------------
# MVP universe
#
# Inception dates below were verified against the data vendor, not assumed.
# The binding constraint is 2007-07-26 (VEA is *not* included precisely because
# later-inception funds would shorten the usable history); every member of this
# universe has continuous history from 2004-11-18 at the latest, comfortably
# ahead of the 2013-01 start of the earliest three-year estimation window.
# ---------------------------------------------------------------------------

DIVERSIFIED_ETF_10 = Universe(
    name="Diversified ETF (10)",
    description=(
        "Ten liquid, long-lived US-listed ETFs spanning equity, fixed income, "
        "commodities and real assets. Chosen for asset-class breadth and pre-2013 "
        "inception, not for realised performance over the evaluation period."
    ),
    assets=(
        AssetSpec("SPY", "S&P 500", AssetClass.EQUITY, "US Large Cap", date(1993, 1, 29)),
        AssetSpec("IJR", "S&P SmallCap 600", AssetClass.EQUITY, "US Small Cap", date(2000, 5, 26)),
        AssetSpec("EFA", "MSCI EAFE", AssetClass.EQUITY, "Intl Developed", date(2001, 8, 27)),
        AssetSpec("EEM", "MSCI Emerging Markets", AssetClass.EQUITY, "Emerging Markets", date(2003, 4, 14)),
        AssetSpec("AGG", "US Aggregate Bond", AssetClass.FIXED_INCOME, "Broad Bond", date(2003, 9, 29)),
        AssetSpec("TLT", "20+ Year Treasury", AssetClass.FIXED_INCOME, "Long Treasury", date(2002, 7, 30)),
        AssetSpec("SHY", "1-3 Year Treasury", AssetClass.FIXED_INCOME, "Short Treasury", date(2002, 7, 30)),
        AssetSpec("LQD", "Investment Grade Corporate", AssetClass.FIXED_INCOME, "Corporate Credit", date(2002, 7, 30)),
        AssetSpec("GLD", "Gold", AssetClass.COMMODITY, "Precious Metals", date(2004, 11, 18)),
        AssetSpec("VNQ", "US Real Estate", AssetClass.REAL_ASSETS, "REITs", date(2004, 9, 29)),
    ),
)


UNIVERSES: dict[str, Universe] = {
    DIVERSIFIED_ETF_10.name: DIVERSIFIED_ETF_10,
}

DEFAULT_UNIVERSE = DIVERSIFIED_ETF_10
