"""The historical replay engine -- the "time machine".

At each decision date ``t`` the engine:

1. constructs a :class:`~src.data.window.MarketDataView` truncated at ``t``;
2. hands that view -- and nothing else -- to every strategy;
3. locks each strategy's chosen weights;
4. *then* reads realised returns over ``(t, t_next]`` from the full price panel
   to mark the portfolios to market;
5. advances to ``t_next`` and repeats.

Steps 1-3 and step 4 are separated by design, and the engine is the only object
that holds both the truncated view and the full panel.  Strategies never see the
panel, so the ordering above is enforced by structure rather than by discipline.

All strategies in a run share the *same* ``MarketDataView`` instance at each
decision date. This is what makes cross-strategy comparison a controlled
experiment: differences in outcome cannot be attributed to differences in the
information supplied.

Conventions
-----------
Holding period
    Weights chosen at ``t`` earn returns from the next trading day through
    ``t_next`` inclusive. A portfolio is never credited with the return of the
    day it was formed on.

Drift
    Weights are *not* held constant between rebalances. Positions drift with
    realised prices, exactly as an unmanaged portfolio would, and the drifted
    weights are what the next rebalance trades away from.

Transaction cost
    Charged on one-way turnover at ``transaction_cost_bps`` and realised in the
    following day's return, so the recorded value at a decision date is the
    pre-trade mark. Zero in the validated baseline.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from src.backtest.rebalance import generate_rebalance_dates
from src.backtest.results import BacktestResult, ExperimentResult, RebalanceRecord
from src.backtest.strategy import AllocationDecision, RebalanceContext, Strategy
from src.config.settings import (
    MIN_OBSERVATIONS_FOR_ESTIMATION,
    BacktestSettings,
)
from src.data.window import InsufficientHistoryError, MarketDataView

logger = logging.getLogger(__name__)


class BacktestConfigurationError(RuntimeError):
    """Raised when the experiment cannot be run as configured."""


class BacktestEngine:
    """Runs one or more strategies over a shared historical experiment."""

    def __init__(
        self,
        prices: pd.DataFrame,
        settings: BacktestSettings | None = None,
    ) -> None:
        if not isinstance(prices, pd.DataFrame):
            raise TypeError("prices must be a DataFrame")
        if not isinstance(prices.index, pd.DatetimeIndex):
            raise TypeError("prices must be indexed by a DatetimeIndex")
        if prices.empty:
            raise BacktestConfigurationError("price panel is empty")

        self.settings = settings if settings is not None else BacktestSettings()
        self._prices = prices.sort_index().copy()
        self._prices.index = self._prices.index.normalize()
        self.tickers = list(self._prices.columns)

        # Realised marks: forward-filled so a missing quote implies a zero return
        # rather than a spurious jump. This panel is used only *after* decisions
        # are locked; it is never exposed to a strategy.
        self._marks = self._prices.ffill()
        self._realised_returns = self._marks.pct_change()

        self.rebalance_dates = self._resolve_rebalance_dates()

    # -- setup ---------------------------------------------------------------

    def _resolve_rebalance_dates(self) -> list[pd.Timestamp]:
        dates = generate_rebalance_dates(
            trading_days=self._prices.index,
            start=self.settings.start,
            end=self.settings.end,
            frequency=self.settings.rebalance_frequency,
        )
        if not dates:
            raise BacktestConfigurationError(
                f"no trading days available for rebalancing between "
                f"{self.settings.start} and {self.settings.end}"
            )

        first = dates[0]
        available = int((self._prices.index <= first).sum())
        required = max(MIN_OBSERVATIONS_FOR_ESTIMATION, 2)
        if available < required:
            raise BacktestConfigurationError(
                f"only {available} observations exist on or before the first decision "
                f"date {first.date()}; at least {required} are required. Extend the "
                f"price history or move the start date later."
            )

        window_start = self._prices.index[max(0, available - self.settings.lookback_days - 1)]
        if available < self.settings.lookback_days + 1:
            logger.warning(
                "First decision date %s has %d observations but the configured lookback "
                "requests %d; the first estimation window will be shorter than configured.",
                first.date(),
                available,
                self.settings.lookback_days + 1,
            )

        unusable = [
            t for t in self.tickers if self._marks.loc[:first, t].isna().all()
        ]
        if unusable:
            raise BacktestConfigurationError(
                f"no price history on or before the first decision date {first.date()} "
                f"for: {unusable}. Adjust the universe or the start date."
            )

        logger.info(
            "Backtest: %d decision dates from %s to %s; first estimation window opens %s",
            len(dates),
            dates[0].date(),
            dates[-1].date(),
            window_start.date(),
        )
        return dates

    # -- execution -----------------------------------------------------------

    def run(self, strategies: dict[str, Strategy]) -> ExperimentResult:
        """Run every strategy over the experiment and return their realised paths."""
        if not strategies:
            raise ValueError("at least one strategy is required")

        state = {
            name: _StrategyState(name=name, tickers=self.tickers,
                                 capital=self.settings.initial_capital)
            for name in strategies
        }

        calendar = self._prices.index
        final_day = calendar[calendar <= pd.Timestamp(self.settings.end)][-1]

        for period_index, decision_date in enumerate(self.rebalance_dates):
            # --- Step 1: one truncated view, shared by every strategy ---------
            view = MarketDataView(
                prices=self._prices,
                as_of=decision_date,
                cutoff=self.settings.cutoff,
            )
            view.assert_within_boundary()

            # --- Step 2/3: decisions are made and locked before any lookahead --
            for name, strategy in strategies.items():
                self._rebalance_one(
                    strategy=strategy,
                    st=state[name],
                    view=view,
                    decision_date=decision_date,
                    period_index=period_index,
                )

            # --- Step 4: only now may realised returns be consulted -----------
            period_returns = self._period_returns(decision_date, period_index, final_day)
            if period_returns is None:
                continue
            for st in state.values():
                st.advance(period_returns)

        return ExperimentResult(
            results={name: st.finalise(self._settings_summary()) for name, st in state.items()},
            rebalance_dates=list(self.rebalance_dates),
            settings_summary=self._settings_summary(),
        )

    def _rebalance_one(
        self,
        strategy: Strategy,
        st: _StrategyState,
        view: MarketDataView,
        decision_date: pd.Timestamp,
        period_index: int,
    ) -> None:
        context = RebalanceContext(
            as_of=decision_date,
            current_weights=st.current_weights(),
            portfolio_value=st.value,
            period_index=period_index,
        )

        weights_before = st.current_weights()
        try:
            decision = strategy.allocate(view, context)
            decision.validate(self.tickers)
        except InsufficientHistoryError:
            raise
        except Exception as exc:
            # A strategy failure is recorded and the previous allocation is held,
            # rather than being silently replaced by some default portfolio.
            logger.error(
                "%s failed at %s: %s -- holding previous weights",
                st.name, decision_date.date(), exc,
            )
            decision = AllocationDecision(
                weights=weights_before if period_index else self._uniform(),
                status=f"error: {type(exc).__name__}",
                diagnostics={"error": str(exc)},
            )

        st.rebalance(
            decision=decision,
            decision_date=decision_date,
            period_index=period_index,
            cost_bps=self.settings.transaction_cost_bps,
            n_observations_used=view.n_observations,
            data_last_date=view.last_date,
        )

    def _period_returns(
        self, decision_date: pd.Timestamp, period_index: int, final_day: pd.Timestamp
    ) -> pd.DataFrame | None:
        """Realised daily returns over ``(decision_date, next_decision]``.

        Called only after all decisions for ``decision_date`` are locked.
        """
        is_last = period_index == len(self.rebalance_dates) - 1
        period_end = final_day if is_last else self.rebalance_dates[period_index + 1]
        if period_end <= decision_date:
            return None

        window = self._realised_returns.loc[
            (self._realised_returns.index > decision_date)
            & (self._realised_returns.index <= period_end)
        ]
        window = window.fillna(0.0)
        return window if not window.empty else None

    def _uniform(self) -> pd.Series:
        n = len(self.tickers)
        return pd.Series(np.full(n, 1.0 / n), index=self.tickers)

    def _settings_summary(self) -> dict[str, Any]:
        s = self.settings
        return {
            "start": str(s.start),
            "end": str(s.end),
            "first_decision_date": str(self.rebalance_dates[0].date()),
            "last_decision_date": str(self.rebalance_dates[-1].date()),
            "n_rebalances": len(self.rebalance_dates),
            "lookback_years": s.lookback_years,
            "lookback_days": s.lookback_days,
            "rebalance_frequency": s.rebalance_frequency.value,
            "cutoff": s.cutoff.value,
            "transaction_cost_bps": s.transaction_cost_bps,
            "initial_capital": s.initial_capital,
            "risk_horizon_days": s.risk_horizon_days,
            "universe": list(self.tickers),
        }


class _StrategyState:
    """Mutable per-strategy bookkeeping during a run.

    Positions are tracked in currency units rather than weights, which makes
    drift between rebalances exact rather than approximated.
    """

    __slots__ = (
        "name", "tickers", "holdings", "value_points",
        "records", "weight_rows", "_seed_capital",
    )

    def __init__(self, name: str, tickers: list[str], capital: float) -> None:
        self.name = name
        self.tickers = tickers
        self.holdings = pd.Series(0.0, index=tickers)
        self.value_points: list[tuple[pd.Timestamp, float]] = []
        self.records: list[RebalanceRecord] = []
        self.weight_rows: dict[pd.Timestamp, pd.Series] = {}
        self._seed_capital = float(capital)

    @property
    def value(self) -> float:
        """Current mark-to-market value; the seed capital before the first trade."""
        total = float(self.holdings.sum())
        return total if total > 0 else self._seed_capital

    def current_weights(self) -> pd.Series:
        total = float(self.holdings.sum())
        if total <= 0:
            return pd.Series(0.0, index=self.tickers)
        return self.holdings / total

    def rebalance(
        self,
        decision: AllocationDecision,
        decision_date: pd.Timestamp,
        period_index: int,
        cost_bps: float,
        n_observations_used: int,
        data_last_date: pd.Timestamp,
    ) -> None:
        weights_before = self.current_weights()
        weights_after = decision.weights.reindex(self.tickers).astype(float)

        pre_trade_value = self.value

        # Weight change is measured against *drifted* weights, not the previous
        # target: positions move with the market between rebalances, and it is
        # the drifted position that must actually be traded away from.
        # At the first rebalance `weights_before` is the zero vector (all cash),
        # so `traded_fraction` is 1.0 -- the whole portfolio is bought.
        delta = (weights_after - weights_before).abs().sum()
        traded_fraction = float(delta)
        turnover = traded_fraction * 0.5  # reported one-way turnover (decision D10)

        # Costs are charged on notional traded, not on one-way turnover: a sale
        # and the purchase it funds are two chargeable trades.
        cost = traded_fraction * (cost_bps / 10_000.0) * pre_trade_value
        post_trade_value = pre_trade_value - cost

        if not self.value_points:
            self.value_points.append((decision_date, pre_trade_value))

        self.holdings = weights_after * post_trade_value
        self.weight_rows[decision_date] = weights_after
        self.records.append(
            RebalanceRecord(
                as_of=decision_date,
                period_index=period_index,
                weights_before=weights_before,
                weights_after=weights_after,
                turnover=turnover,
                traded_fraction=traded_fraction,
                cost=cost,
                portfolio_value=post_trade_value,
                status=decision.status,
                diagnostics=dict(decision.diagnostics),
                n_observations_used=n_observations_used,
                data_last_date=data_last_date,
            )
        )

    def advance(self, period_returns: pd.DataFrame) -> None:
        """Mark positions to market across one holding period."""
        growth = (1.0 + period_returns.loc[:, self.tickers]).cumprod()
        asset_values = growth.mul(self.holdings, axis=1)
        totals = asset_values.sum(axis=1)
        for ts, v in totals.items():
            self.value_points.append((ts, float(v)))
        self.holdings = asset_values.iloc[-1]

    def finalise(self, settings_summary: dict[str, Any]) -> BacktestResult:
        index = pd.DatetimeIndex([ts for ts, _ in self.value_points], name="date")
        values = pd.Series(
            [v for _, v in self.value_points], index=index, name=self.name, dtype="float64"
        )
        values = values[~values.index.duplicated(keep="last")].sort_index()

        weights_history = pd.DataFrame(self.weight_rows).T
        weights_history.index.name = "date"

        return BacktestResult(
            strategy_name=self.name,
            portfolio_values=values,
            daily_returns=values.pct_change().dropna().rename(self.name),
            weights_history=weights_history,
            rebalances=list(self.records),
            settings_summary=dict(settings_summary),
        )
