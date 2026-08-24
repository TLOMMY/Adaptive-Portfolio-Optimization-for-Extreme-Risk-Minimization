"""Containers for backtest output.

These hold *raw realised series only*. Performance metrics are computed from
them by ``src.risk.metrics`` rather than being stored here, so that a metric
definition can be revised without re-running the experiment, and so that no
number in the UI can be a value that was written down rather than computed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class RebalanceRecord:
    """Audit record for a single strategy at a single decision date."""

    as_of: pd.Timestamp
    period_index: int
    weights_before: pd.Series
    """Drifted weights immediately before rebalancing."""
    weights_after: pd.Series
    """Target weights chosen by the strategy."""
    turnover: float
    """One-way turnover: 0.5 * sum |w_after - w_before|. The reported metric."""
    traded_fraction: float
    """Total notional traded as a fraction of portfolio value: sum |w_after - w_before|.
    This -- not one-way turnover -- is the base transaction costs are charged on,
    because a sale and the purchase it funds each incur a charge."""
    cost: float
    """Currency cost charged for this rebalance."""
    portfolio_value: float
    """Portfolio value at the decision date, after cost."""
    status: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    n_observations_used: int = 0
    """Size of the visible history the decision was made from."""
    data_last_date: pd.Timestamp | None = None
    """Latest observation the strategy could see. Recorded so the no-look-ahead
    property is auditable directly from the results, not only from tests."""


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Realised history of one strategy over the experiment window."""

    strategy_name: str
    portfolio_values: pd.Series
    """Daily portfolio value, indexed by trading date, starting at the first
    decision date with the initial capital."""
    daily_returns: pd.Series
    """Daily simple portfolio returns, net of any transaction costs charged."""
    weights_history: pd.DataFrame
    """Target weights by rebalance date (rows) and ticker (columns)."""
    rebalances: list[RebalanceRecord]
    settings_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def start_date(self) -> pd.Timestamp:
        return self.portfolio_values.index[0]

    @property
    def end_date(self) -> pd.Timestamp:
        return self.portfolio_values.index[-1]

    @property
    def turnover_series(self) -> pd.Series:
        return pd.Series(
            [r.turnover for r in self.rebalances],
            index=pd.DatetimeIndex([r.as_of for r in self.rebalances], name="date"),
            name="turnover",
        )

    @property
    def total_cost(self) -> float:
        return float(sum(r.cost for r in self.rebalances))

    def average_turnover(self, exclude_initial: bool = True) -> float:
        """Mean one-way turnover per rebalance.

        The first rebalance establishes the position from cash and is not a
        rebalance in the usual sense, so it is excluded by default; including it
        would bias the average upward by an amount that depends only on how many
        rebalances happen to follow it.
        """
        records = self.rebalances[1:] if exclude_initial else self.rebalances
        if not records:
            return 0.0
        return float(sum(r.turnover for r in records) / len(records))

    def diagnostics_frame(self) -> pd.DataFrame:
        """Flatten per-rebalance diagnostics into a table for inspection."""
        rows = []
        for record in self.rebalances:
            row: dict[str, Any] = {
                "as_of": record.as_of,
                "status": record.status,
                "turnover": record.turnover,
                "traded_fraction": record.traded_fraction,
                "cost": record.cost,
                "portfolio_value": record.portfolio_value,
                "n_observations_used": record.n_observations_used,
                "data_last_date": record.data_last_date,
            }
            row.update(record.diagnostics)
            rows.append(row)
        return pd.DataFrame(rows)


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    """Results for every strategy run over one identical experiment.

    All strategies in an ``ExperimentResult`` were evaluated against the same
    decision dates and the same market views, which is what makes cross-strategy
    comparison meaningful.
    """

    results: dict[str, BacktestResult]
    rebalance_dates: list[pd.Timestamp]
    settings_summary: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, name: str) -> BacktestResult:
        return self.results[name]

    def __iter__(self):
        return iter(self.results.values())

    @property
    def strategy_names(self) -> list[str]:
        return list(self.results)

    def value_frame(self) -> pd.DataFrame:
        """Portfolio value per strategy, aligned on a common date index."""
        return pd.DataFrame({name: r.portfolio_values for name, r in self.results.items()})

    def return_frame(self) -> pd.DataFrame:
        return pd.DataFrame({name: r.daily_returns for name, r in self.results.items()})
