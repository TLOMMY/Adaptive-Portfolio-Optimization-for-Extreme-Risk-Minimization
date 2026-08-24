"""Streamlit rendering for the strategy-diagnostics panel.

Rendering only. Every number shown is computed by :mod:`src.risk.diagnostics`
and every figure by :mod:`src.visualization.charts`; this module arranges them.
Keeping it out of ``app.py`` keeps the main page readable and lets the panel be
smoke-tested as a unit.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from src.backtest.results import BacktestResult, ExperimentResult
from src.config.assets import Universe
from src.profiles.models import InvestorProfile
from src.risk import diagnostics as dx
from src.risk.metrics import comparison_table
from src.visualization import charts

HELP_HHI = (
    "Herfindahl index: the sum of squared weights. 1.0 means everything sits in "
    "one asset; 0.10 is a perfectly even ten-asset split. Higher is more "
    "concentrated."
)
HELP_MATERIAL = "How many assets are held at 5% or more — positions large enough to matter."
HELP_LARGEST = "The single biggest position, averaged across rebalances."
HELP_DISTANCE = (
    "Half the sum of absolute weight differences: the fraction of the portfolio "
    "you would have to trade to turn one strategy into the other. 0% identical, "
    "100% no overlap."
)


def _limit_for(profile: InvestorProfile | None) -> float | None:
    return profile.turnover_limit if profile else None


def _target_for(profile: InvestorProfile | None) -> float | None:
    return profile.return_target if profile else None


def _fmt(value, kind: str = "pct") -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if kind == "pct":
        return f"{value:.2%}"
    if kind == "pct0":
        return f"{value:.0%}"
    if kind == "num":
        return f"{value:,.4f}" if isinstance(value, float) else f"{value}"
    return str(value)


def render(
    experiment: ExperimentResult,
    options: dict[str, InvestorProfile | None],
    universe: Universe,
    default_a: str,
    default_b: str,
) -> None:
    """Render the whole diagnostics panel."""
    labels = list(options)

    st.caption(
        "Every strategy below runs over the selected historical period and sees "
        "identical market data at every decision date. Differences come from the "
        "objectives, parameters and constraints — nothing else."
    )

    col_a, col_b = st.columns(2)
    label_a = col_a.selectbox(
        "Compare Strategy A", labels,
        index=labels.index(default_a) if default_a in labels else 0,
        key="diag_a",
    )
    label_b = col_b.selectbox(
        "Compare Strategy B", labels,
        index=labels.index(default_b) if default_b in labels else 1,
        key="diag_b",
    )

    if label_a == label_b:
        st.info("Pick two different strategies to compare.")
        return

    result_a, result_b = experiment[label_a], experiment[label_b]
    profile_a, profile_b = options[label_a], options[label_b]
    limit_a, limit_b = _limit_for(profile_a), _limit_for(profile_b)

    _render_summary(label_a, result_a, profile_a, label_b, result_b, profile_b)
    st.divider()
    _render_allocation(label_a, result_a, label_b, result_b, universe)
    st.divider()
    _render_turnover(label_a, result_a, limit_a, label_b, result_b, limit_b)
    st.divider()
    _render_concentration(label_a, result_a, label_b, result_b)
    st.divider()
    _render_expected_vs_realised(label_a, result_a, label_b, result_b)
    st.divider()
    _render_model_specific(label_a, result_a, label_b, result_b)
    st.divider()
    _render_disagreement(label_a, result_a, label_b, result_b)
    st.divider()
    _render_interpretation(label_a, result_a, label_b, result_b, limit_a, limit_b)


# ---------------------------------------------------------------------------


def _render_summary(label_a, result_a, profile_a, label_b, result_b, profile_b) -> None:
    st.markdown("##### Side-by-side summary")

    metrics = comparison_table({label_a: result_a, label_b: result_b})
    rows = {
        "Cumulative return": ("cumulative_return", "pct"),
        "Annualised return": ("annualized_return", "pct"),
        "Annualised volatility": ("annualized_volatility", "pct"),
        "Maximum drawdown": ("maximum_drawdown", "pct"),
        "Daily 95% CVaR": ("daily_cvar", "pct"),
        "Avg turnover / rebalance": ("average_turnover", "pct"),
    }
    table = {
        name: {
            label_a: _fmt(metrics.loc[label_a, column], kind),
            label_b: _fmt(metrics.loc[label_b, column], kind),
        }
        for name, (column, kind) in rows.items()
    }
    table["Configured return target"] = {
        label_a: _fmt(_target_for(profile_a), "pct0"),
        label_b: _fmt(_target_for(profile_b), "pct0"),
    }
    table["Return shortfalls"] = {
        label_a: f"{dx._shortfall_count(result_a)} of {len(result_a.rebalances)}",
        label_b: f"{dx._shortfall_count(result_b)} of {len(result_b.rebalances)}",
    }
    table["Configured turnover limit"] = {
        label_a: _fmt(_limit_for(profile_a), "pct0"),
        label_b: _fmt(_limit_for(profile_b), "pct0"),
    }
    st.dataframe(pd.DataFrame(table).T, width="stretch")


def _render_allocation(label_a, result_a, label_b, result_b, universe) -> None:
    st.markdown("##### Allocation over time")

    comparison = dx.average_allocation_comparison(result_a, result_b)
    assets = list(comparison.index)
    asset = st.selectbox(
        "Asset", assets,
        format_func=lambda t: f"{t} — {universe.by_ticker(t).display_name}",
        key="diag_asset",
        help="Sorted by how differently the two strategies treated it.",
    )
    st.plotly_chart(
        charts.weight_comparison_chart(
            dx.weight_path(result_a, asset), label_a,
            dx.weight_path(result_b, asset), label_b, asset,
        ),
        width="stretch",
    )

    st.markdown("**Average weight over the period**, biggest differences first")
    display = pd.DataFrame({
        f"{label_a}": comparison["A"].map("{:.1%}".format),
        f"{label_b}": comparison["B"].map("{:.1%}".format),
        "Difference (A − B)": comparison["difference"].map("{:+.1%}".format),
    })
    display.index = [f"{t} — {universe.by_ticker(t).display_name}" for t in comparison.index]
    st.dataframe(display, width="stretch")


def _render_turnover(label_a, result_a, limit_a, label_b, result_b, limit_b) -> None:
    st.markdown("##### Turnover")

    diag_a = dx.turnover_diagnostics(result_a, limit_a)
    diag_b = dx.turnover_diagnostics(result_b, limit_b)

    for label, diag in ((label_a, diag_a), (label_b, diag_b)):
        if diag["limit"] is None:
            st.caption(
                f"**{label}** — no optimizer turnover constraint. Rebalances only "
                "to restore its target allocation."
            )

    table = pd.DataFrame({
        label_a: {
            "Configured limit": _fmt(diag_a["limit"], "pct0"),
            "Average realised": _fmt(diag_a["avg_turnover"]),
            "Maximum realised": _fmt(diag_a["max_turnover"]),
            "Rebalances where the cap bound": (
                "—" if diag_a["limit"] is None
                else f"{diag_a['n_binding']} of {diag_a['n_rebalances']} ({diag_a['pct_binding']:.0%})"
            ),
        },
        label_b: {
            "Configured limit": _fmt(diag_b["limit"], "pct0"),
            "Average realised": _fmt(diag_b["avg_turnover"]),
            "Maximum realised": _fmt(diag_b["max_turnover"]),
            "Rebalances where the cap bound": (
                "—" if diag_b["limit"] is None
                else f"{diag_b['n_binding']} of {diag_b['n_rebalances']} ({diag_b['pct_binding']:.0%})"
            ),
        },
    })
    st.dataframe(table, width="stretch")
    st.plotly_chart(
        charts.turnover_comparison_chart(
            dx.turnover_by_rebalance(result_a), label_a,
            dx.turnover_by_rebalance(result_b), label_b, limit_a, limit_b,
        ),
        width="stretch",
    )
    st.caption(
        "A cap that never binds did not constrain any decision, so it cannot "
        "explain a difference in outcome."
    )


def _render_concentration(label_a, result_a, label_b, result_b) -> None:
    st.markdown("##### Concentration")

    conc_a = dx.concentration_summary(result_a)
    conc_b = dx.concentration_summary(result_b)

    c1, c2, c3 = st.columns(3)
    c1.metric(f"{label_a} · avg largest position", _fmt(conc_a["avg_largest_position"]),
              help=HELP_LARGEST)
    c2.metric(f"{label_a} · avg assets ≥ 5%", f"{conc_a['avg_n_material']:.1f}",
              help=HELP_MATERIAL)
    c3.metric(f"{label_a} · avg HHI", f"{conc_a['avg_hhi']:.3f}", help=HELP_HHI)

    c4, c5, c6 = st.columns(3)
    c4.metric(f"{label_b} · avg largest position", _fmt(conc_b["avg_largest_position"]),
              help=HELP_LARGEST)
    c5.metric(f"{label_b} · avg assets ≥ 5%", f"{conc_b['avg_n_material']:.1f}",
              help=HELP_MATERIAL)
    c6.metric(f"{label_b} · avg HHI", f"{conc_b['avg_hhi']:.3f}", help=HELP_HHI)


def _render_expected_vs_realised(label_a, result_a, label_b, result_b) -> None:
    st.markdown("##### Expected vs realised return")
    st.caption(
        "What each strategy expected at the moment it decided, against what "
        "actually followed. **The realised column is ex-post only** — it was not "
        "available to the optimizer, which had already committed. A single "
        "quarter annualised is a noisy number; read the pattern, not a point."
    )

    tabs = st.tabs([label_a, label_b])
    for tab, label, result in ((tabs[0], label_a, result_a), (tabs[1], label_b, result_b)):
        with tab:
            frame = dx.expected_vs_realised(result)
            if frame["expected_return"].isna().all():
                st.caption(
                    f"**{label}** estimates no expected return — it performs no "
                    "optimization — so only the realised column is shown."
                )
            st.plotly_chart(
                charts.expected_vs_realised_chart(frame, label), width="stretch"
            )
            accuracy = dx.expectation_accuracy(frame)
            if accuracy["n"]:
                st.caption(
                    f"Expected exceeded realised on **{accuracy['n_overshot']} of "
                    f"{accuracy['n']}** decisions (mean gap "
                    f"{accuracy['mean_gap']:+.2%} annualised)."
                )
            display = frame.copy()
            display.index = display.index.strftime("%Y-%m-%d")
            st.dataframe(
                pd.DataFrame({
                    "Expected (annualised)": display["expected_return"].map(
                        lambda v: "—" if pd.isna(v) else f"{v:.2%}"),
                    "Realised next period": display["realised_period_return"].map(
                        lambda v: "—" if pd.isna(v) else f"{v:.2%}"),
                    "Realised (annualised)": display["realised_annualised"].map(
                        lambda v: "—" if pd.isna(v) else f"{v:.2%}"),
                }),
                width="stretch",
            )


def _render_model_specific(label_a, result_a, label_b, result_b) -> None:
    st.markdown("##### Model-specific diagnostics")
    st.caption("Values from the most recent decision in the selected period.")

    for label, result in ((label_a, result_a), (label_b, result_b)):
        model = dx.model_diagnostics(result)
        st.markdown(f"**{label}**")
        st.caption(model.explanation)
        rows = {
            key: _fmt(value, "pct" if isinstance(value, float) and abs(value) < 10 else "num")
            if isinstance(value, (int, float, bool)) or value is None
            else str(value)
            for key, value in model.fields.items()
        }
        st.dataframe(pd.Series(rows, name="value").to_frame(), width="stretch")


def _render_disagreement(label_a, result_a, label_b, result_b) -> None:
    st.markdown("##### Biggest allocation disagreement")

    distances = dx.allocation_distance_series(result_a, result_b)
    if distances.empty:
        st.caption("The two strategies share no rebalance dates.")
        return

    date, frame = dx.largest_disagreement(result_a, result_b)
    st.markdown(
        f"**Largest allocation disagreement: {date:%B %Y}** — "
        f"{distances.max():.1%} of the portfolio allocated differently.",
        help=HELP_DISTANCE,
    )
    st.plotly_chart(charts.allocation_distance_chart(distances), width="stretch")

    material = frame[frame["difference"].abs() > 1e-4]
    st.dataframe(
        pd.DataFrame({
            label_a: material["A"].map("{:.1%}".format),
            label_b: material["B"].map("{:.1%}".format),
            "Difference": material["difference"].map("{:+.1%}".format),
        }),
        width="stretch",
    )


def _render_interpretation(
    label_a: str, result_a: BacktestResult,
    label_b: str, result_b: BacktestResult,
    limit_a: float | None, limit_b: float | None,
) -> None:
    st.markdown("##### What the numbers say")
    statements = dx.interpretation_statements(
        label_a, result_a, label_b, result_b, limit_a, limit_b
    )
    if not statements:
        st.caption("No material differences to report for this pair.")
        return
    st.markdown("\n".join(f"- {s}" for s in statements))
    st.caption(
        "These are restatements of computed quantities, not causal claims. One "
        "historical path cannot establish why a strategy behaved as it did, only "
        "that it did."
    )
