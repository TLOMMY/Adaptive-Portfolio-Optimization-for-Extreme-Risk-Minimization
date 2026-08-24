"""Tests for the ex-post strategy diagnostics.

Two things matter here beyond arithmetic correctness:

* the diagnostics must be **inert** -- computing them must not change any
  portfolio decision, and no future return may reach an optimizer;
* the interpretation text must state only what the numbers support.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine
from src.backtest.experiment import (
    diagnostic_label,
    diagnostic_options,
    run_diagnostics,
)
from src.config.assets import DEFAULT_UNIVERSE
from src.config.periods import PERIODS
from src.config.settings import DEFAULT_SNAPSHOT, BacktestSettings, RebalanceFrequency
from src.data.csv_provider import CsvProvider
from src.profiles.presets import PROFILES
from src.risk import diagnostics as dx

W = pd.Series([0.5, 0.3, 0.2, 0.0], index=["A", "B", "C", "D"])


# ---------------------------------------------------------------------------
# Pure measures, against hand-computed answers
# ---------------------------------------------------------------------------


def test_largest_position():
    assert dx.largest_position(W) == pytest.approx(0.5)
    assert dx.largest_position(np.array([0.25] * 4)) == pytest.approx(0.25)


def test_materially_held_counts_positions_at_or_above_the_threshold():
    assert dx.materially_held(W) == 3          # 0.5, 0.3, 0.2 ; 0.0 excluded
    assert dx.materially_held(W, threshold=0.25) == 2
    assert dx.materially_held(pd.Series([0.05, 0.95])) == 2, "exactly 5% counts"


def test_herfindahl_matches_the_definition():
    assert dx.herfindahl(W) == pytest.approx(0.25 + 0.09 + 0.04)


def test_herfindahl_bounds():
    """1/N when perfectly even, 1.0 when everything sits in one asset."""
    assert dx.herfindahl(np.array([0.25] * 4)) == pytest.approx(0.25)
    assert dx.herfindahl(np.array([1.0, 0.0, 0.0, 0.0])) == pytest.approx(1.0)
    assert dx.herfindahl(np.full(10, 0.1)) == pytest.approx(0.10)


def test_more_concentrated_portfolios_score_higher():
    even = np.array([0.25, 0.25, 0.25, 0.25])
    skewed = np.array([0.70, 0.10, 0.10, 0.10])
    assert dx.herfindahl(skewed) > dx.herfindahl(even)
    assert dx.largest_position(skewed) > dx.largest_position(even)
    assert dx.materially_held(skewed) <= dx.materially_held(even)


# ---------------------------------------------------------------------------
# Allocation distance
# ---------------------------------------------------------------------------


def test_allocation_distance_of_identical_portfolios_is_zero():
    assert dx.allocation_distance(W, W) == pytest.approx(0.0)


def test_allocation_distance_of_disjoint_portfolios_is_one():
    a = pd.Series([1.0, 0.0], index=["A", "B"])
    b = pd.Series([0.0, 1.0], index=["A", "B"])
    assert dx.allocation_distance(a, b) == pytest.approx(1.0)


def test_allocation_distance_is_half_the_absolute_difference():
    a = np.array([0.5, 0.5, 0.0])
    b = np.array([0.3, 0.3, 0.4])
    assert dx.allocation_distance(a, b) == pytest.approx(0.5 * (0.2 + 0.2 + 0.4))


def test_allocation_distance_is_symmetric():
    a, b = np.array([0.6, 0.4]), np.array([0.1, 0.9])
    assert dx.allocation_distance(a, b) == pytest.approx(dx.allocation_distance(b, a))


def test_mismatched_lengths_are_rejected():
    with pytest.raises(ValueError, match="differ in length"):
        dx.allocation_distance(np.array([0.5, 0.5]), np.array([1.0]))


# ---------------------------------------------------------------------------
# Against a real experiment
# ---------------------------------------------------------------------------

pytestmark_snapshot = pytest.mark.skipif(
    not DEFAULT_SNAPSHOT.exists(), reason="snapshot not generated"
)


@pytest.fixture(scope="module")
def experiment():
    if not DEFAULT_SNAPSHOT.exists():
        pytest.skip("snapshot not generated")
    prices = CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)
    return run_diagnostics(prices, PERIODS["a"], DEFAULT_UNIVERSE)


@pytest.fixture
def growth(experiment):
    return experiment[diagnostic_label(PROFILES["growth"])]


@pytest.fixture
def cvar(experiment):
    return experiment[diagnostic_label(PROFILES["downside"])]


def test_all_five_diagnostic_strategies_are_available(experiment):
    options = diagnostic_options()
    assert list(options) == [
        "Equal Weight",
        "Growth — Markowitz",
        "Balanced — Markowitz",
        "Downside Protection — CVaR 95%",
        "Extreme Low Risk — Robust Min-Variance",
    ]
    assert set(experiment.strategy_names) == set(options)


def test_equal_weight_is_the_only_profile_independent_option():
    options = diagnostic_options()
    assert options["Equal Weight"] is None
    assert all(v is not None for k, v in options.items() if k != "Equal Weight")


def test_each_strategy_carries_its_own_profile_constraints(experiment):
    """Growth's Markowitz and Balanced's Markowitz must differ."""
    growth = experiment["Growth — Markowitz"].rebalances[-1].diagnostics
    balanced = experiment["Balanced — Markowitz"].rebalances[-1].diagnostics
    assert growth["risk_aversion"] != balanced["risk_aversion"]
    assert growth["return_target"] != balanced["return_target"]
    assert growth["turnover_limit"] != balanced["turnover_limit"]


def test_all_strategies_share_identical_decision_dates(experiment):
    reference = experiment[next(iter(experiment.strategy_names))].weights_history.index
    for name in experiment.strategy_names:
        pd.testing.assert_index_equal(experiment[name].weights_history.index, reference)


def test_concentration_summary_is_averaged_over_rebalances(growth):
    frame = dx.concentration_by_rebalance(growth)
    summary = dx.concentration_summary(growth)

    assert len(frame) == len(growth.rebalances)
    assert summary["avg_hhi"] == pytest.approx(frame["hhi"].mean())
    assert summary["avg_largest_position"] == pytest.approx(frame["largest_position"].mean())
    assert 0 < summary["avg_hhi"] <= 1


def test_average_allocation_comparison_is_sorted_by_absolute_difference(growth, cvar):
    frame = dx.average_allocation_comparison(growth, cvar)
    magnitudes = frame["difference"].abs().to_numpy()
    assert (np.diff(magnitudes) <= 1e-12).all()
    assert frame["A"].sum() == pytest.approx(1.0, abs=1e-6)
    assert frame["B"].sum() == pytest.approx(1.0, abs=1e-6)
    assert np.allclose(frame["difference"], frame["A"] - frame["B"])


def test_largest_disagreement_finds_the_maximum_distance_date(growth, cvar):
    distances = dx.allocation_distance_series(growth, cvar)
    date, frame = dx.largest_disagreement(growth, cvar)

    assert date == distances.idxmax()
    assert frame["difference"].abs().sum() == pytest.approx(2 * distances.max(), abs=1e-9)
    magnitudes = frame["difference"].abs().to_numpy()
    assert (np.diff(magnitudes) <= 1e-12).all()


def test_allocation_distance_series_covers_every_shared_date(growth, cvar):
    distances = dx.allocation_distance_series(growth, cvar)
    assert len(distances) == len(growth.rebalances)
    assert ((distances >= 0) & (distances <= 1)).all()


def test_weight_path_returns_one_asset_over_time(growth):
    path = dx.weight_path(growth, "SPY")
    assert len(path) == len(growth.rebalances)
    assert ((path >= -1e-9) & (path <= 1 + 1e-9)).all()

    with pytest.raises(KeyError, match="not in this result"):
        dx.weight_path(growth, "NOPE")


# ---------------------------------------------------------------------------
# Turnover binding detection
# ---------------------------------------------------------------------------


def test_turnover_diagnostics_excludes_the_initial_trade(growth):
    diag = dx.turnover_diagnostics(growth, limit=0.5)
    assert diag["n_rebalances"] == len(growth.rebalances) - 1
    series = dx.turnover_by_rebalance(growth)
    assert diag["avg_turnover"] == pytest.approx(series.mean())
    assert diag["max_turnover"] == pytest.approx(series.max())


def test_a_cap_that_never_binds_is_reported_as_zero(growth):
    diag = dx.turnover_diagnostics(growth, limit=10.0)  # far above anything realised
    assert diag["n_binding"] == 0
    assert diag["pct_binding"] == 0.0


def test_a_binding_cap_is_detected():
    """A cap set at the realised maximum must register as binding at least once."""
    from conftest import DISTINCT_ASSET_CLASSES, make_distinct_risk_prices

    from src.portfolio.constraints import ConstraintSet
    from src.portfolio.markowitz import MarkowitzOptimizer

    prices = make_distinct_risk_prices()
    settings = BacktestSettings(
        start=pd.Timestamp("2016-01-01").date(),
        end=pd.Timestamp("2018-12-31").date(),
        lookback_years=1.0,
        rebalance_frequency=RebalanceFrequency.QUARTERLY,
    )
    limit = 0.10
    result = BacktestEngine(prices, settings).run(
        {
            "mv": MarkowitzOptimizer(
                1.0, lookback_days=settings.lookback_days,
                asset_class_map=DISTINCT_ASSET_CLASSES,
                constraints=ConstraintSet(max_weight=0.5, max_turnover=limit),
            )
        }
    )["mv"]

    diag = dx.turnover_diagnostics(result, limit)
    assert diag["n_binding"] > 0
    assert diag["max_turnover"] <= limit + 1e-6
    assert 0 < diag["pct_binding"] <= 1


def test_no_limit_reports_none(growth):
    diag = dx.turnover_diagnostics(growth, limit=None)
    assert diag["limit"] is None
    assert diag["n_binding"] == 0


def test_equal_weight_drift_diagnostic(experiment):
    frame = dx.equal_weight_drift(experiment["Equal Weight"])
    equal = experiment["Equal Weight"]

    assert len(frame) == len(equal.rebalances) - 1
    assert (frame["max_drift"] > 0).all(), "prices move, so weights must drift"
    assert (frame["traded_to_restore"] > 0).all()
    assert frame["most_drifted_asset"].isin(DEFAULT_UNIVERSE.tickers).all()


# ---------------------------------------------------------------------------
# Expected vs realised -- and its inertness
# ---------------------------------------------------------------------------


def test_expected_vs_realised_aligns_each_decision_with_what_followed(growth):
    frame = dx.expected_vs_realised(growth)
    values = growth.portfolio_values

    assert len(frame) == len(growth.rebalances)
    for i, (date, row) in enumerate(frame.iterrows()):
        is_last = i == len(frame) - 1
        end = values.index[-1] if is_last else growth.rebalances[i + 1].as_of
        expected_realised = float(values.loc[end] / values.loc[date] - 1.0)
        assert row["realised_period_return"] == pytest.approx(expected_realised)
        # The realised leg must come from AFTER the decision date, never before.
        assert end > date


def test_expected_return_matches_what_the_optimizer_recorded(growth):
    frame = dx.expected_vs_realised(growth)
    for record, (_, row) in zip(growth.rebalances, frame.iterrows(), strict=True):
        assert row["expected_return"] == pytest.approx(
            record.diagnostics["expected_return"]
        )


def test_equal_weight_has_no_expected_return_but_still_has_realised(experiment):
    frame = dx.expected_vs_realised(experiment["Equal Weight"])
    # Equal weight records an estimate for reporting, but never optimizes on it.
    assert frame["realised_period_return"].notna().all()
    assert len(frame) == len(experiment["Equal Weight"].rebalances)


def test_expectation_accuracy_counts_overshoots(growth):
    frame = dx.expected_vs_realised(growth)
    accuracy = dx.expectation_accuracy(frame)
    usable = frame.dropna(subset=["expected_return", "realised_annualised"])

    assert accuracy["n"] == len(usable)
    manual = int(
        (usable["expected_return"] > usable["realised_annualised"]).sum()
    )
    assert accuracy["n_overshot"] == manual
    assert 0 <= accuracy["pct_overshot"] <= 1


def test_diagnostics_do_not_change_any_portfolio_decision(experiment):
    """The whole module must be inert with respect to the experiment."""
    prices = CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)
    reference = run_diagnostics(prices, PERIODS["a"], DEFAULT_UNIVERSE)

    for name in experiment.strategy_names:
        result = experiment[name]
        # Exercise every diagnostic against the live result.
        dx.concentration_summary(result)
        dx.turnover_diagnostics(result, 0.2)
        dx.expected_vs_realised(result)
        dx.model_diagnostics(result)
        dx.equal_weight_drift(result)

        pd.testing.assert_frame_equal(
            result.weights_history, reference[name].weights_history
        )
        pd.testing.assert_series_equal(
            result.portfolio_values, reference[name].portfolio_values
        )


def test_no_future_return_reaches_a_decision(experiment):
    """Every decision's visible data still ends at or before its own date."""
    for name in experiment.strategy_names:
        for record in experiment[name].rebalances:
            assert record.data_last_date <= record.as_of


def test_diagnostic_decisions_survive_a_poisoned_future():
    """The flagship invariance check, run through the diagnostics experiment."""
    prices = CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)
    reference = run_diagnostics(prices, PERIODS["a"], DEFAULT_UNIVERSE)

    boundary = reference.rebalance_dates[5]
    poisoned = prices.copy()
    poisoned.loc[poisoned.index > boundary] = 424_242.0
    observed = run_diagnostics(poisoned, PERIODS["a"], DEFAULT_UNIVERSE)

    for name in reference.strategy_names:
        pd.testing.assert_frame_equal(
            observed[name].weights_history.loc[:boundary],
            reference[name].weights_history.loc[:boundary],
            obj=f"{name} weights at or before {boundary.date()}",
        )


# ---------------------------------------------------------------------------
# Model-specific diagnostics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "model", "required"),
    [
        ("Growth — Markowitz", "markowitz",
         ["Risk aversion (lambda)", "Estimated expected return",
          "Estimated annualised volatility", "Return shortfall"]),
        ("Downside Protection — CVaR 95%", "cvar",
         ["Confidence level (alpha)", "Estimated 1-day VaR", "Estimated 1-day CVaR",
          "Scenarios used", "Return shortfall"]),
        ("Extreme Low Risk — Robust Min-Variance", "robust",
         ["Covariance scenarios", "Worst-case variance", "Worst-case volatility",
          "Binding scenario index", "Variance spread across scenarios"]),
        ("Equal Weight", "equal_weight",
         ["Target allocation", "Largest pre-rebalance drift",
          "Traded to restore equal weights"]),
    ],
)
def test_model_diagnostics_return_the_expected_fields(experiment, label, model, required):
    diagnostics = dx.model_diagnostics(experiment[label])
    assert diagnostics.model == model
    assert diagnostics.explanation
    for field in required:
        assert field in diagnostics.fields, f"{label} missing {field}"


def test_robust_diagnostics_report_a_valid_binding_scenario(experiment):
    fields = dx.model_diagnostics(
        experiment["Extreme Low Risk — Robust Min-Variance"]
    ).fields
    assert fields["Covariance scenarios"] == 6
    assert 0 <= fields["Binding scenario index"] < 6
    assert fields["Worst-case volatility"] == pytest.approx(
        np.sqrt(fields["Worst-case variance"])
    )
    assert fields["Variance spread across scenarios"] >= 0


def test_cvar_diagnostics_keep_cvar_at_least_var(experiment):
    fields = dx.model_diagnostics(experiment["Downside Protection — CVaR 95%"]).fields
    assert fields["Estimated 1-day CVaR"] >= fields["Estimated 1-day VaR"] - 1e-12
    assert fields["Confidence level (alpha)"] == 0.95


def test_model_diagnostics_can_target_any_rebalance(growth):
    first = dx.model_diagnostics(growth, index=0)
    last = dx.model_diagnostics(growth, index=-1)
    assert first.model == last.model == "markowitz"
    assert first.fields["Turnover this rebalance"] != last.fields["Turnover this rebalance"]


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------


def test_interpretation_statements_are_produced(growth, cvar):
    statements = dx.interpretation_statements(
        "Growth — Markowitz", growth, "Downside Protection — CVaR 95%", cvar, 0.50, 0.15
    )
    assert statements
    assert all(isinstance(s, str) and s for s in statements)


def test_interpretation_avoids_unsupported_causal_claims(growth, cvar):
    """The text must describe, never rank or diagnose motive."""
    text = " ".join(
        dx.interpretation_statements(
            "Growth — Markowitz", growth, "Downside Protection — CVaR 95%", cvar,
            0.50, 0.15,
        )
    ).lower()

    for forbidden in ("overfit", "is better", "is worse", "chased", "superior",
                      "outperform", "should", "winner", "best"):
        assert forbidden not in text, f"unsupported claim {forbidden!r} in interpretation"


def test_interpretation_reports_a_non_binding_cap_as_non_binding(growth, cvar):
    text = " ".join(
        dx.interpretation_statements(
            "A", growth, "B", cvar, limit_a=10.0, limit_b=10.0
        )
    )
    assert "never bound" in text


def test_interpretation_hedges_the_one_interpretive_claim(growth, cvar):
    """The only non-restatement must be explicitly hedged."""
    statements = dx.interpretation_statements("A", growth, "B", cvar, 0.5, 0.15)
    for statement in statements:
        if "consistent with" in statement:
            assert "cannot establish" in statement


def test_identical_strategies_produce_no_difference_claims(growth):
    statements = dx.interpretation_statements("A", growth, "B", growth, 0.5, 0.5)
    text = " ".join(statements)
    assert "more concentrated" not in text
    assert "differed most" in text  # distance is defined, and is zero
