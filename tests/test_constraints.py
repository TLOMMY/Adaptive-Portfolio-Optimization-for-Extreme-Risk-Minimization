"""Tests for the shared constraint layer."""

from __future__ import annotations

import cvxpy as cp
import numpy as np
import pytest

from src.portfolio.constraints import (
    ConstraintError,
    ConstraintSet,
    asset_class_exposures,
    build_constraints,
)

TICKERS = ["SAFE", "BOND", "STOCK", "WILD"]
CLASSES = {"Equity": ["STOCK", "WILD"], "Fixed Income": ["SAFE", "BOND"]}


def solve_feasible(constraints: ConstraintSet, tickers=TICKERS, classes=CLASSES):
    """Return any feasible portfolio, to check the region is what we think."""
    x = cp.Variable(len(tickers))
    problem = cp.Problem(
        cp.Minimize(cp.sum_squares(x)), build_constraints(x, tickers, constraints, classes)
    )
    problem.solve(solver="CLARABEL")
    return problem.status, (None if x.value is None else np.asarray(x.value))


# ---------------------------------------------------------------------------
# Declaration validity
# ---------------------------------------------------------------------------


def test_defaults_are_long_only_and_fully_invested():
    c = ConstraintSet()
    assert c.max_weight == 1.0
    assert c.min_weight == 0.0
    assert c.allow_shorting is False
    assert c.min_return is None
    assert c.asset_class_limits == {}


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.5])
def test_invalid_max_weight_is_rejected(bad):
    with pytest.raises(ConstraintError, match="max_weight"):
        ConstraintSet(max_weight=bad)


def test_shorting_is_explicitly_unsupported():
    with pytest.raises(ConstraintError, match="short selling"):
        ConstraintSet(allow_shorting=True)


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_invalid_asset_class_limit_is_rejected(bad):
    with pytest.raises(ConstraintError, match="asset-class limit"):
        ConstraintSet(asset_class_limits={"Equity": bad})


# ---------------------------------------------------------------------------
# Structural feasibility, checked before a solver runs
# ---------------------------------------------------------------------------


def test_max_weight_too_small_to_fill_the_budget_is_rejected():
    with pytest.raises(ConstraintError, match="cannot sum to 1"):
        ConstraintSet(max_weight=0.2).validate_for(TICKERS, CLASSES)


def test_max_weight_exactly_filling_the_budget_is_accepted():
    ConstraintSet(max_weight=0.25).validate_for(TICKERS, CLASSES)


def test_unknown_asset_class_is_rejected():
    with pytest.raises(ConstraintError, match="unknown classes"):
        ConstraintSet(asset_class_limits={"Crypto": 0.5}).validate_for(TICKERS, CLASSES)


def test_asset_class_limits_that_cannot_fill_the_budget_are_rejected():
    limits = {"Equity": 0.3, "Fixed Income": 0.3}
    with pytest.raises(ConstraintError, match="cap total exposure"):
        ConstraintSet(asset_class_limits=limits).validate_for(TICKERS, CLASSES)


def test_no_assets_is_rejected():
    with pytest.raises(ConstraintError, match="no assets"):
        ConstraintSet().validate_for([], {})


def test_validation_without_asset_class_limits_ignores_the_class_map():
    """An empty class map must not be read as 'nothing is reachable'."""
    ConstraintSet(max_weight=0.5).validate_for(TICKERS, {})


# ---------------------------------------------------------------------------
# The feasible region the solver actually sees
# ---------------------------------------------------------------------------


def test_built_constraints_enforce_budget_and_non_negativity():
    status, weights = solve_feasible(ConstraintSet())
    assert status == cp.OPTIMAL
    assert weights.sum() == pytest.approx(1.0)
    assert (weights >= -1e-9).all()


def test_built_constraints_enforce_the_max_weight_cap():
    status, weights = solve_feasible(ConstraintSet(max_weight=0.3))
    assert status == cp.OPTIMAL
    assert weights.max() <= 0.3 + 1e-7


def test_built_constraints_enforce_asset_class_limits():
    status, weights = solve_feasible(
        ConstraintSet(asset_class_limits={"Equity": 0.25})
    )
    assert status == cp.OPTIMAL
    equity = weights[TICKERS.index("STOCK")] + weights[TICKERS.index("WILD")]
    assert equity <= 0.25 + 1e-7


def test_minimum_return_is_not_built_into_the_constraint_list():
    """The return target is handled by the shortfall mechanism, not here."""
    x = cp.Variable(len(TICKERS))
    without = build_constraints(x, TICKERS, ConstraintSet(), CLASSES)
    with_target = build_constraints(x, TICKERS, ConstraintSet(min_return=0.5), CLASSES)
    assert len(without) == len(with_target)


def test_limits_on_classes_absent_from_the_universe_are_skipped():
    x = cp.Variable(2)
    built = build_constraints(
        x, ["SAFE", "BOND"], ConstraintSet(asset_class_limits={"Equity": 0.5}), CLASSES
    )
    assert len(built) == 3  # budget + two box bounds, no equity row


# ---------------------------------------------------------------------------
# Exposure reporting
# ---------------------------------------------------------------------------


def test_asset_class_exposures_sum_to_the_portfolio():
    weights = {"SAFE": 0.1, "BOND": 0.2, "STOCK": 0.3, "WILD": 0.4}
    exposures = asset_class_exposures(weights, TICKERS, CLASSES)
    assert exposures["Fixed Income"] == pytest.approx(0.3)
    assert exposures["Equity"] == pytest.approx(0.7)
    assert sum(exposures.values()) == pytest.approx(1.0)


def test_asset_class_exposures_accept_an_array():
    exposures = asset_class_exposures(np.array([0.1, 0.2, 0.3, 0.4]), TICKERS, CLASSES)
    assert exposures["Equity"] == pytest.approx(0.7)
