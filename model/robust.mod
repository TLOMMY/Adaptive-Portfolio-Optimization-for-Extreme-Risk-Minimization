# ---------------------------------------------------------------------------
# Robust mean-variance model (ellipsoidal uncertainty in mu).  Requires common.mod.
#
# The expected-return estimate mu is uncertain; the true mean is assumed to lie
# in the ellipsoid { m : (m - mu)' Omega^-1 (m - mu) <= kappa^2 } where Omega
# is the covariance of the estimation error (Sigma / nS).  Maximising the
# worst case over that set gives  mu'w - kappa * sqrt(w' Omega w), which is
# modelled with the cone variable t >= sqrt(w' Omega w).  Same variance cap as
# Markowitz.  MISOCP; solved by Gurobi.
# ---------------------------------------------------------------------------

param Sigma {ASSETS, ASSETS};     # daily return covariance in percent^2
param Omega {ASSETS, ASSETS};     # covariance of the mean estimate (Sigma / n), percent^2
param kappa >= 0;                 # size of the uncertainty set (in standard errors)
param sigma_scale > 0 default 100;  # Omega is in percent^2 so t is in percent; mu is a fraction
param var_limit >= 0;

var t >= 0;                       # >= sqrt(w' Omega w)
var variance = sum {i in ASSETS, j in ASSETS} w[i] * Sigma[i,j] * w[j];
var worst_return = exp_return - kappa * t / sigma_scale;

maximize objective:
    hold_days * worst_return - lambda_risk * variance - cost_rate * turnover;

subject to cone:              sum {i in ASSETS, j in ASSETS} w[i] * Omega[i,j] * w[j] <= t * t;
subject to risk_tolerance:    variance <= var_limit;
