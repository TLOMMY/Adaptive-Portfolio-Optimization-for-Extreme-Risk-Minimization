"""Return-scenario construction for scenario-based risk optimization.

A *scenario* is one realisation of the joint asset-return vector.  The CVaR model
treats each historical observation in the estimation window as an equiprobable
scenario, which makes the resulting risk measure a purely empirical one: it makes
no distributional assumption, and in particular does not assume normality.

Like every other estimator in this project, builders take a
:class:`~src.data.window.MarketDataView` and never a price panel, so a scenario
set cannot contain an observation from after the decision date.

The builder is an interface rather than a function so that later extensions --
block bootstrap, filtered historical simulation, alternative windows -- can be
added without touching the optimizers that consume scenarios.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.data.window import MarketDataView

MIN_SCENARIOS = 100
"""Fewest scenarios an empirical tail measure may be estimated from.

A 95% CVaR averages the worst 5% of scenarios. With 100 scenarios that tail
holds 5 observations, which is already thin; below that the estimate is driven
by a handful of points and is not meaningfully an expectation. The guard is a
hard error rather than a warning because a silently under-powered tail estimate
looks exactly like a well-estimated one in the output.
"""


class InsufficientScenariosError(RuntimeError):
    """Raised when a scenario set is too small to estimate a tail measure from."""


@dataclass(frozen=True, slots=True)
class ReturnScenarios:
    """An equiprobable set of historical return scenarios.

    Attributes
    ----------
    returns
        ``(S, N)`` array of simple **returns** (not losses) over ``horizon_days``,
        one row per scenario, columns in ``tickers`` order.
    tickers
        Asset order.
    horizon_days
        Length of the period each scenario spans. ``1`` means one trading day.
    as_of
        The decision date the scenarios were built for.
    window_start, window_end
        First and last observation date contributing to the set. ``window_end``
        never exceeds ``as_of``.
    method
        Identifier for how the set was constructed, recorded in diagnostics.

    Notes
    -----
    Scenarios store returns, and losses are derived as :math:`L_s = -r_s^\\top x`
    where they are needed. Keeping the stored sign the same as everywhere else in
    the project avoids a class of sign errors that are invisible until they
    invert a risk number.
    """

    returns: np.ndarray
    tickers: list[str]
    horizon_days: int
    as_of: pd.Timestamp
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    method: str

    @property
    def n_scenarios(self) -> int:
        return int(self.returns.shape[0])

    @property
    def n_assets(self) -> int:
        return int(self.returns.shape[1])

    @property
    def probabilities(self) -> np.ndarray:
        """Equiprobable weights, one per scenario.

        Held explicitly so that a later non-uniform scheme (exponential decay,
        importance weighting) has an obvious place to attach.
        """
        return np.full(self.n_scenarios, 1.0 / self.n_scenarios)

    def portfolio_returns(self, weights: pd.Series | np.ndarray) -> np.ndarray:
        """Portfolio return in each scenario: :math:`r_s^\\top x`."""
        return self.returns @ self._as_array(weights)

    def portfolio_losses(self, weights: pd.Series | np.ndarray) -> np.ndarray:
        """Portfolio loss in each scenario: :math:`L_s = -r_s^\\top x`.

        Positive values are losses, negative values are gains.
        """
        return -self.portfolio_returns(weights)

    def _as_array(self, weights: pd.Series | np.ndarray) -> np.ndarray:
        if isinstance(weights, pd.Series):
            return weights.reindex(self.tickers).to_numpy(dtype="float64")
        array = np.asarray(weights, dtype="float64")
        if array.shape != (self.n_assets,):
            raise ValueError(
                f"expected {self.n_assets} weights, got shape {array.shape}"
            )
        return array

    def summary(self) -> dict[str, Any]:
        """Compact record for the diagnostics audit trail."""
        return {
            "n_scenarios": self.n_scenarios,
            "scenario_method": self.method,
            "scenario_horizon_days": self.horizon_days,
            "scenario_window_start": str(self.window_start.date()),
            "scenario_window_end": str(self.window_end.date()),
        }


class ScenarioBuilder(ABC):
    """Turns a truncated market view into a set of return scenarios."""

    method: str = "abstract"

    def __init__(self, min_scenarios: int = MIN_SCENARIOS) -> None:
        self.min_scenarios = min_scenarios

    @abstractmethod
    def build(self, view: MarketDataView, lookback_days: int) -> ReturnScenarios:
        """Construct scenarios from the view's estimation window."""

    def _check_size(self, n_scenarios: int, view: MarketDataView, detail: str) -> None:
        if n_scenarios < self.min_scenarios:
            raise InsufficientScenariosError(
                f"{self.method} produced {n_scenarios} scenarios at "
                f"{view.as_of.date()}, below the minimum of {self.min_scenarios}. "
                f"{detail}"
            )


class DailyHistoricalScenarios(ScenarioBuilder):
    """Each daily return in the lookback window is one equiprobable scenario.

    This is the MVP construction: ``horizon_days = 1``, no resampling, no
    synthetic data. With a three-year lookback it yields ~756 scenarios, whose
    worst 5% tail holds ~38 observations.
    """

    method = "historical_daily"
    horizon_days = 1

    def build(self, view: MarketDataView, lookback_days: int) -> ReturnScenarios:
        returns = view.returns(lookback_days)
        self._check_size(
            len(returns), view, "Lengthen the lookback window."
        )
        return ReturnScenarios(
            returns=returns.to_numpy(dtype="float64"),
            tickers=list(returns.columns),
            horizon_days=1,
            as_of=view.as_of,
            window_start=returns.index[0],
            window_end=returns.index[-1],
            method=self.method,
        )


class NonOverlappingHorizonScenarios(ScenarioBuilder):
    """Compounded multi-day returns over non-overlapping blocks.

    The window is divided into consecutive blocks of ``horizon_days`` sessions
    and each block is compounded, :math:`\\prod_t (1 + r_t) - 1`. Blocks do not
    overlap, so the scenarios are (approximately) independent draws -- which
    overlapping windows are emphatically not, and which matters because a tail
    measure estimated from serially dependent samples understates its own
    sampling error.

    The cost is severe: a three-year window yields only ``756 / h`` scenarios,
    so a 21-day horizon leaves 36 of them. That is far too few for a 95% tail,
    and :attr:`min_scenarios` will reject it. This class exists so multi-day
    horizons are *possible* and correctly implemented, not because the default
    lookback can support them -- see the Phase 3 notes on ``risk_horizon_days``.
    """

    method = "historical_non_overlapping"

    def __init__(self, horizon_days: int, min_scenarios: int = MIN_SCENARIOS) -> None:
        super().__init__(min_scenarios=min_scenarios)
        if horizon_days < 1:
            raise ValueError(f"horizon_days must be >= 1, got {horizon_days}")
        self.horizon_days = int(horizon_days)

    def build(self, view: MarketDataView, lookback_days: int) -> ReturnScenarios:
        returns = view.returns(lookback_days)
        h = self.horizon_days
        n_blocks = len(returns) // h

        if n_blocks == 0:
            raise InsufficientScenariosError(
                f"{len(returns)} observations cannot fill a single {h}-day block "
                f"at {view.as_of.date()}"
            )

        # Align blocks to the END of the window so the most recent data is always
        # used; any remainder is dropped from the oldest end.
        used = returns.iloc[len(returns) - n_blocks * h :]
        blocks = used.to_numpy(dtype="float64").reshape(n_blocks, h, used.shape[1])
        compounded = np.prod(1.0 + blocks, axis=1) - 1.0

        self._check_size(
            n_blocks,
            view,
            f"A {h}-day horizon consumes {h} observations per scenario; "
            f"lengthen the lookback or shorten the horizon.",
        )

        return ReturnScenarios(
            returns=compounded,
            tickers=list(used.columns),
            horizon_days=h,
            as_of=view.as_of,
            window_start=used.index[0],
            window_end=used.index[-1],
            method=self.method,
        )


def build_scenario_builder(
    horizon_days: int = 1, min_scenarios: int = MIN_SCENARIOS
) -> ScenarioBuilder:
    """Select the appropriate builder for a risk horizon."""
    if horizon_days == 1:
        return DailyHistoricalScenarios(min_scenarios=min_scenarios)
    return NonOverlappingHorizonScenarios(horizon_days, min_scenarios=min_scenarios)
