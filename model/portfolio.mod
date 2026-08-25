# ---------------------------------------------------------------------------
# Profile-driven CVaR portfolio model (single rebalance decision).
#
# Solved once per rebalance date.  All inputs come from data strictly before
# that date.  Linear except for the binary "do I hold it" variables, so the
# whole thing is a MILP that HiGHS solves in well under a second.
# ---------------------------------------------------------------------------

set ASSETS;                       # everything the portfolio may hold, incl. CASH
set SCENARIOS;                    # historical days used as samples of the future
set SECTORS;
param sector {ASSETS} symbolic in SECTORS;
param is_cash {ASSETS} binary default 0;

# --- market estimates ------------------------------------------------------
param mu {ASSETS};                # expected daily return (after shrinkage)
param r  {SCENARIOS, ASSETS};     # realised daily return in each scenario
param nS := card(SCENARIOS);

# --- investor profile ------------------------------------------------------
param alpha       >= 0.5, < 1;    # CVaR confidence level, e.g. 0.95
param cvar_limit  >= 0;           # max average daily loss in the worst (1-alpha) of days
param lambda_risk >= 0 default 0; # optional extra CVaR penalty in the objective
param w_max  {ASSETS} >= 0, <= 1; # per-asset cap (concentration and liquidity)
param w_min_pos >= 0, <= 1;       # if held, hold at least this much (no dust)
param max_holdings integer >= 1;  # cardinality cap over non-cash assets
param sector_cap {SECTORS} >= 0, <= 1;
param cash_min >= 0, <= 1 default 0;

# --- trading ---------------------------------------------------------------
param w_prev {ASSETS} >= 0 default 0;   # weights held going into this decision
param cost_rate >= 0 default 0.001;     # proportional cost per unit traded (10 bp)
param hold_days >= 1 default 21;        # expected days until the next rebalance

# --- decision variables ----------------------------------------------------
var w    {a in ASSETS} >= 0, <= w_max[a];
var z    {ASSETS} binary;               # 1 if asset is held
var buy  {ASSETS} >= 0;
var sell {ASSETS} >= 0;
var zeta;                               # the VaR threshold (Rockafellar-Uryasev)
var u    {SCENARIOS} >= 0;              # loss beyond zeta in each scenario

var cvar = zeta + sum {s in SCENARIOS} u[s] / ((1 - alpha) * nS);
var exp_return = sum {a in ASSETS} mu[a] * w[a];
var turnover   = sum {a in ASSETS} (buy[a] + sell[a]);

maximize objective:
    hold_days * exp_return - lambda_risk * cvar - cost_rate * turnover;

subject to budget:            sum {a in ASSETS} w[a] = 1;
subject to trade_balance {a in ASSETS}:  w[a] = w_prev[a] + buy[a] - sell[a];

# CVaR: u[s] must cover the portfolio loss in scenario s beyond the threshold
subject to tail_loss {s in SCENARIOS}:
    u[s] >= -sum {a in ASSETS} r[s,a] * w[a] - zeta;
subject to loss_tolerance:    cvar <= cvar_limit;

# cardinality and minimum position (cash is always allowed)
subject to link_upper {a in ASSETS: is_cash[a] = 0}:  w[a] <= w_max[a] * z[a];
subject to link_lower {a in ASSETS: is_cash[a] = 0}:  w[a] >= w_min_pos * z[a];
subject to cardinality:       sum {a in ASSETS: is_cash[a] = 0} z[a] <= max_holdings;

subject to sector_limit {k in SECTORS}:
    sum {a in ASSETS: sector[a] = k} w[a] <= sector_cap[k];
subject to cash_floor:        sum {a in ASSETS: is_cash[a] = 1} w[a] >= cash_min;
