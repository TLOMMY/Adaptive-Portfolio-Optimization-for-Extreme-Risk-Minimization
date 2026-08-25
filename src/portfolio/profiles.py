"""Investor archetypes and the mapping from human factors to model parameters.

A Profile holds what a person would tell an adviser.  `params_at(years_left)`
turns that into the numbers the AMPL model needs on a given rebalance date.
The only time-varying piece is the loss limit, which follows a linear glide
path from `cvar_start` (full horizon) to `cvar_end` (horizon exhausted).

Loss limits are *daily* CVaR at 95%: the average loss on the worst 5% of
days.  For intuition, a daily CVaR of 2% corresponds roughly to a portfolio
that loses 8-10% in a bad month.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_SECTOR_CAP = 0.30


@dataclass(frozen=True)
class Profile:
    key: str
    name: str
    tagline: str
    horizon_years: float
    cvar_start: float             # daily CVaR limit with the full horizon ahead
    cvar_end: float               # daily CVaR limit at the end of the horizon
    max_holdings: int
    w_max: float                  # concentration cap per asset
    cash_min: float               # liquidity: minimum cash weight
    sector_cap: dict[str, float] = field(default_factory=dict)
    exclude: tuple[str, ...] = ()    # tickers this investor refuses to hold
    w_min_pos: float = 0.02
    cost_rate: float = 0.001
    alpha: float = 0.95
    lambda_risk: float = 0.0
    hold_days: int = 21
    lookback_days: int = 756
    shrink: float = 0.75           # tuned on 2011-2015, see tune.py
    # rebalance triggers (see backtest.py)
    drift_trigger: float = 0.10   # total |w - target| that forces a re-solve
    vol_trigger: float = 2.0      # tuned on 2011-2015; ratio of short-run to long-run vol that forces a re-solve
    max_days_between: int = 63    # a re-solve at least this often (one quarter)
    min_days_between: int = 10    # cooldown so a crash does not trigger daily re-solves

    def cvar_limit(self, years_left: float) -> float:
        frac = min(max(years_left / self.horizon_years, 0.0), 1.0)
        return self.cvar_end + frac * (self.cvar_start - self.cvar_end)

    def params_at(self, years_left: float) -> dict:
        return dict(
            alpha=self.alpha,
            cvar_limit=self.cvar_limit(years_left),
            lambda_risk=self.lambda_risk,
            w_max=self.w_max,
            w_min_pos=self.w_min_pos,
            max_holdings=self.max_holdings,
            sector_cap={**{}, **self.sector_cap},
            cash_min=self.cash_min,
            cost_rate=self.cost_rate,
            hold_days=self.hold_days,
            exclude=list(self.exclude),
        )


PROFILES: dict[str, Profile] = {
    p.key: p
    for p in [
        Profile(
            key="preserver", name="The Preserver",
            tagline="Would rather miss a rally than sit through a crash.",
            horizon_years=10, cvar_start=0.010, cvar_end=0.005,
            max_holdings=20, w_max=0.08, cash_min=0.10,
            sector_cap={"Information Technology": 0.20, "Energy": 0.10},
        ),
        Profile(
            key="steady", name="The Steady Hand",
            tagline="Balanced growth, no heroics.",
            horizon_years=10, cvar_start=0.015, cvar_end=0.007,
            max_holdings=15, w_max=0.10, cash_min=0.05,
        ),
        Profile(
            key="builder", name="The Builder",
            tagline="Growth first, with a seatbelt.",
            horizon_years=10, cvar_start=0.020, cvar_end=0.010,
            max_holdings=12, w_max=0.12, cash_min=0.02,
        ),
        Profile(
            key="maverick", name="The Maverick",
            tagline="Concentrated bets, stomach of steel.",
            horizon_years=10, cvar_start=0.028, cvar_end=0.014,
            max_holdings=8, w_max=0.20, cash_min=0.0,
            sector_cap={},
        ),
        Profile(
            key="sprinter", name="The Sprinter",
            tagline="Needs the money in three years.",
            horizon_years=3, cvar_start=0.015, cvar_end=0.004,
            max_holdings=12, w_max=0.10, cash_min=0.10,
        ),
        Profile(
            key="ethical", name="The Ethical Investor",
            tagline="Growth, but not from oil or tobacco.",
            horizon_years=10, cvar_start=0.018, cvar_end=0.009,
            max_holdings=15, w_max=0.10, cash_min=0.02,
            sector_cap={"Energy": 0.0}, exclude=("PM",),
        ),
    ]
}
