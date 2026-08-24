"""Covariance estimation.

The project uses **one** covariance estimator for the main experiment:
Ledoit-Wolf shrinkage of the sample covariance toward a scaled identity target.

Why shrinkage rather than the plain sample covariance: with roughly 750 daily
observations and ten assets the sample estimate is usable, but it can be
ill-conditioned, and a near-singular :math:`\\Sigma` makes a quadratic objective
numerically fragile.  Ledoit-Wolf is guaranteed positive definite and well
conditioned, and its shrinkage intensity is chosen analytically from the data
rather than tuned -- so nothing about it is fitted to the evaluation period.

Estimators take a :class:`~src.data.window.MarketDataView`, never a price panel.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

from src.config.settings import TRADING_DAYS_PER_YEAR
from src.data.window import MarketDataView

logger = logging.getLogger(__name__)

ESTIMATOR_NAME = "ledoit_wolf"

MIN_EIGENVALUE = 1e-12
"""Floor applied when repairing a non-PSD matrix."""


def ledoit_wolf_covariance(
    view: MarketDataView,
    lookback_days: int,
    annualize: bool = True,
) -> tuple[pd.DataFrame, float]:
    r"""Annualised Ledoit-Wolf shrunk covariance.

    .. math::
        \hat\Sigma = (1 - \delta)\, S + \delta\, F,
        \qquad F = \frac{\operatorname{tr}(S)}{N} I

    where :math:`S` is the sample covariance, :math:`F` the scaled-identity
    shrinkage target, and :math:`\delta \in [0, 1]` the shrinkage intensity
    chosen analytically by the Ledoit-Wolf rule.

    Annualisation multiplies by 252, matching the expected-return convention.

    Returns
    -------
    (covariance, shrinkage)
        The annualised covariance matrix and the shrinkage intensity actually
        used. The intensity is recorded so it can be reported in diagnostics --
        a high value at a given date signals that the sample estimate was
        unreliable there.
    """
    if lookback_days < 2:
        raise ValueError(f"lookback_days must be at least 2, got {lookback_days}")

    returns = view.returns(lookback_days)
    n_obs, n_assets = returns.shape
    if n_obs <= n_assets:
        logger.warning(
            "Covariance at %s estimated from %d observations for %d assets; "
            "shrinkage is carrying most of the estimate.",
            view.as_of.date(), n_obs, n_assets,
        )

    estimator = LedoitWolf(assume_centered=False).fit(returns.to_numpy())
    matrix = np.asarray(estimator.covariance_, dtype="float64")
    shrinkage = float(estimator.shrinkage_)

    matrix = ensure_positive_semidefinite(matrix, context=f"{view.as_of.date()}")
    if annualize:
        matrix = matrix * TRADING_DAYS_PER_YEAR

    covariance = pd.DataFrame(matrix, index=returns.columns, columns=returns.columns)
    return covariance, shrinkage


def ensure_positive_semidefinite(
    matrix: np.ndarray,
    context: str = "",
    min_eigenvalue: float = MIN_EIGENVALUE,
) -> np.ndarray:
    """Return the nearest PSD matrix by clipping negative eigenvalues.

    Ledoit-Wolf output is PSD by construction, so this should never activate in
    normal operation -- but a silently indefinite covariance would make a
    quadratic program meaningless rather than merely inaccurate, so the check is
    explicit and logs loudly when it fires.
    """
    symmetric = 0.5 * (matrix + matrix.T)
    eigenvalues = np.linalg.eigvalsh(symmetric)

    if eigenvalues.min() >= 0.0:
        return symmetric

    logger.warning(
        "Covariance matrix %s was not positive semidefinite (min eigenvalue %.3e); "
        "repairing by eigenvalue clipping.",
        context, eigenvalues.min(),
    )
    values, vectors = np.linalg.eigh(symmetric)
    repaired = vectors @ np.diag(np.clip(values, min_eigenvalue, None)) @ vectors.T
    return 0.5 * (repaired + repaired.T)
