"""Global settings, paths, and the numerical conventions used throughout the project.

Every convention that could plausibly be defined more than one way is defined
exactly once, here, and documented.  Downstream code imports these constants
rather than re-deriving them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
SNAPSHOT_DIR = DATA_DIR / "snapshots"

DEFAULT_SNAPSHOT = SNAPSHOT_DIR / "prices_diversified_etf_10.csv"


# ---------------------------------------------------------------------------
# Numerical conventions  (decisions D3, D4, D10)
# ---------------------------------------------------------------------------

TRADING_DAYS_PER_YEAR = 252
"""Annualisation factor for daily data.

Convention: annualised mean  = daily mean * 252
            annualised var   = daily var  * 252
            annualised vol   = daily vol  * sqrt(252)
"""

TRADING_DAYS_PER_MONTH = 21

RETURN_CONVENTION: Literal["simple"] = "simple"
"""Simple (arithmetic) returns from adjusted close: r_t = P_t / P_{t-1} - 1.

Simple returns are used everywhere -- estimation, optimization and compounding.
Log returns aggregate more conveniently across *time* but not across *assets*:
the log return of a portfolio is not the weighted sum of asset log returns, so a
portfolio built on log-return inputs would be internally inconsistent.

Adjusted close incorporates reinvested dividends and split adjustments.  Taxes
are not modelled.
"""


class DataCutoff(StrEnum):
    """How the estimation window relates to the decision date `t`.  (Decision D3)"""

    INCLUSIVE = "inclusive"
    """Estimation uses observations with date <= t. The portfolio formed at t
    earns returns from the next trading day onward. This is the project default:
    the decision maker is assumed to observe the close on t and transact at it."""

    EXCLUSIVE = "exclusive"
    """Estimation uses observations with date < t strictly. Marginally more
    conservative; provided so the sensitivity of results to this convention can
    be examined without editing code."""


DEFAULT_CUTOFF = DataCutoff.INCLUSIVE


class LookbackPolicy(StrEnum):
    """What to do when a decision date lacks the full configured lookback.

    A shorter-than-configured estimation window changes what the experiment
    measures, so it is never entered silently.
    """

    REQUIRE = "require"
    """Refuse to run. The offending dates are named and the experiment aborts.
    This is the default: for a formal backtest, an unmet lookback is a
    configuration error, not a condition to work around."""

    EXCLUDE = "exclude"
    """Drop the offending decision dates before the experiment starts and record
    which were dropped in the results. The remaining dates all have the full
    configured history."""


class ExperimentMode(StrEnum):
    """Whether the experiment window is frozen or tracks the latest data."""

    RESEARCH = "research"
    """Fixed start and end dates. Results do not change as new market data
    arrives, so a re-run reproduces earlier numbers exactly. All reported
    findings must come from this mode."""

    DEMO = "demo"
    """The window extends to the most recent data available. Convenient for a
    live presentation; **not** reproducible, because the evaluation period grows
    over time. Never use for reported results."""


# ---------------------------------------------------------------------------
# The frozen research window
#
# These dates define the formal experiment and must not be edited to chase newer
# data. The window spans ten complete calendar years, and ends well before the
# snapshot does so that refreshing the snapshot cannot alter published results.
# ---------------------------------------------------------------------------

RESEARCH_START = date(2016, 1, 1)
RESEARCH_END = date(2025, 12, 31)


class RebalanceFrequency(StrEnum):
    """Supported rebalancing cadences.  (Decision D12)"""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"

    @property
    def months(self) -> int:
        return {"monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12}[self.value]


# ---------------------------------------------------------------------------
# Experiment configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BacktestSettings:
    """Everything needed to define a reproducible historical experiment.

    Parameters
    ----------
    start
        First scheduled rebalance date. The engine snaps this forward to the
        first available trading day.
    end
        Last date on which realised performance is recorded. Defaults to the
        frozen ``RESEARCH_END``; it is a fixed date rather than "the latest
        data" so that a re-run reproduces earlier results exactly.
    mode
        ``RESEARCH`` (frozen window, reproducible) or ``DEMO`` (window extends
        to the latest available data, not reproducible). Construct demo settings
        with :meth:`BacktestSettings.for_demo`.
    lookback_policy
        What to do when a decision date lacks the full configured lookback:
        refuse to run, or exclude those dates before the experiment starts.
    lookback_years
        Length of the estimation window preceding each decision date.
    rebalance_frequency
        Cadence of re-optimization.
    cutoff
        Estimation-window convention relative to the decision date (see DataCutoff).
    transaction_cost_bps
        One-way transaction cost in basis points applied to turnover.  Held at
        zero for the first validated baseline; the mechanism exists so cost
        sensitivity can be examined without re-engineering the backtest.
    initial_capital
        Starting portfolio value in currency units.
    risk_horizon_days
        Horizon over which downside-risk scenarios are measured.  1 = daily.
        The MVP measures and reports *daily* 95% CVaR; this field exists so the
        risk horizon can be lengthened in a later extension without changing
        call sites.
    """

    start: date = RESEARCH_START
    end: date = RESEARCH_END
    lookback_years: float = 3.0
    rebalance_frequency: RebalanceFrequency = RebalanceFrequency.QUARTERLY
    cutoff: DataCutoff = DEFAULT_CUTOFF
    transaction_cost_bps: float = 0.0
    initial_capital: float = 100_000.0
    risk_horizon_days: int = 1
    mode: ExperimentMode = ExperimentMode.RESEARCH
    lookback_policy: LookbackPolicy = LookbackPolicy.REQUIRE

    @property
    def lookback_days(self) -> int:
        """Estimation window length in trading days (counted as returns)."""
        return int(round(self.lookback_years * TRADING_DAYS_PER_YEAR))

    @property
    def required_observations(self) -> int:
        """Price observations a decision date needs for a full estimation window.

        One more than ``lookback_days``, because a return consumes two prices.
        """
        return self.lookback_days + 1

    @property
    def is_reproducible(self) -> bool:
        """True when the window is frozen and results cannot drift over time."""
        return self.mode is ExperimentMode.RESEARCH

    @classmethod
    def for_demo(cls, latest_available: date, **overrides: object) -> BacktestSettings:
        """Settings whose window runs to the most recent data available.

        Intended for a live presentation, where showing history up to the present
        is worth more than reproducibility. Results from demo mode are not
        reproducible -- the evaluation period grows as data arrives -- and must
        not be reported as research findings.
        """
        params: dict[str, object] = {
            "start": RESEARCH_START,
            "end": latest_available,
            "mode": ExperimentMode.DEMO,
        }
        params.update(overrides)
        return cls(**params)  # type: ignore[arg-type]

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"end ({self.end}) must be after start ({self.start})")
        if self.lookback_years <= 0:
            raise ValueError("lookback_years must be positive")
        if self.transaction_cost_bps < 0:
            raise ValueError("transaction_cost_bps must be non-negative")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if self.risk_horizon_days < 1:
            raise ValueError("risk_horizon_days must be >= 1")


# ---------------------------------------------------------------------------
# Risk reporting conventions  (decision D7)
# ---------------------------------------------------------------------------

DEFAULT_CVAR_CONFIDENCE = 0.95
"""Confidence level alpha for VaR / CVaR.

Reported CVaR is the mean loss in the worst (1 - alpha) tail of the scenario
set.  With risk_horizon_days = 1 this is a **daily** figure and must be labelled
as such wherever it is displayed; a daily 95% CVaR is not comparable to a
monthly or annual one.
"""

MIN_OBSERVATIONS_FOR_ESTIMATION = 60
"""Refuse to estimate parameters from fewer observations than this."""
