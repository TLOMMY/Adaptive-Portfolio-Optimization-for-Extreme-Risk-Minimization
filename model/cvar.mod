# ---------------------------------------------------------------------------
# CVaR-constrained model (the project's own).  Requires common.mod.
#
# Risk is the average loss on the worst (1-alpha) share of historical days,
# linearised with the Rockafellar-Uryasev threshold trick, and capped by the
# investor's (time-varying) cvar_limit.  Solvable by HiGHS as a MILP.
# ---------------------------------------------------------------------------

set SCENARIOS;                    # historical days used as samples of the future
param r  {SCENARIOS, ASSETS};     # realised daily return in each scenario
param nS := card(SCENARIOS);

param alpha       >= 0.5, < 1;    # CVaR confidence level, e.g. 0.95
param cvar_limit  >= 0;           # max average daily loss in the worst (1-alpha) of days

var zeta;                         # the VaR threshold
var u {SCENARIOS} >= 0;           # loss beyond zeta in each scenario
var cvar = zeta + sum {s in SCENARIOS} u[s] / ((1 - alpha) * nS);

maximize objective:
    hold_days * exp_return - lambda_risk * cvar - cost_rate * turnover;

subject to tail_loss {s in SCENARIOS}:
    u[s] >= -sum {a in ASSETS} r[s,a] * w[a] - zeta;
subject to loss_tolerance:    cvar <= cvar_limit;
