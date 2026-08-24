"""Shared deterministic fixtures and strategy test doubles.

Every fixture here is seeded or analytically constructed. No test depends on
network access or on the committed snapshot unless it is explicitly marked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.backtest.strategy import AllocationDecision, RebalanceContext  # noqa: E402
from src.config.settings import BacktestSettings, RebalanceFrequency  # noqa: E402
from src.data.window import MarketDataView  # noqa: E402

SEED = 20160104
TICKERS = ["AAA", "BBB", "CCC", "DDD"]


# ---------------------------------------------------------------------------
# Price fixtures
# ---------------------------------------------------------------------------


def make_prices(
    n_days: int = 2000,
    tickers: list[str] | None = None,
    start: str = "2012-01-02",
    seed: int = SEED,
    drift: float = 0.0003,
    vol: float = 0.01,
) -> pd.DataFrame:
    """Deterministic geometric-random-walk price panel on a business-day index."""
    tickers = tickers or TICKERS
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start=start, periods=n_days, name="date")
    shocks = rng.normal(loc=drift, scale=vol, size=(n_days, len(tickers)))
    prices = 100.0 * np.exp(np.cumsum(shocks, axis=0))
    return pd.DataFrame(prices, index=index, columns=tickers).astype("float64")


def make_distinct_risk_prices(
    n_days: int = 2000,
    start: str = "2012-01-02",
    seed: int = SEED,
) -> pd.DataFrame:
    """Prices for four assets with deliberately separated risk/return profiles.

    Used where a test needs the risk-return trade-off to be visible: a fixture in
    which every asset looks alike cannot demonstrate that an optimizer responds
    to risk aversion at all.

        SAFE  : very low drift, very low volatility   (cash-like)
        BOND  : low drift,      low volatility
        STOCK : high drift,     high volatility
        WILD  : high drift,     very high volatility
    """
    profiles = {
        "SAFE": (0.00005, 0.0010),
        "BOND": (0.00015, 0.0035),
        "STOCK": (0.00045, 0.0110),
        "WILD": (0.00055, 0.0200),
    }
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start=start, periods=n_days, name="date")
    columns = {}
    for ticker, (drift, vol) in profiles.items():
        shocks = rng.normal(loc=drift, scale=vol, size=n_days)
        columns[ticker] = 100.0 * np.exp(np.cumsum(shocks))
    return pd.DataFrame(columns, index=index).astype("float64")


DISTINCT_ASSET_CLASSES = {
    "Equity": ["STOCK", "WILD"],
    "Fixed Income": ["SAFE", "BOND"],
}


@pytest.fixture
def prices() -> pd.DataFrame:
    return make_prices()


@pytest.fixture
def risk_prices() -> pd.DataFrame:
    return make_distinct_risk_prices()


@pytest.fixture
def risk_view(risk_prices) -> MarketDataView:
    """A view late enough in `risk_prices` to support a 500-day lookback."""
    return MarketDataView(risk_prices, risk_prices.index[1500])


@pytest.fixture
def rebalance_context(risk_prices) -> RebalanceContext:
    tickers = list(risk_prices.columns)
    return RebalanceContext(
        as_of=risk_prices.index[1500],
        current_weights=pd.Series(0.0, index=tickers),
        portfolio_value=100_000.0,
        period_index=0,
    )


@pytest.fixture
def short_prices() -> pd.DataFrame:
    return make_prices(n_days=400, start="2014-01-01")


@pytest.fixture
def phase2_settings() -> BacktestSettings:
    """A short experiment with a lookback the `prices` fixture can support."""
    return BacktestSettings(
        start=pd.Timestamp("2016-01-01").date(),
        end=pd.Timestamp("2018-12-31").date(),
        lookback_years=1.0,
        rebalance_frequency=RebalanceFrequency.QUARTERLY,
        initial_capital=100_000.0,
        transaction_cost_bps=0.0,
    )


@pytest.fixture
def settings() -> BacktestSettings:
    """A small, fast experiment sitting entirely inside the `prices` fixture."""
    return BacktestSettings(
        start=pd.Timestamp("2016-01-01").date(),
        end=pd.Timestamp("2018-12-31").date(),
        lookback_years=1.0,
        rebalance_frequency=RebalanceFrequency.QUARTERLY,
        initial_capital=100_000.0,
        transaction_cost_bps=0.0,
    )


# ---------------------------------------------------------------------------
# Strategy test doubles
#
# Phase 1 has no optimizers by design. These stand in for them so the engine,
# the rebalance calendar and the look-ahead firewall can be validated on their
# own, before any optimization logic exists to confound a failure.
# ---------------------------------------------------------------------------


class FixedWeightStrategy:
    """Allocates the same weights at every decision date."""

    def __init__(self, weights: pd.Series, name: str = "fixed") -> None:
        self.weights = weights.astype(float)
        self.name = name

    def allocate(self, view: MarketDataView, context: RebalanceContext) -> AllocationDecision:
        return AllocationDecision(
            weights=self.weights.reindex(view.tickers).fillna(0.0),
            status="analytic",
        )


class UniformStrategy:
    """Equal weight across whatever universe the view exposes."""

    name = "uniform"

    def allocate(self, view: MarketDataView, context: RebalanceContext) -> AllocationDecision:
        tickers = view.tickers
        w = pd.Series(1.0 / len(tickers), index=tickers)
        return AllocationDecision(weights=w, status="analytic")


class RecordingStrategy:
    """Uniform allocation that records exactly what each view exposed.

    Used to assert, from the outside, that no decision ever saw data beyond its
    decision date.
    """

    name = "recording"

    def __init__(self) -> None:
        self.seen: list[dict] = []

    def allocate(self, view: MarketDataView, context: RebalanceContext) -> AllocationDecision:
        visible = view.prices()
        self.seen.append(
            {
                "as_of": view.as_of,
                "max_visible_date": visible.index.max(),
                "min_visible_date": visible.index.min(),
                "n_obs": len(visible),
                "checksum": float(np.nansum(visible.to_numpy())),
            }
        )
        w = pd.Series(1.0 / len(view.tickers), index=view.tickers)
        return AllocationDecision(weights=w, status="analytic")


class TrailingMomentumStrategy:
    """A data-dependent strategy, used to make leakage detectable.

    Its weights depend on the *content* of the estimation window, so if any
    future data reached the view the resulting allocations would change. A
    strategy that ignores its inputs could not detect leakage at all.
    """

    name = "momentum"

    def __init__(self, lookback: int = 60) -> None:
        self.lookback = lookback

    def allocate(self, view: MarketDataView, context: RebalanceContext) -> AllocationDecision:
        returns = view.returns(self.lookback)
        score = returns.mean()
        positive = score.clip(lower=0.0)
        weights = (
            positive / positive.sum()
            if positive.sum() > 0
            else pd.Series(1.0 / len(view.tickers), index=view.tickers)
        )
        return AllocationDecision(
            weights=weights.reindex(view.tickers).fillna(0.0),
            status="analytic",
            diagnostics={"mean_score": float(score.mean())},
        )


@pytest.fixture
def uniform_strategy() -> UniformStrategy:
    return UniformStrategy()


@pytest.fixture
def recording_strategy() -> RecordingStrategy:
    return RecordingStrategy()


@pytest.fixture
def momentum_strategy() -> TrailingMomentumStrategy:
    return TrailingMomentumStrategy()
