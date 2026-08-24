"""Tests for the covariance uncertainty set used by robust optimization."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config.settings import TRADING_DAYS_PER_YEAR
from src.data.window import MarketDataView
from src.estimation.covariance import ledoit_wolf_covariance
from src.estimation.covariance_scenarios import (
    DEFAULT_N_SUBWINDOWS,
    DEFAULT_STRIDE,
    DEFAULT_WINDOW_LENGTH,
    CovarianceScenario,
    CovarianceScenarioError,
    InsufficientCovarianceScenariosError,
    RollingWindowUncertaintySet,
    validate_covariance_scenario,
)

LOOKBACK = 756


@pytest.fixture
def long_view(risk_prices) -> MarketDataView:
    """A view with enough history for the full default 756-observation lookback."""
    return MarketDataView(risk_prices, risk_prices.index[1900])


# ---------------------------------------------------------------------------
# Default construction
# ---------------------------------------------------------------------------


def test_default_set_has_five_subwindows_plus_the_full_window(long_view):
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)

    assert scenarios.n_scenarios == 6
    assert scenarios.window_length == DEFAULT_WINDOW_LENGTH == 252
    assert scenarios.stride == DEFAULT_STRIDE == 126
    assert DEFAULT_N_SUBWINDOWS == 5

    labels = scenarios.labels
    assert labels[:5] == [
        "sub0[0:252]", "sub1[126:378]", "sub2[252:504]",
        "sub3[378:630]", "sub4[504:756]",
    ]
    assert labels[5] == "full[0:756]"


def test_subwindows_have_the_configured_length_and_stride(long_view):
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)
    window = long_view.returns(LOOKBACK)

    for i, scenario in enumerate(scenarios.scenarios[:5]):
        assert scenario.n_observations == 252
        assert scenario.window_start == window.index[i * 126]
        assert scenario.window_end == window.index[i * 126 + 251]

    assert scenarios.scenarios[5].n_observations == 756


def test_the_last_subwindow_ends_at_the_decision_date(long_view):
    """Offsets 0..504 with length 252 tile the window exactly."""
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)
    assert scenarios.scenarios[4].window_end == long_view.as_of
    assert scenarios.scenarios[5].window_end == long_view.as_of


def test_scenarios_use_the_validated_estimator_and_annualisation(long_view):
    """The full-window scenario must equal the Phase 2 covariance exactly."""
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)
    expected, expected_shrinkage = ledoit_wolf_covariance(long_view, LOOKBACK)

    full = scenarios.scenarios[5]
    assert np.allclose(full.matrix, expected.to_numpy())
    assert full.shrinkage == pytest.approx(expected_shrinkage)


def test_scenarios_are_annualised(long_view):
    """Each scenario is the daily estimate scaled by exactly 252.

    Compared against the *unannualised* Ledoit-Wolf estimate of the same block
    rather than against a raw sample variance: shrinkage legitimately moves an
    individual diagonal entry a long way when asset variances are heterogeneous,
    so a sample-variance comparison would test shrinkage, not annualisation.
    """
    from src.estimation.covariance import ledoit_wolf_from_returns

    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)
    block = long_view.returns(LOOKBACK).iloc[:252]
    daily, _ = ledoit_wolf_from_returns(block, annualize=False)

    assert np.allclose(
        scenarios.scenarios[0].matrix, daily.to_numpy() * TRADING_DAYS_PER_YEAR
    )


def test_scenarios_share_the_ticker_order(long_view):
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)
    for scenario in scenarios.scenarios:
        assert scenario.tickers == scenarios.tickers == long_view.tickers


def test_configuration_is_recorded_in_the_summary(long_view):
    summary = RollingWindowUncertaintySet().build(long_view, LOOKBACK).summary()
    assert summary["n_covariance_scenarios"] == 6
    assert summary["covariance_window_length"] == 252
    assert summary["covariance_window_stride"] == 126
    assert summary["covariance_method"] == "rolling_subwindows"
    assert len(summary["covariance_scenario_labels"]) == 6


def test_count_length_and_stride_are_configurable(long_view):
    builder = RollingWindowUncertaintySet(
        window_length=150, stride=100, n_subwindows=3, include_full_window=False
    )
    scenarios = builder.build(long_view, LOOKBACK)
    assert scenarios.n_scenarios == 3
    assert all(s.n_observations == 150 for s in scenarios.scenarios)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_every_scenario_is_finite_symmetric_and_psd(long_view):
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)
    for scenario in scenarios.scenarios:
        matrix = scenario.matrix
        assert np.all(np.isfinite(matrix))
        assert np.abs(matrix - matrix.T).max() < 1e-10
        assert np.linalg.eigvalsh(matrix).min() >= -1e-10


def test_an_asymmetric_matrix_is_rejected(long_view):
    bad = CovarianceScenario(
        matrix=np.array([[1.0, 0.5], [0.2, 1.0]]),
        tickers=["A", "B"], label="bad", n_observations=252,
        window_start=pd.Timestamp("2015-01-01"), window_end=pd.Timestamp("2015-12-31"),
        shrinkage=0.1,
    )
    with pytest.raises(CovarianceScenarioError, match="not symmetric"):
        validate_covariance_scenario(bad, ["A", "B"], pd.Timestamp("2016-01-04"))


def test_a_non_psd_matrix_is_rejected():
    bad = CovarianceScenario(
        matrix=np.array([[1.0, 2.0], [2.0, 1.0]]),  # eigenvalues -1, 3
        tickers=["A", "B"], label="bad", n_observations=252,
        window_start=pd.Timestamp("2015-01-01"), window_end=pd.Timestamp("2015-12-31"),
        shrinkage=0.1,
    )
    with pytest.raises(CovarianceScenarioError, match="not positive semidefinite"):
        validate_covariance_scenario(bad, ["A", "B"], pd.Timestamp("2016-01-04"))


def test_a_non_finite_matrix_is_rejected():
    bad = CovarianceScenario(
        matrix=np.array([[1.0, np.nan], [np.nan, 1.0]]),
        tickers=["A", "B"], label="bad", n_observations=252,
        window_start=pd.Timestamp("2015-01-01"), window_end=pd.Timestamp("2015-12-31"),
        shrinkage=0.1,
    )
    with pytest.raises(CovarianceScenarioError, match="non-finite"):
        validate_covariance_scenario(bad, ["A", "B"], pd.Timestamp("2016-01-04"))


def test_a_scenario_crossing_the_decision_date_is_rejected():
    bad = CovarianceScenario(
        matrix=np.eye(2), tickers=["A", "B"], label="bad", n_observations=252,
        window_start=pd.Timestamp("2015-01-01"), window_end=pd.Timestamp("2016-06-01"),
        shrinkage=0.1,
    )
    with pytest.raises(CovarianceScenarioError, match="after the decision date"):
        validate_covariance_scenario(bad, ["A", "B"], pd.Timestamp("2016-01-04"))


def test_a_scenario_with_too_few_observations_is_rejected():
    bad = CovarianceScenario(
        matrix=np.eye(2), tickers=["A", "B"], label="bad", n_observations=30,
        window_start=pd.Timestamp("2015-11-01"), window_end=pd.Timestamp("2015-12-31"),
        shrinkage=0.1,
    )
    with pytest.raises(CovarianceScenarioError, match="below the minimum"):
        validate_covariance_scenario(bad, ["A", "B"], pd.Timestamp("2016-01-04"))


def test_mismatched_tickers_are_rejected():
    bad = CovarianceScenario(
        matrix=np.eye(2), tickers=["A", "B"], label="bad", n_observations=252,
        window_start=pd.Timestamp("2015-01-01"), window_end=pd.Timestamp("2015-12-31"),
        shrinkage=0.1,
    )
    with pytest.raises(CovarianceScenarioError, match="expected"):
        validate_covariance_scenario(bad, ["B", "A"], pd.Timestamp("2016-01-04"))


def test_the_covariance_guard_is_separate_from_the_cvar_guard():
    """The two guards measure different things and must not be conflated."""
    from src.estimation.covariance_scenarios import MIN_OBSERVATIONS_PER_SCENARIO
    from src.estimation.scenarios import MIN_SCENARIOS

    assert MIN_OBSERVATIONS_PER_SCENARIO != MIN_SCENARIOS
    # One counts observations behind each matrix; the other counts tail points.
    assert MIN_OBSERVATIONS_PER_SCENARIO >= 120


def test_a_lookback_too_short_for_the_configuration_fails_explicitly(long_view):
    """Never silently shrink the uncertainty set."""
    with pytest.raises(InsufficientCovarianceScenariosError, match="span"):
        RollingWindowUncertaintySet().build(long_view, 300)


def test_requiring_more_scenarios_than_configured_fails(long_view):
    builder = RollingWindowUncertaintySet(n_subwindows=2, required_scenarios=6)
    with pytest.raises(InsufficientCovarianceScenariosError, match="required"):
        builder.build(long_view, LOOKBACK)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"window_length": 1}, "window_length"),
        ({"stride": 0}, "stride"),
        ({"n_subwindows": 0}, "n_subwindows"),
    ],
)
def test_invalid_configuration_is_rejected(kwargs, match):
    with pytest.raises(ValueError, match=match):
        RollingWindowUncertaintySet(**kwargs)


# ---------------------------------------------------------------------------
# Variance arithmetic
# ---------------------------------------------------------------------------


def test_variances_match_matrix_algebra(long_view):
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)
    weights = np.array([0.4, 0.3, 0.2, 0.1])

    variances = scenarios.variances(weights)
    for i, scenario in enumerate(scenarios.scenarios):
        assert variances[i] == pytest.approx(weights @ scenario.matrix @ weights)


def test_worst_case_is_the_maximum_over_scenarios(long_view):
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)
    weights = pd.Series(0.25, index=scenarios.tickers)

    variances = scenarios.variances(weights)
    assert scenarios.worst_case_variance(weights) == pytest.approx(variances.max())
    assert scenarios.worst_case_index(weights) == int(np.argmax(variances))


def test_wrong_weight_length_is_rejected(long_view):
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)
    with pytest.raises(ValueError, match="expected 4 weights"):
        scenarios.variances(np.array([0.5, 0.5]))


# ---------------------------------------------------------------------------
# Look-ahead protection
# ---------------------------------------------------------------------------


def test_no_scenario_crosses_the_decision_boundary(long_view):
    scenarios = RollingWindowUncertaintySet().build(long_view, LOOKBACK)
    for scenario in scenarios.scenarios:
        assert scenario.window_end <= long_view.as_of
        assert scenario.window_start <= scenario.window_end


def test_scenarios_are_unchanged_when_the_future_is_poisoned(risk_prices):
    as_of = risk_prices.index[1900]
    builder = RollingWindowUncertaintySet()

    clean = builder.build(MarketDataView(risk_prices, as_of), LOOKBACK)

    poisoned_panel = risk_prices.copy()
    poisoned_panel.loc[poisoned_panel.index > as_of] = 252_525.0
    poisoned = builder.build(MarketDataView(poisoned_panel, as_of), LOOKBACK)

    assert poisoned.labels == clean.labels
    for a, b in zip(poisoned.scenarios, clean.scenarios, strict=True):
        assert np.array_equal(a.matrix, b.matrix)
        assert a.window_start == b.window_start and a.window_end == b.window_end


def test_scenarios_are_unchanged_when_the_future_is_deleted(risk_prices):
    as_of = risk_prices.index[1900]
    builder = RollingWindowUncertaintySet()

    full = builder.build(MarketDataView(risk_prices, as_of), LOOKBACK)
    truncated = builder.build(
        MarketDataView(risk_prices.loc[risk_prices.index <= as_of], as_of), LOOKBACK
    )
    for a, b in zip(truncated.scenarios, full.scenarios, strict=True):
        assert np.array_equal(a.matrix, b.matrix)


def test_builder_accepts_only_a_view_not_a_panel(risk_prices):
    with pytest.raises(AttributeError):
        RollingWindowUncertaintySet().build(risk_prices, LOOKBACK)  # type: ignore[arg-type]
