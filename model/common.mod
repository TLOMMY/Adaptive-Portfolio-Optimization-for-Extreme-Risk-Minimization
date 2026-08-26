# ---------------------------------------------------------------------------
# Shared part of every optimising model: the investor's rules.
#
# Loaded first; then one of cvar.mod / markowitz.mod / robust.mod adds its
# own risk measure and objective.  Everything here is linear except the
# binary "do I hold it" variables.
# ---------------------------------------------------------------------------

set ASSETS;                       # everything the portfolio may hold, incl. CASH
set SECTORS;
param sector {ASSETS} symbolic in SECTORS;
param is_cash {ASSETS} binary default 0;

# --- market estimate -------------------------------------------------------
param mu {ASSETS};                # expected daily return (after shrinkage)

# --- investor profile ------------------------------------------------------
param lambda_risk >= 0 default 0; # optional extra risk penalty in the objective
param w_max  {ASSETS} >= 0, <= 1; # per-asset cap (concentration, exclusions)
param w_min_pos >= 0, <= 1;       # if held, hold at least this much (no dust)
param max_holdings integer >= 1;  # cardinality cap over non-cash assets (max number of unique assets we can hold)
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

var exp_return = sum {a in ASSETS} mu[a] * w[a];
var turnover   = sum {a in ASSETS} (buy[a] + sell[a]);

subject to budget:            sum {a in ASSETS} w[a] = 1;
subject to trade_balance {a in ASSETS}:  w[a] = w_prev[a] + buy[a] - sell[a];

# minimum and max position (cash is always allowed)
subject to link_upper {a in ASSETS: is_cash[a] = 0}:  w[a] <= w_max[a] * z[a];
subject to link_lower {a in ASSETS: is_cash[a] = 0}:  w[a] >= w_min_pos * z[a];

# enforce we don't go beyond max num of unique assets (cardinality)
subject to cardinality:       sum {a in ASSETS: is_cash[a] = 0} z[a] <= max_holdings;

subject to sector_limit {k in SECTORS}:
    sum {a in ASSETS: sector[a] = k} w[a] <= sector_cap[k];
subject to cash_floor:        sum {a in ASSETS: is_cash[a] = 1} w[a] >= cash_min;
