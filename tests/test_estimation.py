"""Tests for the shared estimation layer.

Estimates are checked against hand-computed values from the same window, and
against the invariant that matters most: an estimator can only ever see what its
``MarketDataView`` exposes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config.settings import TRADING_DAYS_PER_YEAR
from src.data.window import MarketDataView
from src.estimation.covariance import (
    ensure_positive_semidefinite,
    ledoit_wolf_covariance,
)
from src.estimation.expected_returns import sample_mean_returns
from src.estimation.parameters import estimate_parameters

LOOKBACK = 500


# ---------------------------------------------------------------------------
# Expected returns
# ---------------------------------------------------------------------------


def test_sample_mean_matches_a_hand_computed_value(risk_view):
    mu = sample_mean_returns(risk_view, LOOKBACK)
    window = risk_view.returns(LOOKBACK)

    expected = window["BOND"].mean() * TRADING_DAYS_PER_YEAR
    assert mu["BOND"] == pytest.approx(expected)


def test_sample_mean_annualisation_is_arithmetic(risk_view):
    daily = sample_mean_returns(risk_view, LOOKBACK, annualize=False)
    annual = sample_mean_returns(risk_view, LOOKBACK, annualize=True)
    assert np.allclose(annual.to_numpy(), daily.to_numpy() * TRADING_DAYS_PER_YEAR)


def test_sample_mean_covers_every_asset(risk_view):
    mu = sample_mean_returns(risk_view, LOOKBACK)
    assert list(mu.index) == risk_view.tickers
    assert not mu.isna().any()


def test_sample_mean_rejects_a_degenerate_lookback(risk_view):
    with pytest.raises(ValueError, match="at least 2"):
        sample_mean_returns(risk_view, 1)


# ---------------------------------------------------------------------------
# Covariance
# ---------------------------------------------------------------------------


def test_covariance_is_symmetric_and_positive_semidefinite(risk_view):
    sigma, _ = ledoit_wolf_covariance(risk_view, LOOKBACK)
    matrix = sigma.to_numpy()

    assert np.allclose(matrix, matrix.T)
    assert np.linalg.eigvalsh(matrix).min() > 0


def test_covariance_shrinkage_is_a_valid_intensity(risk_view):
    _, shrinkage = ledoit_wolf_covariance(risk_view, LOOKBACK)
    assert 0.0 <= shrinkage <= 1.0


def test_covariance_annualisation_scales_by_the_trading_year(risk_view):
    daily, _ = ledoit_wolf_covariance(risk_view, LOOKBACK, annualize=False)
    annual, _ = ledoit_wolf_covariance(risk_view, LOOKBACK, annualize=True)
    assert np.allclose(annual.to_numpy(), daily.to_numpy() * TRADING_DAYS_PER_YEAR)


def test_covariance_diagonal_tracks_asset_volatility(risk_view):
    """The fixture's assets have deliberately separated volatilities."""
    sigma, _ = ledoit_wolf_covariance(risk_view, LOOKBACK)
    vols = np.sqrt(np.diag(sigma.to_numpy()))
    order = pd.Series(vols, index=sigma.index).sort_values()
    assert list(order.index) == ["SAFE", "BOND", "STOCK", "WILD"]


def test_covariance_is_labelled_by_ticker(risk_view):
    sigma, _ = ledoit_wolf_covariance(risk_view, LOOKBACK)
    assert list(sigma.index) == risk_view.tickers
    assert list(sigma.columns) == risk_view.tickers


def test_psd_repair_leaves_a_valid_matrix_untouched():
    matrix = np.array([[4.0, 1.0], [1.0, 3.0]])
    repaired = ensure_positive_semidefinite(matrix)
    assert np.allclose(repaired, matrix)


def test_psd_repair_fixes_an_indefinite_matrix():
    indefinite = np.array([[1.0, 2.0], [2.0, 1.0]])  # eigenvalues -1 and 3
    assert np.linalg.eigvalsh(indefinite).min() < 0

    repaired = ensure_positive_semidefinite(indefinite)
    assert np.linalg.eigvalsh(repaired).min() >= -1e-15
    assert np.allclose(repaired, repaired.T)


# ---------------------------------------------------------------------------
# Combined parameters
# ---------------------------------------------------------------------------


def test_parameters_report_the_window_they_used(risk_view):
    params = estimate_parameters(risk_view, LOOKBACK)
    assert params.n_observations == LOOKBACK
    assert params.as_of == risk_view.as_of
    assert params.window_end <= risk_view.as_of
    assert params.window_start < params.window_end


def test_parameters_never_see_past_the_decision_date(risk_prices):
    """The estimation layer's boundary guarantee, stated directly."""
    as_of = risk_prices.index[1500]
    view = MarketDataView(risk_prices, as_of)
    params = estimate_parameters(view, LOOKBACK)
    assert params.window_end <= as_of


def test_parameters_are_unchanged_when_the_future_is_poisoned(risk_prices):
    as_of = risk_prices.index[1500]
    clean = estimate_parameters(MarketDataView(risk_prices, as_of), LOOKBACK)

    poisoned_panel = risk_prices.copy()
    poisoned_panel.loc[poisoned_panel.index > as_of] = 555_555.0
    poisoned = estimate_parameters(MarketDataView(poisoned_panel, as_of), LOOKBACK)

    pd.testing.assert_series_equal(poisoned.expected_returns, clean.expected_returns)
    pd.testing.assert_frame_equal(poisoned.covariance, clean.covariance)


def test_portfolio_moments_match_matrix_algebra(risk_view):
    params = estimate_parameters(risk_view, LOOKBACK)
    weights = pd.Series([0.4, 0.3, 0.2, 0.1], index=params.tickers)
    w = weights.to_numpy()

    assert params.portfolio_return(weights) == pytest.approx(params.mu @ w)
    assert params.portfolio_variance(weights) == pytest.approx(w @ params.sigma @ w)
    assert params.portfolio_volatility(weights) == pytest.approx(
        np.sqrt(w @ params.sigma @ w)
    )


def test_portfolio_moments_accept_an_array(risk_view):
    params = estimate_parameters(risk_view, LOOKBACK)
    array = np.array([0.25, 0.25, 0.25, 0.25])
    series = pd.Series(array, index=params.tickers)
    assert params.portfolio_return(array) == pytest.approx(params.portfolio_return(series))


def test_volatilities_are_the_covariance_diagonal(risk_view):
    params = estimate_parameters(risk_view, LOOKBACK)
    assert np.allclose(params.volatilities.to_numpy(), np.sqrt(np.diag(params.sigma)))


def test_summary_records_which_estimators_were_used(risk_view):
    summary = estimate_parameters(risk_view, LOOKBACK).summary()
    assert summary["mu_estimator"] == "sample_mean"
    assert summary["covariance_estimator"] == "ledoit_wolf"
    assert summary["n_observations"] == LOOKBACK
    assert 0.0 <= summary["shrinkage"] <= 1.0


def test_mu_and_sigma_share_the_ticker_order(risk_view):
    params = estimate_parameters(risk_view, LOOKBACK)
    assert list(params.expected_returns.index) == params.tickers
    assert list(params.covariance.index) == params.tickers
    assert params.mu.shape == (len(params.tickers),)
    assert params.sigma.shape == (len(params.tickers), len(params.tickers))
