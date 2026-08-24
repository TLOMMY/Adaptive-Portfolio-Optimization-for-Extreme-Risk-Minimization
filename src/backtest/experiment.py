"""Assembling and running the four-model comparison for a profile and period.

This module is deliberately UI-independent: the Streamlit app calls it, but so
can a script or a test. Nothing here imports Streamlit.

All four models are run under the **selected profile's constraints** -- the same
return target, turnover limit and weight cap. That is what makes the comparison
answer the project's actual question: given this investor's stated requirements,
which formulation best satisfies their objective? Running each model under
different constraints would compare constraint sets rather than objectives.

Equal Weight is the exception by construction: it uses no estimated parameters
and ignores the return target and turnover limit entirely. That is the point of
including it -- it is the benchmark that cannot be wrong about anything it never
estimated.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.backtest.engine import BacktestEngine
from src.backtest.results import ExperimentResult
from src.backtest.strategy import Strategy
from src.config.assets import Universe
from src.config.periods import EvaluationPeriod
from src.config.settings import BacktestSettings, ExperimentMode
from src.portfolio.constraints import ConstraintSet
from src.portfolio.cvar import CVaROptimizer
from src.portfolio.equal_weight import EqualWeightOptimizer
from src.portfolio.markowitz import MarkowitzOptimizer
from src.portfolio.robust_variance import RobustMinimumVarianceOptimizer
from src.profiles.models import COMMON_MAX_WEIGHT, InvestorProfile, ModelChoice
from src.profiles.presets import PROFILES

EQUAL_WEIGHT = "Equal Weight"
MARKOWITZ = "Markowitz"
CVAR = "CVaR 95%"
ROBUST = "Robust Min-Variance"

COMPARISON_ORDER = [EQUAL_WEIGHT, MARKOWITZ, CVAR, ROBUST]


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    """Everything that defines one run of the comparison."""

    profile: InvestorProfile
    period: EvaluationPeriod
    universe: Universe
    lookback_years: float = 3.0

    def settings(self) -> BacktestSettings:
        """Backtest settings for this spec.

        The evaluation window comes from the period; every other setting is
        fixed. Mode is RESEARCH: these windows are frozen, so results do not
        change as new data arrives.
        """
        return BacktestSettings(
            start=self.period.start,
            end=self.period.end,
            lookback_years=self.lookback_years,
            mode=ExperimentMode.RESEARCH,
        )


def build_comparison_strategies(
    profile: InvestorProfile,
    lookback_days: int,
    asset_class_map: dict[str, list[str]] | None = None,
) -> dict[str, Strategy]:
    """The four comparison models, all under the profile's constraints."""
    constraints: ConstraintSet = profile.constraint_set()
    classes = asset_class_map or {}
    shared = {
        "constraints": constraints,
        "asset_class_map": classes,
        "lookback_days": lookback_days,
    }
    return {
        # Equal weight ignores the return target and turnover limit by nature;
        # it is included as the no-estimation benchmark.
        EQUAL_WEIGHT: EqualWeightOptimizer(
            constraints=ConstraintSet(max_weight=profile.max_weight),
            asset_class_map=classes,
            lookback_days=lookback_days,
            name=EQUAL_WEIGHT,
        ),
        MARKOWITZ: MarkowitzOptimizer(
            risk_aversion=profile.risk_aversion or 2.5, name=MARKOWITZ, **shared
        ),
        CVAR: CVaROptimizer(
            confidence=profile.cvar_confidence or 0.95, name=CVAR, **shared
        ),
        ROBUST: RobustMinimumVarianceOptimizer(name=ROBUST, **shared),
    }


def run_comparison(prices: pd.DataFrame, spec: ExperimentSpec) -> ExperimentResult:
    """Run all four models over the spec's period and return their realised paths."""
    settings = spec.settings()
    engine = BacktestEngine(prices, settings)
    strategies = build_comparison_strategies(
        profile=spec.profile,
        lookback_days=settings.lookback_days,
        asset_class_map=spec.universe.asset_class_map(),
    )
    return engine.run(strategies)


# ---------------------------------------------------------------------------
# Diagnostic comparison
#
# The headline comparison runs all four models under one profile's constraints.
# The diagnostics view asks a different question: how do the *profiles* differ
# from each other? So each strategy here carries its own profile's return
# target, turnover limit and model parameters -- Growth's Markowitz is a
# genuinely different program from Balanced's Markowitz, and comparing them is
# the point.
#
# All of them still run in a single engine pass, so they share one MarketDataView
# at every decision date and remain a controlled comparison.
# ---------------------------------------------------------------------------


def diagnostic_label(profile: InvestorProfile) -> str:
    """Display name pairing a profile with its model, e.g. 'Growth - Markowitz'."""
    short = {
        ModelChoice.MARKOWITZ: "Markowitz",
        ModelChoice.CVAR: "CVaR 95%",
        ModelChoice.ROBUST: "Robust Min-Variance",
        ModelChoice.EQUAL_WEIGHT: "Equal Weight",
    }[profile.model]
    return f"{profile.name.split(' / ')[0]} — {short}"


def diagnostic_options() -> dict[str, InvestorProfile | None]:
    """Every strategy available for diagnostic comparison.

    Equal Weight maps to ``None``: it uses no estimated parameters and honours
    neither a return target nor a turnover limit, so it is not tied to a profile.
    """
    options: dict[str, InvestorProfile | None] = {EQUAL_WEIGHT: None}
    for profile in PROFILES.values():
        options[diagnostic_label(profile)] = profile
    return options


def build_diagnostic_strategies(
    lookback_days: int,
    asset_class_map: dict[str, list[str]] | None = None,
) -> dict[str, Strategy]:
    """One strategy per diagnostic option, each under its own profile's rules."""
    classes = asset_class_map or {}
    strategies: dict[str, Strategy] = {
        EQUAL_WEIGHT: EqualWeightOptimizer(
            constraints=ConstraintSet(max_weight=COMMON_MAX_WEIGHT),
            asset_class_map=classes,
            lookback_days=lookback_days,
            name=EQUAL_WEIGHT,
        )
    }
    for label, profile in diagnostic_options().items():
        if profile is None:
            continue
        optimizer = profile.build_optimizer(lookback_days, classes)
        optimizer.name = label
        strategies[label] = optimizer
    return strategies


def run_diagnostics(prices: pd.DataFrame, period: EvaluationPeriod,
                    universe: Universe, lookback_years: float = 3.0) -> ExperimentResult:
    """Run every diagnostic strategy over one period.

    Profile-independent: the result depends only on the period, so a single
    cached run serves every profile selection in the UI.
    """
    settings = BacktestSettings(
        start=period.start,
        end=period.end,
        lookback_years=lookback_years,
        mode=ExperimentMode.RESEARCH,
    )
    engine = BacktestEngine(prices, settings)
    return engine.run(
        build_diagnostic_strategies(
            lookback_days=settings.lookback_days,
            asset_class_map=universe.asset_class_map(),
        )
    )
