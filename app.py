"""Adaptive Investor-Specific Portfolio Optimization -- interactive demonstration.

An Operations Research teaching demo: stand at a past date, optimize a portfolio
using only information available then, observe what actually happened, repeat.

Run with:   streamlit run app.py

This module is layout and wiring only. Optimization, estimation, backtesting and
chart construction all live under ``src/`` and import no Streamlit.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.backtest.experiment import (
    COMPARISON_ORDER,
    ExperimentSpec,
    diagnostic_label,
    diagnostic_options,
    run_comparison,
    run_diagnostics,
)
from src.config.assets import DEFAULT_UNIVERSE
from src.config.periods import DEFAULT_PERIOD, PERIODS
from src.data.csv_provider import CsvProvider
from src.profiles.presets import DEFAULT_PROFILE, PROFILES, profile_mapping_table
from src.risk.metrics import comparison_table, drawdown_series
from src.ui import content, diagnostics_panel
from src.visualization import charts

st.set_page_config(
    page_title="Adaptive Portfolio Optimization",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Data and computation (cached -- the demo must stay responsive on stage)
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def load_prices() -> pd.DataFrame:
    return CsvProvider().get_adjusted_prices(DEFAULT_UNIVERSE.tickers)


@st.cache_data(show_spinner="Running the historical experiment…")
def run(profile_key: str, period_key: str):
    """Run the four-model comparison for one profile and period.

    The whole experiment is computed once and revealed progressively by the time
    machine. That is not a shortcut: every decision is causal by construction, so
    the prefix shown after k advances is identical to what stepping forward k
    times would produce -- and it keeps each click instant.
    """
    spec = ExperimentSpec(
        profile=PROFILES[profile_key],
        period=PERIODS[period_key],
        universe=DEFAULT_UNIVERSE,
    )
    return run_comparison(load_prices(), spec)


@st.cache_data(show_spinner="Preparing diagnostics…")
def run_diagnostic_experiment(period_key: str):
    """Every diagnostic strategy over one period.

    Depends only on the period, not the selected profile, so switching profiles
    never re-runs it. Each strategy carries its own profile's constraints, and
    all of them share one engine pass, so they see identical data at every
    decision date.
    """
    return run_diagnostics(load_prices(), PERIODS[period_key], DEFAULT_UNIVERSE)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

if "step" not in st.session_state:
    st.session_state.step = 0
if "profile_key" not in st.session_state:
    st.session_state.profile_key = DEFAULT_PROFILE.key
if "period_key" not in st.session_state:
    st.session_state.period_key = DEFAULT_PERIOD.key


def reset_time() -> None:
    st.session_state.step = 0


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Investor profile")
    profile_key = st.radio(
        "Investor profile",
        options=list(PROFILES),
        format_func=lambda k: PROFILES[k].name,
        key="profile_key",
        on_change=reset_time,
        label_visibility="collapsed",
    )
    profile = PROFILES[profile_key]
    st.caption(profile.tagline)

    st.divider()
    st.markdown("### Historical period")
    st.selectbox(
        "Historical period",
        options=list(PERIODS),
        format_func=lambda k: PERIODS[k].label,
        key="period_key",
        on_change=reset_time,
        label_visibility="collapsed",
    )
    period = PERIODS[st.session_state.period_key]
    st.caption(
        f"{period.start:%b %Y} – {period.end:%b %Y}. The 3-year estimation window "
        "extends before this period; all other settings are fixed."
    )

    st.divider()
    st.markdown("### Fixed methodology")
    st.markdown(
        f"""
- **Universe:** {len(DEFAULT_UNIVERSE.assets)} ETFs across
  {len(DEFAULT_UNIVERSE.asset_class_map())} asset classes
- **Lookback:** 3 years of daily data
- **Rebalancing:** quarterly
- **Estimators:** sample mean, Ledoit–Wolf
- **Transaction costs:** 0 bps
"""
    )
    st.caption("Identical for every profile and period.")


experiment = run(profile_key, st.session_state.period_key)
dates = experiment.rebalance_dates
n_steps = len(dates)
step = min(st.session_state.step, n_steps - 1)
current_date = dates[step]
highlight = profile.strategy_name

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("Adaptive Investor-Specific Portfolio Optimization")
st.caption(
    "A historical portfolio time machine. Educational Operations Research "
    "demonstration — not investment advice."
)

# The guide sits above everything and opens by default the first time a session
# loads, then stays shut once someone has started driving the app. A newcomer
# needs it immediately; a presenter mid-demo does not.
if "guide_seen" not in st.session_state:
    st.session_state.guide_seen = False

with st.expander(
    "👋  **New here? Start with this** — a short walkthrough",
    expanded=not st.session_state.guide_seen,
):
    st.markdown(content.WALKTHROUGH)
st.session_state.guide_seen = True

with st.expander("📈  **What are these 10 investments?**  (yes, they are real)"):
    st.markdown(content.ASSET_INTRO)
    st.markdown("##### The universe")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Ticker": a.ticker,
                    "Name": a.display_name,
                    "Type": a.asset_class,
                    "What it actually holds": content.ASSET_DESCRIPTIONS.get(a.ticker, ""),
                    "Data from": f"{a.inception:%b %Y}",
                }
                for a in DEFAULT_UNIVERSE.assets
            ]
        ).set_index("Ticker"),
        width="stretch",
    )
    st.caption(
        "Prices are real daily adjusted closes — dividends reinvested, splits "
        "applied. Taxes are not modelled, and this baseline charges no trading "
        "costs."
    )

# --- Section A: profile summary -------------------------------------------
st.markdown("#### Your objective")
a1, a2, a3, a4 = st.columns(4)
a1.metric("Profile", profile.name.split(" / ")[0])
a2.metric("Optimization model", profile.model_label.split(" (")[0])
a3.metric("Return target", f"{profile.return_target:.0%}")
a4.metric(
    "Turnover limit",
    "None" if profile.turnover_limit is None else f"{profile.turnover_limit:.0%}",
    help=f"Liquidity preference: {profile.liquidity.value}",
)
st.info(f"**Risk objective —** {profile.risk_objective}")

st.divider()

# --- Section B/C: the time machine ----------------------------------------
left, right = st.columns([1, 1.1])

with left:
    st.markdown("#### Historical decision date")
    st.markdown(
        f"<div style='font-size:2.6rem;font-weight:700;line-height:1.1;"
        f"letter-spacing:-0.02em'>{current_date:%B %Y}</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Decision {step + 1} of {n_steps}")
    st.warning(content.TIME_MACHINE_NOTE, icon="🔒")

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Advance quarter", width='stretch', disabled=step >= n_steps - 1):
        st.session_state.step = min(step + 1, n_steps - 1)
        st.rerun()
    if c2.button("Advance year", width='stretch', disabled=step >= n_steps - 1):
        st.session_state.step = min(step + 4, n_steps - 1)
        st.rerun()
    if c3.button("Run full period", width='stretch', type="primary"):
        st.session_state.step = n_steps - 1
        st.rerun()
    if c4.button("Reset", width='stretch'):
        st.session_state.step = 0
        st.rerun()
    st.progress((step + 1) / n_steps)

with right:
    st.markdown(f"#### Portfolio decision — {highlight}")
    result = experiment[highlight]
    record = result.rebalances[step]
    weights = record.weights_after
    diagnostics = record.diagnostics

    m1, m2, m3 = st.columns(3)
    m1.metric("Expected return", f"{diagnostics.get('expected_return', 0):.2%}",
              help="Annualised, estimated from the lookback window")
    if profile.model.value == "cvar":
        m2.metric("Est. 1-day 95% CVaR", f"{diagnostics.get('cvar', 0):.3%}",
                  help="Average loss on the worst 5% of days. Not annualised.")
    elif profile.model.value == "robust":
        m2.metric("Worst-case volatility",
                  f"{diagnostics.get('worst_case_volatility', 0):.2%}",
                  help="Across 6 covariance scenarios, annualised")
    else:
        m2.metric("Est. volatility", f"{diagnostics.get('expected_volatility', 0):.2%}",
                  help="Annualised")
    if step == 0:
        # The first rebalance establishes the position from cash; reporting it as
        # turnover would invite comparison with genuine rebalances, which it is not.
        m3.metric("Turnover this rebalance", "—", help="Initial position established from cash")
    else:
        m3.metric("Turnover this rebalance", f"{record.turnover:.1%}")

    shortfall = diagnostics.get("return_shortfall", 0.0) or 0.0
    if shortfall > 0:
        st.error(
            f"**Return target unattainable at this date.** "
            f"The best any allowed portfolio can offer is "
            f"{diagnostics.get('max_attainable_return', 0):.2%}, leaving a shortfall of "
            f"**{shortfall:.2%}** against the {profile.return_target:.0%} target. "
            "The constraint was not removed — the portfolio is solved at the closest "
            "attainable target.",
            icon="⚠️",
        )
    if diagnostics.get("turnover_limit_relaxed"):
        st.warning(
            "Turnover limit could not be met from the drifted position and was "
            "relaxed for this rebalance.", icon="↔️",
        )

    st.plotly_chart(
        charts.allocation_bar_chart(weights, charts.color_for(highlight)),
        width='stretch',
    )

with st.expander("Allocation table"):
    table = pd.DataFrame({
        "Asset": [DEFAULT_UNIVERSE.by_ticker(t).display_name for t in weights.index],
        "Class": [DEFAULT_UNIVERSE.by_ticker(t).asset_class for t in weights.index],
        "Weight": [f"{w:.2%}" for w in weights],
    }, index=weights.index)
    st.dataframe(table[table["Weight"] != "0.00%"], width='stretch')

st.divider()

# --- Section E: comparison -------------------------------------------------
st.markdown("#### How the four formulations compare")
st.caption(
    f"All four run under **{profile.name}**'s constraints and see identical data "
    f"at every decision date. {highlight} is this profile's model and is drawn "
    "thicker — the others are shown in full."
)

values = experiment.value_frame().loc[:current_date, COMPARISON_ORDER]
st.plotly_chart(
    charts.portfolio_value_chart(values, highlight=highlight),
    width='stretch',
)

# --- Section F: performance dashboard --------------------------------------
st.markdown("#### Realised performance so far")
st.caption(
    f"Measured from {values.index[0]:%b %Y} through {current_date:%b %Y}. "
    "Tail risk is a **1-day** figure and is not annualised."
)

truncated = {name: experiment[name].until(current_date) for name in COMPARISON_ORDER}
metrics = comparison_table(truncated).loc[COMPARISON_ORDER]

display = pd.DataFrame({
    "Cumulative return": metrics["cumulative_return"].map("{:.1%}".format),
    "Annualised return": metrics["annualized_return"].map("{:.2%}".format),
    "Annualised volatility": metrics["annualized_volatility"].map("{:.2%}".format),
    "Max drawdown": metrics["maximum_drawdown"].map("{:.1%}".format),
    "Daily 95% CVaR": metrics["daily_cvar"].map("{:.2%}".format),
    "Avg turnover / rebalance": metrics["average_turnover"].map("{:.1%}".format),
})
display.index.name = "Strategy"


def _emphasise(row: pd.Series):
    is_profile = row.name == highlight
    return [
        f"background-color: {'#eef4fc' if is_profile else 'transparent'};"
        f"font-weight: {'700' if is_profile else '400'}"
    ] * len(row)


st.dataframe(display.style.apply(_emphasise, axis=1), width='stretch')

with st.expander("Drawdown paths"):
    drawdowns = pd.DataFrame(
        {name: drawdown_series(r.portfolio_values) for name, r in truncated.items()}
    )
    st.plotly_chart(
        charts.drawdown_chart(drawdowns, highlight=highlight), width='stretch'
    )

with st.expander(f"How {highlight} shifted its allocation over time"):
    st.plotly_chart(
        charts.allocation_history_chart(experiment[highlight].weights_history.loc[:current_date]),
        width='stretch',
    )

st.divider()

# --- Strategy diagnostics --------------------------------------------------
with st.expander("🔍  **Strategy Diagnostics** — Explain the decisions"):
    st.markdown("### Why did these portfolios behave differently?")
    diagnostics_panel.render(
        experiment=run_diagnostic_experiment(st.session_state.period_key),
        options=diagnostic_options(),
        universe=DEFAULT_UNIVERSE,
        default_a=diagnostic_label(profile),
        default_b="Equal Weight",
    )

st.divider()

# --- Section G: the main question -----------------------------------------
st.markdown("### Which portfolio best satisfies this investor's stated objective?")
st.markdown(
    f"""
This is the question the demonstration exists to ask, and it is **not** the same
as "which one made the most money."

**{profile.name}** stated: *{profile.risk_objective}* — with a
{profile.return_target:.0%} return target and {profile.liquidity.value.lower()}
turnover. Read the table against **that** objective, not against the largest
cumulative return. A strategy that earned more while violating the investor's
stated risk objective has not served them better.

No model is labelled "best" here. The formulations optimize different things, so
each one wins on its own objective by construction — the interesting question is
what that costs on the others.
"""
)

st.divider()

# --- Poster / methodology support -----------------------------------------
left_panel, right_panel = st.columns([1, 1.35])

with left_panel:
    st.markdown("#### Methodology")
    st.markdown(content.METHODOLOGY_FLOW)

with right_panel:
    st.markdown("#### The four profiles")
    st.dataframe(
        pd.DataFrame(profile_mapping_table()).set_index("Profile"),
        width='stretch',
    )
    st.caption(
        "Profiles differ in exactly three factors: risk objective, return "
        "requirement, liquidity preference. Universe, weight caps, lookback, "
        "rebalance cadence and estimators are identical across all four."
    )

with st.expander(f"Model detail — {highlight}"):
    spec = content.MODEL_FORMULATIONS[highlight]
    st.markdown("**Objective**")
    st.code(spec["objective"], language=None)
    st.markdown(f"**In words.** {spec['reads_as']}")
    st.markdown(f"**Decision variables.** {spec['variables']}")
    st.markdown("**Shared constraints**")
    st.markdown(content.SHARED_CONSTRAINTS)
    st.markdown(f"**Worth knowing.** {spec['notes']}")

with st.expander("Assumptions, methodology and disclaimers"):
    st.markdown(content.ASSUMPTIONS)
