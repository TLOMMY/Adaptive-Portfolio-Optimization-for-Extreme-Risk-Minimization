"""Tests for investor profiles, evaluation periods and the experiment runner.

These cover the UI-independent personalization logic: nothing here imports
Streamlit, so the demo's correctness does not depend on its presentation.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from src.backtest.experiment import (
    COMPARISON_ORDER,
    CVAR,
    EQUAL_WEIGHT,
    MARKOWITZ,
    ROBUST,
    ExperimentSpec,
    build_comparison_strategies,
)
from src.config.assets import DEFAULT_UNIVERSE
from src.config.periods import DEFAULT_PERIOD, PERIODS
from src.config.settings import ExperimentMode
from src.portfolio.cvar import CVaROptimizer
from src.portfolio.equal_weight import EqualWeightOptimizer
from src.portfolio.markowitz import MarkowitzOptimizer
from src.portfolio.robust_variance import RobustMinimumVarianceOptimizer
from src.profiles.models import (
    COMMON_MAX_WEIGHT,
    InvestorProfile,
    LiquidityPreference,
    ModelChoice,
)
from src.profiles.presets import (
    BALANCED,
    DEFAULT_PROFILE,
    DOWNSIDE_PROTECTION,
    EXTREME_LOW_RISK,
    GROWTH,
    PROFILES,
    profile_mapping_table,
)

# ---------------------------------------------------------------------------
# Profile configuration
# ---------------------------------------------------------------------------


def test_there_are_exactly_four_profiles():
    assert len(PROFILES) == 4
    assert list(PROFILES) == ["growth", "balanced", "downside", "low_risk"]


def test_profiles_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        GROWTH.return_target = 0.5  # type: ignore[misc]


@pytest.mark.parametrize(
    ("profile", "model", "target"),
    [
        (GROWTH, ModelChoice.MARKOWITZ, 0.08),
        (BALANCED, ModelChoice.MARKOWITZ, 0.06),
        (DOWNSIDE_PROTECTION, ModelChoice.CVAR, 0.04),
        (EXTREME_LOW_RISK, ModelChoice.ROBUST, 0.02),
    ],
)
def test_profile_maps_to_its_specified_model_and_target(profile, model, target):
    assert profile.model is model
    assert profile.return_target == pytest.approx(target)


def test_growth_is_less_risk_averse_than_balanced():
    """The two Markowitz profiles must differ in the factor that defines them."""
    assert GROWTH.risk_aversion < BALANCED.risk_aversion


def test_return_targets_decrease_with_risk_appetite():
    targets = [p.return_target for p in PROFILES.values()]
    assert targets == sorted(targets, reverse=True)


def test_turnover_limits_match_the_liquidity_labels():
    assert GROWTH.liquidity is LiquidityPreference.FLEXIBLE
    assert BALANCED.liquidity is LiquidityPreference.MODERATE
    for profile in (DOWNSIDE_PROTECTION, EXTREME_LOW_RISK):
        assert profile.liquidity is LiquidityPreference.CONSERVATIVE

    assert GROWTH.turnover_limit > BALANCED.turnover_limit
    assert BALANCED.turnover_limit > DOWNSIDE_PROTECTION.turnover_limit


def test_profiles_differ_only_in_the_three_decision_factors():
    """Weight caps must be common, so outcomes are attributable to the factors."""
    for profile in PROFILES.values():
        assert profile.max_weight == COMMON_MAX_WEIGHT
        assert profile.asset_class_limits == {}


def test_cvar_profile_carries_a_confidence_level():
    assert DOWNSIDE_PROTECTION.cvar_confidence == 0.95


def test_a_markowitz_profile_without_risk_aversion_is_rejected():
    with pytest.raises(ValueError, match="risk_aversion"):
        InvestorProfile(
            key="x", name="X", tagline="", risk_objective="",
            model=ModelChoice.MARKOWITZ, return_target=0.05,
            turnover_limit=None, liquidity=LiquidityPreference.MODERATE,
        )


def test_a_cvar_profile_without_a_confidence_level_is_rejected():
    with pytest.raises(ValueError, match="cvar_confidence"):
        InvestorProfile(
            key="x", name="X", tagline="", risk_objective="",
            model=ModelChoice.CVAR, return_target=0.05,
            turnover_limit=None, liquidity=LiquidityPreference.MODERATE,
        )


def test_a_negative_return_target_is_rejected():
    with pytest.raises(ValueError, match="return_target"):
        InvestorProfile(
            key="x", name="X", tagline="", risk_objective="",
            model=ModelChoice.ROBUST, return_target=-0.01,
            turnover_limit=None, liquidity=LiquidityPreference.MODERATE,
        )


# ---------------------------------------------------------------------------
# Profile -> constraints and optimizer
# ---------------------------------------------------------------------------


def test_constraint_set_carries_all_three_factors():
    constraints = BALANCED.constraint_set()
    assert constraints.min_return == pytest.approx(BALANCED.return_target)
    assert constraints.max_turnover == pytest.approx(BALANCED.turnover_limit)
    assert constraints.max_weight == COMMON_MAX_WEIGHT


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (GROWTH, MarkowitzOptimizer),
        (BALANCED, MarkowitzOptimizer),
        (DOWNSIDE_PROTECTION, CVaROptimizer),
        (EXTREME_LOW_RISK, RobustMinimumVarianceOptimizer),
    ],
)
def test_profile_builds_the_right_optimizer(profile, expected):
    optimizer = profile.build_optimizer(lookback_days=756)
    assert isinstance(optimizer, expected)
    assert optimizer.constraints.min_return == pytest.approx(profile.return_target)
    assert optimizer.constraints.max_turnover == profile.turnover_limit


def test_built_optimizer_carries_the_model_parameters():
    markowitz = GROWTH.build_optimizer(756)
    assert markowitz.risk_aversion == pytest.approx(GROWTH.risk_aversion)

    cvar = DOWNSIDE_PROTECTION.build_optimizer(756)
    assert cvar.confidence == pytest.approx(0.95)


def test_strategy_name_matches_the_comparison_set():
    for profile in PROFILES.values():
        assert profile.strategy_name in COMPARISON_ORDER


def test_every_profile_has_display_text():
    for profile in PROFILES.values():
        assert profile.name and profile.tagline and profile.risk_objective
        assert profile.model_label and profile.risk_measure_label


def test_mapping_table_has_one_row_per_profile():
    rows = profile_mapping_table()
    assert len(rows) == 4
    for row in rows:
        assert set(row) == {
            "Profile", "Risk objective", "Model",
            "Return target", "Turnover limit", "Liquidity",
        }


def test_default_profile_is_one_of_the_four():
    assert DEFAULT_PROFILE.key in PROFILES


# ---------------------------------------------------------------------------
# Evaluation periods
# ---------------------------------------------------------------------------


def test_the_four_predefined_periods_exist():
    assert list(PERIODS) == ["full", "a", "b", "c"]


def test_full_period_spans_2016_to_2024():
    full = PERIODS["full"]
    assert full.start == date(2016, 1, 1)
    assert full.end == date(2024, 12, 31)


@pytest.mark.parametrize(
    ("key", "start", "end"),
    [
        ("a", date(2016, 1, 1), date(2018, 12, 31)),
        ("b", date(2019, 1, 1), date(2021, 12, 31)),
        ("c", date(2022, 1, 1), date(2024, 12, 31)),
    ],
)
def test_subperiods_are_three_years_each(key, start, end):
    period = PERIODS[key]
    assert period.start == start
    assert period.end == end
    assert 2.9 < period.years < 3.1


def test_subperiods_tile_the_full_period_without_gaps():
    a, b, c, full = PERIODS["a"], PERIODS["b"], PERIODS["c"], PERIODS["full"]
    assert a.start == full.start
    assert c.end == full.end
    assert (b.start - a.end).days == 1
    assert (c.start - b.end).days == 1


def test_default_period_is_the_full_period():
    assert DEFAULT_PERIOD is PERIODS["full"]


# ---------------------------------------------------------------------------
# Experiment assembly
# ---------------------------------------------------------------------------


def test_spec_settings_use_the_period_window_and_research_mode():
    spec = ExperimentSpec(
        profile=BALANCED, period=PERIODS["b"], universe=DEFAULT_UNIVERSE
    )
    settings = spec.settings()
    assert settings.start == PERIODS["b"].start
    assert settings.end == PERIODS["b"].end
    assert settings.mode is ExperimentMode.RESEARCH
    assert settings.is_reproducible


def test_settings_are_fixed_across_periods_apart_from_the_window():
    specs = [
        ExperimentSpec(profile=BALANCED, period=PERIODS[k], universe=DEFAULT_UNIVERSE)
        for k in PERIODS
    ]
    settings = [s.settings() for s in specs]
    assert len({s.lookback_years for s in settings}) == 1
    assert len({s.rebalance_frequency for s in settings}) == 1
    assert len({s.transaction_cost_bps for s in settings}) == 1


def test_comparison_always_contains_the_same_four_models():
    strategies = build_comparison_strategies(BALANCED, lookback_days=756)
    assert list(strategies) == COMPARISON_ORDER == [EQUAL_WEIGHT, MARKOWITZ, CVAR, ROBUST]


def test_optimized_models_all_inherit_the_profile_constraints():
    """A comparison is only meaningful if the models face the same feasible region."""
    strategies = build_comparison_strategies(DOWNSIDE_PROTECTION, lookback_days=756)
    for name in (MARKOWITZ, CVAR, ROBUST):
        constraints = strategies[name].constraints
        assert constraints.min_return == pytest.approx(DOWNSIDE_PROTECTION.return_target)
        assert constraints.max_turnover == pytest.approx(
            DOWNSIDE_PROTECTION.turnover_limit
        )
        assert constraints.max_weight == COMMON_MAX_WEIGHT


def test_equal_weight_is_exempt_from_target_and_turnover():
    """1/N cannot honour a return target; pretending otherwise would be false."""
    strategies = build_comparison_strategies(GROWTH, lookback_days=756)
    equal = strategies[EQUAL_WEIGHT]
    assert isinstance(equal, EqualWeightOptimizer)
    assert equal.constraints.min_return is None
    assert equal.constraints.max_turnover is None
    assert equal.constraints.max_weight == COMMON_MAX_WEIGHT


def test_switching_profile_changes_the_constraints_the_models_see():
    growth = build_comparison_strategies(GROWTH, 756)[MARKOWITZ]
    low_risk = build_comparison_strategies(EXTREME_LOW_RISK, 756)[MARKOWITZ]
    assert growth.constraints.min_return != low_risk.constraints.min_return
    assert growth.constraints.max_turnover != low_risk.constraints.max_turnover
