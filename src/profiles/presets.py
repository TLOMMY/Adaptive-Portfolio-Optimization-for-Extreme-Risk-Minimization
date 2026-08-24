"""The four illustrative investor profiles.

Illustrative academic presets for a teaching demonstration -- **not** investment
advice, and the parameter values are prototype assumptions chosen to make the
comparison legible, not calibrated to any real investor.

The four differ only in the three decision factors (risk objective, return
requirement, liquidity preference). Weight caps, universe, lookback, rebalance
cadence and estimators are identical across all of them.
"""

from __future__ import annotations

from src.profiles.models import InvestorProfile, LiquidityPreference, ModelChoice

GROWTH = InvestorProfile(
    key="growth",
    name="Growth",
    tagline="Long horizon, willing to ride out volatility in pursuit of return.",
    risk_objective="Favour expected return, accepting volatility along the way.",
    model=ModelChoice.MARKOWITZ,
    risk_aversion=1.0,
    return_target=0.08,
    turnover_limit=0.50,
    liquidity=LiquidityPreference.FLEXIBLE,
)

BALANCED = InvestorProfile(
    key="balanced",
    name="Balanced",
    tagline="Wants growth but is unwilling to accept the full swing of equities.",
    risk_objective="Balance expected return against volatility.",
    model=ModelChoice.MARKOWITZ,
    risk_aversion=5.0,
    return_target=0.06,
    turnover_limit=0.25,
    liquidity=LiquidityPreference.MODERATE,
)

DOWNSIDE_PROTECTION = InvestorProfile(
    key="downside",
    name="Downside Protection / Retirement",
    tagline="Drawing on the portfolio soon; a severe loss is hard to recover from.",
    risk_objective="Reduce severe downside losses, not day-to-day variability.",
    model=ModelChoice.CVAR,
    cvar_confidence=0.95,
    return_target=0.04,
    turnover_limit=0.15,
    liquidity=LiquidityPreference.CONSERVATIVE,
)

EXTREME_LOW_RISK = InvestorProfile(
    key="low_risk",
    name="Extreme Low Risk",
    tagline="Capital preservation first, and sceptical that any risk estimate is exact.",
    risk_objective=(
        "Minimise risk under uncertainty about the covariance estimate itself."
    ),
    model=ModelChoice.ROBUST,
    return_target=0.02,
    turnover_limit=0.15,
    liquidity=LiquidityPreference.CONSERVATIVE,
)

PROFILES: dict[str, InvestorProfile] = {
    p.key: p for p in (GROWTH, BALANCED, DOWNSIDE_PROTECTION, EXTREME_LOW_RISK)
}

DEFAULT_PROFILE = BALANCED


def profile_mapping_table() -> list[dict[str, str]]:
    """The four-profile mapping, for display."""
    return [p.summary() for p in PROFILES.values()]
