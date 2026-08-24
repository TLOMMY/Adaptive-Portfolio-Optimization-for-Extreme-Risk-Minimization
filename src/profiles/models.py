"""Investor-profile configuration.

A profile is a *quantitative* configuration object, not a label. Each one is
defined by exactly three decision factors:

1. **Risk objective** -- which optimization formulation expresses what the
   investor is trying to avoid;
2. **Return requirement** -- the minimum annualised expected return demanded;
3. **Liquidity preference** -- how much trading the investor tolerates, as a
   one-way turnover limit per rebalance.

Everything else (asset universe, weight caps, lookback, rebalance cadence,
estimators) is held **common across profiles** so that differences in outcome
are attributable to the three factors above and not to incidental configuration.

These are illustrative academic presets for a teaching demonstration. They are
not investment advice and the parameter values are prototype assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.portfolio.base import PortfolioOptimizer
from src.portfolio.constraints import ConstraintSet


class ModelChoice(StrEnum):
    """The optimization formulation a profile's risk objective maps to."""

    MARKOWITZ = "markowitz"
    CVAR = "cvar"
    ROBUST = "robust"
    EQUAL_WEIGHT = "equal_weight"


class LiquidityPreference(StrEnum):
    """Human-readable label for the turnover limit."""

    FLEXIBLE = "Flexible"
    MODERATE = "Moderate"
    CONSERVATIVE = "Conservative"


# Structural constraints shared by every profile, so that profiles differ only
# in the three decision factors.
COMMON_MAX_WEIGHT = 0.35
"""No single asset may exceed 35% of the portfolio, for any profile."""


@dataclass(frozen=True, slots=True)
class InvestorProfile:
    """One illustrative investor configuration.

    Attributes
    ----------
    key
        Stable identifier used in code and URLs.
    name
        Display name.
    tagline
        One line describing who this profile represents.
    risk_objective
        Plain-language statement of what the investor is trying to avoid.
    model
        The optimization formulation the objective maps to.
    return_target
        Minimum required annualised expected return, as a decimal. Illustrative.
    turnover_limit
        Maximum one-way turnover per rebalance, or ``None`` for no limit.
    liquidity
        Label for the turnover limit.
    risk_aversion
        Markowitz lambda. Ignored by other models.
    cvar_confidence
        CVaR alpha. Ignored by other models.
    max_weight
        Per-asset cap. Common across profiles by design.
    """

    key: str
    name: str
    tagline: str
    risk_objective: str
    model: ModelChoice
    return_target: float
    turnover_limit: float | None
    liquidity: LiquidityPreference
    risk_aversion: float | None = None
    cvar_confidence: float | None = None
    max_weight: float = COMMON_MAX_WEIGHT
    asset_class_limits: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.model is ModelChoice.MARKOWITZ and self.risk_aversion is None:
            raise ValueError(f"{self.key}: Markowitz profiles need a risk_aversion")
        if self.model is ModelChoice.CVAR and self.cvar_confidence is None:
            raise ValueError(f"{self.key}: CVaR profiles need a cvar_confidence")
        if self.return_target < 0:
            raise ValueError(f"{self.key}: return_target must be non-negative")

    # -- derived configuration ----------------------------------------------

    @property
    def model_label(self) -> str:
        return {
            ModelChoice.MARKOWITZ: "Markowitz Mean-Variance",
            ModelChoice.CVAR: "CVaR (Expected Shortfall)",
            ModelChoice.ROBUST: "Robust Minimum Variance",
            ModelChoice.EQUAL_WEIGHT: "Equal Weight",
        }[self.model]

    @property
    def strategy_name(self) -> str:
        """Name of the comparison strategy this profile maps to."""
        return {
            ModelChoice.MARKOWITZ: "Markowitz",
            ModelChoice.CVAR: "CVaR 95%",
            ModelChoice.ROBUST: "Robust Min-Variance",
            ModelChoice.EQUAL_WEIGHT: "Equal Weight",
        }[self.model]

    @property
    def risk_measure_label(self) -> str:
        """What 'estimated risk' means for this profile's model."""
        return {
            ModelChoice.MARKOWITZ: "Estimated annualised volatility",
            ModelChoice.CVAR: "Estimated 1-day 95% CVaR",
            ModelChoice.ROBUST: "Worst-case annualised volatility",
            ModelChoice.EQUAL_WEIGHT: "Estimated annualised volatility",
        }[self.model]

    def constraint_set(self) -> ConstraintSet:
        """The feasible region implied by this profile."""
        return ConstraintSet(
            max_weight=self.max_weight,
            asset_class_limits=dict(self.asset_class_limits),
            min_return=self.return_target,
            max_turnover=self.turnover_limit,
        )

    def build_optimizer(
        self,
        lookback_days: int,
        asset_class_map: dict[str, list[str]] | None = None,
    ) -> PortfolioOptimizer:
        """Instantiate the optimizer this profile's risk objective maps to."""
        from src.portfolio.cvar import CVaROptimizer
        from src.portfolio.equal_weight import EqualWeightOptimizer
        from src.portfolio.markowitz import MarkowitzOptimizer
        from src.portfolio.robust_variance import RobustMinimumVarianceOptimizer

        shared: dict[str, Any] = {
            "constraints": self.constraint_set(),
            "asset_class_map": asset_class_map or {},
            "lookback_days": lookback_days,
        }
        if self.model is ModelChoice.MARKOWITZ:
            return MarkowitzOptimizer(risk_aversion=self.risk_aversion, **shared)
        if self.model is ModelChoice.CVAR:
            return CVaROptimizer(confidence=self.cvar_confidence, **shared)
        if self.model is ModelChoice.ROBUST:
            return RobustMinimumVarianceOptimizer(**shared)
        return EqualWeightOptimizer(**shared)

    def summary(self) -> dict[str, Any]:
        """Row for the profile-mapping table."""
        return {
            "Profile": self.name,
            "Risk objective": self.risk_objective,
            "Model": self.model_label,
            "Return target": f"{self.return_target:.0%}",
            "Turnover limit": (
                "None" if self.turnover_limit is None else f"{self.turnover_limit:.0%}"
            ),
            "Liquidity": self.liquidity.value,
        }
