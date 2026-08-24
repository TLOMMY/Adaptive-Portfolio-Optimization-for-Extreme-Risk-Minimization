"""Plotly figure builders.

Pure functions: they take data and return figures, and import no Streamlit. That
keeps them testable and keeps chart code out of the UI layer.

Colour
------
Slots 1-4 of the reference categorical palette, assigned in fixed order and
bound to the *strategy*, never to its rank -- so filtering or reordering the
comparison never repaints a series. Every chart also carries a legend, and the
allocation chart is direct-labelled, so identity is never colour-alone.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# Reference categorical palette, slots 1-4, light mode.
SERIES_COLORS = {
    "Equal Weight": "#2a78d6",        # slot 1 blue
    "Markowitz": "#eb6834",           # slot 2 orange
    "CVaR 95%": "#1baf7a",            # slot 3 aqua
    "Robust Min-Variance": "#eda100",  # slot 4 yellow
}
FALLBACK_COLOR = "#52514e"

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"

FONT = dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13)


def _base_layout(fig: go.Figure, height: int = 420) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(**FONT, color=TEXT_PRIMARY),
        margin=dict(l=8, r=8, t=8, b=8),
        hovermode="x unified",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)", font=dict(size=12),
        ),
    )
    fig.update_xaxes(
        showgrid=False, zeroline=False,
        linecolor=GRID, tickfont=dict(color=TEXT_SECONDARY, size=11),
    )
    fig.update_yaxes(
        showgrid=True, gridcolor=GRID, zeroline=False, linecolor=GRID,
        tickfont=dict(color=TEXT_SECONDARY, size=11),
    )
    return fig


def color_for(strategy: str) -> str:
    return SERIES_COLORS.get(strategy, FALLBACK_COLOR)


def portfolio_value_chart(
    values: pd.DataFrame,
    highlight: str | None = None,
    initial_capital: float = 100_000.0,
) -> go.Figure:
    """Portfolio value over time, one line per strategy.

    The profile's own strategy is drawn thicker; the others stay fully visible
    and fully coloured -- highlighting must not amount to hiding the comparison.
    """
    fig = go.Figure()
    for name in values.columns:
        is_highlight = name == highlight
        fig.add_trace(
            go.Scatter(
                x=values.index, y=values[name], name=name, mode="lines",
                line=dict(
                    color=color_for(name),
                    width=3.5 if is_highlight else 2,
                ),
                opacity=1.0 if is_highlight else 0.85,
                hovertemplate="%{y:$,.0f}<extra>" + name + "</extra>",
            )
        )
    fig.add_hline(
        y=initial_capital, line=dict(color=GRID, width=1, dash="dot"),
        annotation_text="Starting capital", annotation_position="bottom right",
        annotation_font=dict(size=10, color=TEXT_SECONDARY),
    )
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    return _base_layout(fig, height=430)


def allocation_bar_chart(weights: pd.Series, color: str = "#2a78d6") -> go.Figure:
    """Current allocation as a horizontal bar chart, direct-labelled."""
    held = weights[weights > 1e-6].sort_values()
    fig = go.Figure(
        go.Bar(
            x=held.to_numpy(), y=list(held.index), orientation="h",
            marker=dict(color=color, line=dict(width=0)),
            text=[f"{v:.1%}" for v in held],
            textposition="outside",
            textfont=dict(color=TEXT_SECONDARY, size=11),
            hovertemplate="%{y}: %{x:.2%}<extra></extra>",
            width=0.62,
        )
    )
    fig.update_xaxes(
        tickformat=".0%", range=[0, min(1.0, float(held.max()) * 1.28)],
        showgrid=True, gridcolor=GRID,
    )
    fig.update_yaxes(showgrid=False)
    fig.update_layout(showlegend=False)
    return _base_layout(fig, height=max(240, 34 * len(held) + 60))


def allocation_history_chart(weights_history: pd.DataFrame) -> go.Figure:
    """How the allocation shifts across rebalances, as a stacked area."""
    fig = go.Figure()
    ordered = weights_history.loc[:, weights_history.mean().sort_values(ascending=False).index]
    # A ten-asset stack exceeds any categorical palette, so magnitude is carried
    # by a single-hue sequential ramp and identity by direct hover + legend.
    n = len(ordered.columns)
    for i, ticker in enumerate(ordered.columns):
        shade = 0.18 + 0.72 * (1 - i / max(n - 1, 1))
        fig.add_trace(
            go.Scatter(
                x=ordered.index, y=ordered[ticker], name=ticker,
                mode="lines", stackgroup="one", line=dict(width=0.5, color=SURFACE),
                fillcolor=f"rgba(42,120,214,{shade:.2f})",
                hovertemplate="%{y:.1%}<extra>" + ticker + "</extra>",
            )
        )
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    fig.update_layout(legend=dict(orientation="h", y=1.02, font=dict(size=10)))
    return _base_layout(fig, height=360)


def drawdown_chart(drawdowns: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    """Drawdown paths, one line per strategy. Values are negative by convention."""
    fig = go.Figure()
    for name in drawdowns.columns:
        is_highlight = name == highlight
        fig.add_trace(
            go.Scatter(
                x=drawdowns.index, y=drawdowns[name], name=name, mode="lines",
                line=dict(color=color_for(name), width=3 if is_highlight else 1.8),
                opacity=1.0 if is_highlight else 0.8,
                hovertemplate="%{y:.1%}<extra>" + name + "</extra>",
            )
        )
    fig.update_yaxes(tickformat=".0%")
    return _base_layout(fig, height=320)


# ---------------------------------------------------------------------------
# Diagnostic charts
#
# A/B here are user-chosen roles, not data-derived ranks, so binding slots 1 and
# 2 to them is stable: changing the selection repaints by intent, never as a
# side effect of reordering.
# ---------------------------------------------------------------------------

COMPARE_A = "#2a78d6"  # slot 1 blue
COMPARE_B = "#eb6834"  # slot 2 orange


def weight_comparison_chart(
    series_a: pd.Series, label_a: str, series_b: pd.Series, label_b: str, asset: str
) -> go.Figure:
    """One asset's weight over time under two strategies."""
    fig = go.Figure()
    for series, label, color in (
        (series_a, label_a, COMPARE_A),
        (series_b, label_b, COMPARE_B),
    ):
        fig.add_trace(
            go.Scatter(
                x=series.index, y=series.to_numpy(), name=label, mode="lines+markers",
                line=dict(color=color, width=2),
                marker=dict(size=6, line=dict(width=1.5, color=SURFACE)),
                hovertemplate="%{y:.1%}<extra>" + label + "</extra>",
            )
        )
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    fig.update_layout(title=None)
    return _base_layout(fig, height=330)


def turnover_comparison_chart(
    series_a: pd.Series, label_a: str, series_b: pd.Series, label_b: str,
    limit_a: float | None = None, limit_b: float | None = None,
) -> go.Figure:
    """Realised turnover at each rebalance, with any configured caps drawn in."""
    fig = go.Figure()
    for series, label, color in (
        (series_a, label_a, COMPARE_A),
        (series_b, label_b, COMPARE_B),
    ):
        fig.add_trace(
            go.Scatter(
                x=series.index, y=series.to_numpy(), name=label, mode="lines+markers",
                line=dict(color=color, width=2),
                marker=dict(size=6, line=dict(width=1.5, color=SURFACE)),
                hovertemplate="%{y:.1%}<extra>" + label + "</extra>",
            )
        )
    for limit, color, label in ((limit_a, COMPARE_A, label_a), (limit_b, COMPARE_B, label_b)):
        if limit is not None:
            fig.add_hline(
                y=limit, line=dict(color=color, width=1, dash="dash"),
                annotation_text=f"{label} cap {limit:.0%}",
                annotation_font=dict(size=10, color=TEXT_SECONDARY),
            )
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    return _base_layout(fig, height=330)


def expected_vs_realised_chart(frame: pd.DataFrame, label: str) -> go.Figure:
    """Decision-time expectation against the return that followed it."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=frame.index, y=frame["expected_return"], name="Expected (at decision)",
            mode="lines+markers", line=dict(color=COMPARE_A, width=2),
            marker=dict(size=6, line=dict(width=1.5, color=SURFACE)),
            hovertemplate="%{y:.1%}<extra>Expected</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame.index, y=frame["realised_annualised"],
            name="Realised next period (annualised)",
            mode="lines+markers", line=dict(color=COMPARE_B, width=2),
            marker=dict(size=6, line=dict(width=1.5, color=SURFACE)),
            hovertemplate="%{y:.1%}<extra>Realised</extra>",
        )
    )
    fig.add_hline(y=0, line=dict(color=GRID, width=1))
    fig.update_yaxes(tickformat=".0%")
    fig.update_layout(title=dict(text=label, font=dict(size=13, color=TEXT_SECONDARY), x=0))
    return _base_layout(fig, height=330)


def allocation_distance_chart(distances: pd.Series) -> go.Figure:
    """How far apart the two strategies were at each rebalance."""
    peak = distances.idxmax()
    fig = go.Figure(
        go.Scatter(
            x=distances.index, y=distances.to_numpy(), mode="lines+markers",
            line=dict(color=COMPARE_A, width=2),
            marker=dict(size=6, line=dict(width=1.5, color=SURFACE)),
            hovertemplate="%{y:.1%} of the portfolio differed<extra></extra>",
            showlegend=False,
        )
    )
    fig.add_vline(
        x=peak, line=dict(color=TEXT_SECONDARY, width=1, dash="dot"),
        annotation_text=f"widest gap · {peak:%b %Y}",
        annotation_font=dict(size=10, color=TEXT_SECONDARY),
    )
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    return _base_layout(fig, height=300)
