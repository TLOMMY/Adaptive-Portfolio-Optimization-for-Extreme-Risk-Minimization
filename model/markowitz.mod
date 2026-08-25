# ---------------------------------------------------------------------------
# Markowitz mean-variance model.  Requires common.mod.
#
# Risk is the portfolio variance w' Sigma w, capped at var_limit (the
# investor's CVaR limit translated to a variance under a normal assumption).
# The quadratic constraint plus the binaries make this a MIQCP; solved by
# Gurobi.
# ---------------------------------------------------------------------------

param Sigma {ASSETS, ASSETS};     # daily return covariance in percent^2 (sample or Ledoit-Wolf)
param var_limit >= 0;             # max daily variance, percent^2

var variance = sum {i in ASSETS, j in ASSETS} w[i] * Sigma[i,j] * w[j];

maximize objective:
    hold_days * exp_return - lambda_risk * variance - cost_rate * turnover;

subject to risk_tolerance:    variance <= var_limit;
