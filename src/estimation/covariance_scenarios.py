"""Covariance uncertainty sets for robust optimization.

Motivation
----------
A mean-variance or minimum-variance portfolio treats its estimated covariance
matrix as if it were known.  It is not: :math:`\\hat\\Sigma` is a statistic, and a
portfolio optimized against one realisation of it can be badly positioned under
another equally plausible one.  The robust model addresses this directly by
optimizing against the *worst case* over a finite set of covariance matrices,
each estimated from a different slice of the same history.

Construction
------------
The MVP uncertainty set is built from overlapping rolling subwindows of the
lookback period, plus the full-window estimate.  With the default 756-observation
lookback: five 252-observation subwindows at stride 126 (offsets 0, 126, 252,
378, 504 -- the last ending exactly at 756), plus the 756-observation estimate,
giving **six** covariance scenarios.

This is a fixed MVP construction, not a claim of optimality.  Six matrices from
overlapping windows are neither an exhaustive nor an unbiased description of
estimation uncertainty -- the subwindows share observations and are therefore
correlated, and the set says nothing about covariance regimes absent from the
lookback.  The count, length and stride are configuration, and the
:class:`CovarianceUncertaintySet` interface exists so box or ellipsoidal
uncertainty sets can replace scenario enumeration entirely without touching the
optimizer.

Every scenario is estimated with the same Ledoit-Wolf estimator and the same
annualisation convention validated in Phase 2, so differences between scenarios
reflect the data window and nothing else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.data.window import MarketDataView
from src.estimation.covariance import ledoit_wolf_from_returns

DEFAULT_WINDOW_LENGTH = 252
"""Observations in each rolling covariance subwindow (about one trading year)."""

DEFAULT_STRIDE = 126
"""Offset between consecutive subwindow starts (about half a trading year)."""

DEFAULT_N_SUBWINDOWS = 5
"""Rolling subwindows before the full-window estimate is added."""

MIN_OBSERVATIONS_PER_SCENARIO = 120
"""Fewest returns a single covariance scenario may be estimated from.

Deliberately *not* the CVaR ``MIN_SCENARIOS`` rule, which counts scenarios in a
tail average. Here each scenario is an entire covariance matrix, and what must
be adequate is the number of observations behind each one. For an N-asset
universe a sample covariance needs comfortably more than N observations to be
informative; Ledoit-Wolf shrinkage keeps it well conditioned below that, but
shrinkage carrying most of the estimate would make the scenarios nearly
identical and the uncertainty set vacuous.
"""

SYMMETRY_TOLERANCE = 1e-10
PSD_TOLERANCE = -1e-10
"""Most negative eigenvalue tolerated before a matrix is rejected as non-PSD."""


class CovarianceScenarioError(RuntimeError):
    """Raised when an uncertainty set cannot be built as configured."""


class InsufficientCovarianceScenariosError(CovarianceScenarioError):
    """Raised when fewer scenarios can be generated than were required.

    Falling back to a smaller set would silently change the model being solved,
    so this is an error rather than a degradation.
    """


@dataclass(frozen=True, slots=True)
class CovarianceScenario:
    """One annualised covariance matrix and the window it came from."""

    matrix: np.ndarray
    tickers: list[str]
    label: str
    n_observations: int
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    shrinkage: float

    def variance(self, weights: np.ndarray) -> float:
        """Annualised portfolio variance under this scenario."""
        w = np.asarray(weights, dtype="float64")
        return float(w @ self.matrix @ w)

    def summary(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "n_observations": self.n_observations,
            "window_start": str(self.window_start.date()),
            "window_end": str(self.window_end.date()),
            "shrinkage": round(self.shrinkage, 6),
        }


@dataclass(frozen=True, slots=True)
class CovarianceScenarioSet:
    """A finite uncertainty set of annualised covariance matrices."""

    scenarios: tuple[CovarianceScenario, ...]
    tickers: list[str]
    as_of: pd.Timestamp
    method: str
    window_length: int
    stride: int

    @property
    def n_scenarios(self) -> int:
        return len(self.scenarios)

    @property
    def matrices(self) -> list[np.ndarray]:
        return [s.matrix for s in self.scenarios]

    @property
    def labels(self) -> list[str]:
        return [s.label for s in self.scenarios]

    def variances(self, weights: pd.Series | np.ndarray) -> np.ndarray:
        """Annualised portfolio variance under each scenario, in order."""
        w = self._as_array(weights)
        return np.array([s.variance(w) for s in self.scenarios], dtype="float64")

    def worst_case_variance(self, weights: pd.Series | np.ndarray) -> float:
        r"""The robust objective for a weight vector: :math:`\\max_s x^\\top Q_s x`."""
        return float(self.variances(weights).max())

    def worst_case_index(self, weights: pd.Series | np.ndarray) -> int:
        """Index of the scenario attaining the worst case."""
        return int(np.argmax(self.variances(weights)))

    def _as_array(self, weights: pd.Series | np.ndarray) -> np.ndarray:
        if isinstance(weights, pd.Series):
            return weights.reindex(self.tickers).to_numpy(dtype="float64")
        array = np.asarray(weights, dtype="float64")
        if array.shape != (len(self.tickers),):
            raise ValueError(
                f"expected {len(self.tickers)} weights, got shape {array.shape}"
            )
        return array

    def summary(self) -> dict[str, Any]:
        """Compact record for the diagnostics audit trail."""
        return {
            "n_covariance_scenarios": self.n_scenarios,
            "covariance_method": self.method,
            "covariance_window_length": self.window_length,
            "covariance_window_stride": self.stride,
            "covariance_scenario_labels": list(self.labels),
            "covariance_window_end": str(
                max(s.window_end for s in self.scenarios).date()
            ),
        }


# ---------------------------------------------------------------------------
# Validation
#
# Separate from the CVaR scenario guard by design: that one asks whether a tail
# average has enough points, this one asks whether each matrix is a usable
# covariance. A non-PSD or asymmetric matrix does not make the robust program
# inaccurate -- it makes it meaningless, because the quadratic constraint stops
# being convex.
# ---------------------------------------------------------------------------


def validate_covariance_scenario(
    scenario: CovarianceScenario,
    tickers: list[str],
    as_of: pd.Timestamp,
    min_observations: int = MIN_OBSERVATIONS_PER_SCENARIO,
) -> None:
    """Raise ``CovarianceScenarioError`` unless the scenario is usable."""
    label = scenario.label

    if scenario.tickers != tickers:
        raise CovarianceScenarioError(
            f"scenario {label!r} covers {scenario.tickers}, expected {tickers}"
        )

    matrix = scenario.matrix
    n = len(tickers)
    if matrix.shape != (n, n):
        raise CovarianceScenarioError(
            f"scenario {label!r} has shape {matrix.shape}, expected {(n, n)}"
        )
    if not np.all(np.isfinite(matrix)):
        raise CovarianceScenarioError(f"scenario {label!r} contains non-finite values")

    asymmetry = float(np.abs(matrix - matrix.T).max())
    if asymmetry > SYMMETRY_TOLERANCE:
        raise CovarianceScenarioError(
            f"scenario {label!r} is not symmetric (max |Q - Q'| = {asymmetry:.3e})"
        )

    min_eigenvalue = float(np.linalg.eigvalsh(0.5 * (matrix + matrix.T)).min())
    if min_eigenvalue < PSD_TOLERANCE:
        raise CovarianceScenarioError(
            f"scenario {label!r} is not positive semidefinite "
            f"(min eigenvalue {min_eigenvalue:.3e})"
        )

    if scenario.window_end > as_of:
        raise CovarianceScenarioError(
            f"scenario {label!r} ends {scenario.window_end.date()}, "
            f"after the decision date {as_of.date()}"
        )

    if scenario.n_observations < min_observations:
        raise CovarianceScenarioError(
            f"scenario {label!r} uses {scenario.n_observations} observations, "
            f"below the minimum of {min_observations}"
        )


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


class CovarianceUncertaintySet(ABC):
    """Turns a truncated market view into a finite set of covariance scenarios.

    Implementations enumerate scenarios. A future box or ellipsoidal set would
    implement a different interface method on the optimizer side; this one is
    deliberately narrow so that swap remains possible.
    """

    method: str = "abstract"

    @abstractmethod
    def build(self, view: MarketDataView, lookback_days: int) -> CovarianceScenarioSet:
        """Construct the uncertainty set from the view's estimation window."""


class RollingWindowUncertaintySet(CovarianceUncertaintySet):
    """Overlapping rolling subwindows, optionally plus the full-window estimate.

    Parameters
    ----------
    window_length
        Observations per subwindow.
    stride
        Offset between consecutive subwindow starts.
    n_subwindows
        How many rolling subwindows to take. Subwindow ``i`` covers returns
        ``[i*stride, i*stride + window_length)`` of the lookback window.
    include_full_window
        Whether to append the estimate from the entire lookback window.
    required_scenarios
        Exact number of scenarios the set must contain. Defaults to
        ``n_subwindows + (1 if include_full_window else 0)``. Generating fewer
        raises rather than quietly shrinking the uncertainty set.
    """

    method = "rolling_subwindows"

    def __init__(
        self,
        window_length: int = DEFAULT_WINDOW_LENGTH,
        stride: int = DEFAULT_STRIDE,
        n_subwindows: int = DEFAULT_N_SUBWINDOWS,
        include_full_window: bool = True,
        required_scenarios: int | None = None,
        min_observations: int = MIN_OBSERVATIONS_PER_SCENARIO,
    ) -> None:
        if window_length < 2:
            raise ValueError(f"window_length must be >= 2, got {window_length}")
        if stride < 1:
            raise ValueError(f"stride must be >= 1, got {stride}")
        if n_subwindows < 1:
            raise ValueError(f"n_subwindows must be >= 1, got {n_subwindows}")

        self.window_length = int(window_length)
        self.stride = int(stride)
        self.n_subwindows = int(n_subwindows)
        self.include_full_window = bool(include_full_window)
        self.min_observations = int(min_observations)
        self.required_scenarios = (
            int(required_scenarios)
            if required_scenarios is not None
            else self.n_subwindows + (1 if self.include_full_window else 0)
        )

    def build(self, view: MarketDataView, lookback_days: int) -> CovarianceScenarioSet:
        returns = view.returns(lookback_days)
        tickers = list(returns.columns)
        n_obs = len(returns)

        span = (self.n_subwindows - 1) * self.stride + self.window_length
        if span > n_obs:
            raise InsufficientCovarianceScenariosError(
                f"{self.n_subwindows} subwindows of {self.window_length} at stride "
                f"{self.stride} span {span} observations, but only {n_obs} are "
                f"available at {view.as_of.date()}. Lengthen the lookback, or "
                f"reduce the subwindow count, length or stride."
            )

        scenarios: list[CovarianceScenario] = []
        for i in range(self.n_subwindows):
            start = i * self.stride
            block = returns.iloc[start : start + self.window_length]
            scenarios.append(
                self._estimate(block, label=f"sub{i}[{start}:{start + self.window_length}]")
            )

        if self.include_full_window:
            scenarios.append(self._estimate(returns, label=f"full[0:{n_obs}]"))

        if len(scenarios) != self.required_scenarios:
            raise InsufficientCovarianceScenariosError(
                f"built {len(scenarios)} covariance scenarios at "
                f"{view.as_of.date()}, but {self.required_scenarios} are required"
            )

        for scenario in scenarios:
            validate_covariance_scenario(
                scenario, tickers, view.as_of, self.min_observations
            )

        return CovarianceScenarioSet(
            scenarios=tuple(scenarios),
            tickers=tickers,
            as_of=view.as_of,
            method=self.method,
            window_length=self.window_length,
            stride=self.stride,
        )

    def _estimate(self, block: pd.DataFrame, label: str) -> CovarianceScenario:
        matrix, shrinkage = ledoit_wolf_from_returns(
            block, annualize=True, context=label
        )
        return CovarianceScenario(
            matrix=matrix.to_numpy(dtype="float64"),
            tickers=list(block.columns),
            label=label,
            n_observations=len(block),
            window_start=block.index[0],
            window_end=block.index[-1],
            shrinkage=shrinkage,
        )
