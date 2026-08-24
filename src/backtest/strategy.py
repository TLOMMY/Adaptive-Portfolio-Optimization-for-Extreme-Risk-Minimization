"""The contract the backtest engine requires of an allocation strategy.

The engine defines this interface rather than importing one from the optimization
package, which keeps the dependency pointing the right way: optimizers conform to
what the backtest needs, and the backtest knows nothing about how any particular
portfolio is computed.

The critical clause is the signature of :meth:`Strategy.allocate`: a strategy is
handed a :class:`~src.data.window.MarketDataView`, never a price panel.  A strategy
therefore *cannot* observe data after the decision date, because the object it is
given does not contain any.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from src.data.window import MarketDataView


@dataclass(frozen=True, slots=True)
class RebalanceContext:
    """Non-market information available at a decision date.

    Attributes
    ----------
    as_of
        The decision date.
    current_weights
        Portfolio weights immediately *before* rebalancing, after market drift
        since the previous rebalance. Zero vector at the first decision date.
        Strategies need this to evaluate turnover constraints.
    portfolio_value
        Portfolio value at the decision date, before any rebalancing cost.
    period_index
        Zero-based index of this rebalance within the backtest.
    """

    as_of: pd.Timestamp
    current_weights: pd.Series
    portfolio_value: float
    period_index: int


@dataclass(slots=True)
class AllocationDecision:
    """A strategy's output at one decision date.

    Attributes
    ----------
    weights
        Target portfolio weights, indexed by ticker.
    status
        Solver or strategy status string (e.g. ``"optimal"``, ``"analytic"``).
    diagnostics
        Free-form record of anything worth auditing later: solve time, whether a
        return target was attainable, the shortfall from feasibility, the
        estimator settings used. Surfaced in the backtest output; never used to
        alter the decision after the fact.
    """

    weights: pd.Series
    status: str = "ok"
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def validate(self, tickers: list[str], tolerance: float = 1e-6) -> None:
        """Check the decision is a well-formed portfolio over ``tickers``."""
        if list(self.weights.index) != list(tickers):
            raise ValueError(
                f"weights index {list(self.weights.index)} does not match universe {tickers}"
            )
        if self.weights.isna().any():
            raise ValueError(f"weights contain NaN: {self.weights.to_dict()}")
        total = float(self.weights.sum())
        if abs(total - 1.0) > tolerance:
            raise ValueError(f"weights sum to {total!r}, expected 1.0 (tol={tolerance})")


@runtime_checkable
class Strategy(Protocol):
    """Anything that can turn a truncated market view into portfolio weights."""

    name: str

    def allocate(self, view: MarketDataView, context: RebalanceContext) -> AllocationDecision:
        """Choose target weights using only information visible in ``view``."""
        ...
