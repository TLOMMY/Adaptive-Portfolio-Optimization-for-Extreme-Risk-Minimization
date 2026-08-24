"""Portfolio constraints, shared by every optimizer.

Constraints are declared once as data (:class:`ConstraintSet`) and translated
into CVXPY expressions by :func:`build_constraints`.  Every model therefore
faces exactly the same feasible region for a given configuration, which is what
makes a comparison between models a comparison of *objectives* rather than of
incidentally different constraint code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np


class ConstraintError(ValueError):
    """Raised when a constraint set cannot describe a valid portfolio."""


@dataclass(frozen=True, slots=True)
class ConstraintSet:
    """The feasible region for a long-only portfolio.

    Attributes
    ----------
    max_weight
        Upper bound on any single asset's weight. ``1.0`` means unconstrained.
    allow_shorting
        Short selling is disabled throughout the MVP. The flag exists so the
        no-shorting assumption is explicit and testable rather than implied by
        a hard-coded lower bound.
    asset_class_limits
        Upper bound on the total weight of each asset class, e.g.
        ``{"Equity": 0.6}``. Classes absent from the mapping are unconstrained.
    min_return
        Minimum required annualised expected return, as a decimal (``0.08`` =
        8% per year). ``None`` imposes no return target.

    Notes
    -----
    Turnover constraints are part of the investor-profile specification and are
    deferred to that phase; they are not silently applied here.
    """

    max_weight: float = 1.0
    allow_shorting: bool = False
    asset_class_limits: dict[str, float] = field(default_factory=dict)
    min_return: float | None = None

    def __post_init__(self) -> None:
        if not 0.0 < self.max_weight <= 1.0:
            raise ConstraintError(
                f"max_weight must lie in (0, 1], got {self.max_weight}"
            )
        if self.allow_shorting:
            raise ConstraintError(
                "short selling is not supported in this phase; "
                "the optimizers assume a long-only feasible region"
            )
        for name, limit in self.asset_class_limits.items():
            if not 0.0 <= limit <= 1.0:
                raise ConstraintError(
                    f"asset-class limit for {name!r} must lie in [0, 1], got {limit}"
                )

    @property
    def min_weight(self) -> float:
        return 0.0

    def validate_for(self, tickers: list[str], asset_class_map: dict[str, list[str]]) -> None:
        """Check the set can be satisfied at all, before a solver is invoked.

        These are structural impossibilities -- a budget that cannot be filled --
        as distinct from a return target that merely happens to be unattainable.
        The latter is handled by the shortfall mechanism; this raises.
        """
        n = len(tickers)
        if n == 0:
            raise ConstraintError("no assets to allocate across")

        if self.max_weight * n < 1.0 - 1e-9:
            raise ConstraintError(
                f"max_weight={self.max_weight} across {n} assets caps total exposure at "
                f"{self.max_weight * n:.3f}, so the weights cannot sum to 1. "
                f"Raise max_weight to at least {1.0 / n:.4f}."
            )

        unknown = set(self.asset_class_limits) - set(asset_class_map)
        if unknown:
            raise ConstraintError(
                f"asset-class limits reference unknown classes: {sorted(unknown)}. "
                f"Known classes: {sorted(asset_class_map)}"
            )

        # When asset-class limits are in force, the capped classes plus the
        # uncapped remainder must still be able to reach a total weight of 1.
        # Skipped when no limits are set: an empty class map carries no
        # information about reachability, and the max_weight check above already
        # covers the unconstrained case.
        if not self.asset_class_limits:
            return

        reachable = 0.0
        for cls, members in asset_class_map.items():
            members_present = [t for t in members if t in tickers]
            if not members_present:
                continue
            class_cap = self.asset_class_limits.get(cls, 1.0)
            reachable += min(class_cap, self.max_weight * len(members_present))
        if reachable < 1.0 - 1e-9:
            raise ConstraintError(
                f"asset-class limits and max_weight together cap total exposure at "
                f"{reachable:.3f}; the weights cannot sum to 1."
            )


def build_constraints(
    x: cp.Variable,
    tickers: list[str],
    constraints: ConstraintSet,
    asset_class_map: dict[str, list[str]] | None = None,
) -> list[cp.Constraint]:
    """Translate a :class:`ConstraintSet` into CVXPY constraints.

    The returned list always contains the budget constraint and the box bounds.
    The minimum-return constraint is **not** included -- it is handled separately
    by the shortfall mechanism in the optimizers, so that an unattainable target
    is measured rather than quietly dropped or left to fail as an infeasibility.
    """
    asset_class_map = asset_class_map or {}
    built: list[cp.Constraint] = [
        cp.sum(x) == 1,                       # fully invested
        x >= constraints.min_weight,          # long only
        x <= constraints.max_weight,          # concentration cap
    ]

    for cls, limit in constraints.asset_class_limits.items():
        members = [t for t in asset_class_map.get(cls, []) if t in tickers]
        if not members:
            continue
        selector = np.array([1.0 if t in members else 0.0 for t in tickers])
        built.append(selector @ x <= limit)

    return built


def asset_class_exposures(
    weights: dict[str, float] | np.ndarray,
    tickers: list[str],
    asset_class_map: dict[str, list[str]],
) -> dict[str, float]:
    """Total weight per asset class, for reporting and constraint verification."""
    if not isinstance(weights, dict):
        weights = dict(zip(tickers, np.asarray(weights, dtype=float), strict=True))
    return {
        cls: float(sum(weights.get(t, 0.0) for t in members))
        for cls, members in asset_class_map.items()
    }
