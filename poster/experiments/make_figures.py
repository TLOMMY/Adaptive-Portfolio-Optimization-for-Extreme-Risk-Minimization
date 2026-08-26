"""Poster figures from experiments/out/*.csv  ->  poster/figures/*.pdf

Run from the repo root:  uv run python poster/experiments/make_figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

matplotlib.use("Agg")

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
FIG = HERE.parent / "figures"
FIG.mkdir(exist_ok=True)

NAVY, TEAL, ORANGE = "#122D55", "#00787D", "#DA732D"
COL = {"markowitz": ORANGE, "markowitz_lw": "#C8A028", "robust": "#7850A0",
       "cvar": TEAL, "equal": NAVY, "SPY": "#555555"}
LABEL = {"markowitz": "Markowitz (sample)", "markowitz_lw": "Markowitz + Ledoit–Wolf",
         "robust": "Robust (ellipsoid on μ)", "cvar": "CVaR limit", "equal": "1/N equal weight",
         "SPY": "S&P 500 (SPY)"}
MODELS = ["markowitz", "markowitz_lw", "robust", "cvar", "equal"]
PROFILES = ["preserver", "steady", "builder", "maverick", "ethical"]
PNAME = {"preserver": "Preserver", "steady": "Steady Hand", "builder": "Builder",
         "maverick": "Maverick", "sprinter": "Sprinter", "ethical": "Ethical"}
MARK = {"preserver": "o", "steady": "s", "builder": "^", "maverick": "D", "sprinter": "v", "ethical": "P"}

plt.rcParams.update({
    "font.family": "serif", "font.size": 12.5, "axes.titlesize": 12.5, "axes.labelsize": 12.5,
    "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#333333",
    "legend.frameon": False, "figure.dpi": 150, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf")
    fig.savefig(FIG / f"{name}.png", dpi=170)
    plt.close(fig)
    print("wrote", name)


# ------------------------------------------------------------------ 1. correlation heatmaps
def fig_corr():
    est = pd.read_csv(OUT / "corr_est.csv", index_col=0)
    real = pd.read_csv(OUT / "corr_real.csv", index_col=0)
    sectors = pd.read_csv(OUT / "corr_sectors.csv", index_col=0)["sector"]
    cmap = LinearSegmentedColormap.from_list("c", ["#FFFFFF", "#F7C59F", ORANGE, "#7A1E0C"])
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.4))
    for ax, m, title in zip(axes, [est, real],
                            ["Estimated: 2017–2019 (what the optimiser saw)",
                             "Realised: Jan–Mar 2020 (what it got)"]):
        im = ax.imshow(m.values, cmap=cmap, vmin=0, vmax=1)
        ax.set_title(title, fontsize=11)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ["top", "right", "left", "bottom"]:
            ax.spines[s].set_visible(False)
        # sector brackets
        bounds = np.flatnonzero(sectors.values[1:] != sectors.values[:-1]) + 0.5
        for b in bounds:
            ax.axhline(b, color="white", lw=0.8); ax.axvline(b, color="white", lw=0.8)
        off = m.values[np.triu_indices(len(m), 1)].mean()
        ax.text(0.99, -0.03, f"mean pairwise ρ = {off:.2f}", transform=ax.transAxes,
                ha="right", va="top", fontsize=10, color=NAVY, fontweight="bold")
    # sector labels on left plot
    starts = [0] + list(np.flatnonzero(sectors.values[1:] != sectors.values[:-1]) + 1)
    ends = starts[1:] + [len(sectors)]
    for a, b in zip(starts, ends):
        axes[0].text(-1.2, (a + b - 1) / 2, sectors.values[a], ha="right", va="center", fontsize=7.5)
    cb = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02)
    cb.set_label("correlation of daily returns")
    save(fig, "fig_corr")


# ------------------------------------------------------------------ 2. growth of $1 (one profile)
def fig_growth(profile="steady"):
    r = pd.read_csv(OUT / "daily_returns.csv", index_col=0, parse_dates=True)
    fig, ax = plt.subplots(figsize=(8.6, 3.5))
    for m in MODELS:
        g = (1 + r[f"{profile}__{m}"]).cumprod()
        ax.plot(g.index, g.values, color=COL[m], lw=1.8, label=LABEL[m])
    g = (1 + r["SPY"]).cumprod()
    ax.plot(g.index, g.values, color=COL["SPY"], lw=1.6, ls="--", label=LABEL["SPY"])
    ax.axvspan(pd.Timestamp("2020-02-19"), pd.Timestamp("2020-03-23"), color="#E8F1F8", zorder=0)
    ax.axvspan(pd.Timestamp("2022-01-03"), pd.Timestamp("2022-10-12"), color="#E8F1F8", zorder=0)
    ax.text(pd.Timestamp("2020-03-05"), 0.86, "COVID", ha="center", va="bottom", fontsize=10, color=NAVY)
    ax.text(pd.Timestamp("2022-05-20"), 0.86, "rate shock", ha="center", va="bottom", fontsize=10, color=NAVY)
    ax.set_ylim(0.84, 6.8)
    ax.set_ylabel("growth of $1 (log scale)")
    ax.set_yscale("log")
    ax.set_yticks([1, 1.5, 2, 3, 4, 6]); ax.set_yticklabels(["1", "1.5", "2", "3", "4", "6"])
    ax.set_title(f"Growth of $1 under the {PNAME[profile]} rules, 2016–2025, out of sample", fontsize=12)
    ax.legend(loc="upper left", fontsize=10, ncol=3, handlelength=1.6, columnspacing=1.0)
    ax.grid(axis="y", color="#DDDDDD", lw=0.6)
    save(fig, "fig_growth")


# ------------------------------------------------------------------ 3. risk–return scatter, all runs
def fig_scatter():
    b = pd.read_csv(OUT / "bootstrap_runs.csv")
    pt = b.pivot_table(index="run", columns="metric", values="point")
    fig, ax = plt.subplots(figsize=(5.6, 4.8))
    for p in PROFILES:
        for m in MODELS:
            row = pt.loc[f"{p}__{m}"]
            ax.scatter(row["cvar_95_daily"] * 100, row["cagr"] * 100, color=COL[m], marker=MARK[p],
                       s=75, edgecolor="white", lw=0.5, zorder=3)
    spy = pt.loc["SPY"]
    ax.scatter(spy["cvar_95_daily"] * 100, spy["cagr"] * 100, color="black", marker="*", s=220, zorder=4)
    ax.annotate("S&P 500", (spy["cvar_95_daily"] * 100, spy["cagr"] * 100), xytext=(-8, 8),
                textcoords="offset points", ha="right", fontsize=10, fontweight="bold")
    # per-model mean, as a larger hollow marker
    for m in MODELS:
        sub = pt.loc[[f"{p}__{m}" for p in PROFILES]]
        ax.scatter(sub["cvar_95_daily"].mean() * 100, sub["cagr"].mean() * 100, facecolor="none",
                   edgecolor=COL[m], s=260, lw=2.2, zorder=5)
    h1 = [plt.Line2D([], [], color=COL[m], marker="o", ls="", ms=7, label=LABEL[m]) for m in MODELS]
    h2 = [plt.Line2D([], [], color="#666666", marker=MARK[p], ls="", ms=6, label=PNAME[p]) for p in PROFILES]
    l1 = ax.legend(handles=h1, loc="lower right", fontsize=10, title="colour = model", title_fontsize=10.5)
    ax.add_artist(l1)
    ax.legend(handles=h2, loc="upper left", fontsize=10, title="marker = investor rules", title_fontsize=10.5, ncol=2)
    ax.set_xlabel("realised CVaR₉₅, % (mean loss on worst 5% of days)")
    ax.set_ylabel("CAGR (% per year)")
    ax.grid(color="#DDDDDD", lw=0.6)
    save(fig, "fig_scatter")


# ------------------------------------------------------------------ 4. sub-period Sharpe by model
def fig_subperiods():
    sp = pd.read_csv(OUT / "subperiods.csv")
    periods = list(dict.fromkeys(sp["period"]))
    fig, ax = plt.subplots(figsize=(8.6, 3.3))
    width = 0.13
    x = np.arange(len(periods))
    for i, m in enumerate(MODELS + ["SPY"]):
        sub = sp[sp.model == m]
        means = [sub[sub.period == p]["sharpe"].mean() for p in periods]
        lo = [sub[sub.period == p]["sharpe"].min() for p in periods]
        hi = [sub[sub.period == p]["sharpe"].max() for p in periods]
        xs = x + (i - 2.5) * width
        ax.bar(xs, means, width, color=COL[m], label=LABEL[m], alpha=0.95 if m != "SPY" else 0.6)
        if m != "SPY":
            ax.vlines(xs, lo, hi, color="black", lw=0.8, alpha=0.6)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(periods)
    ax.set_ylabel("Sharpe ratio (annualised)")
    ax.legend(fontsize=10.5, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.14))
    ax.set_title("Sharpe by regime. Bar = mean over the five rule-sets, whisker = min–max", fontsize=12)
    ax.grid(axis="y", color="#DDDDDD", lw=0.6)
    save(fig, "fig_subperiods")


# ------------------------------------------------------------------ 5. bootstrap: paired differences vs 1/N
def fig_bootstrap(metric="sharpe", reference="equal"):
    pr = pd.read_csv(OUT / "bootstrap_pairs.csv")
    d = pr[(pr.metric == metric) & (pr.reference == reference)]
    models = [m for m in MODELS if m != reference]
    fig, ax = plt.subplots(figsize=(5.6, 4.8))
    y = 0
    yticks, ylabels = [], []
    for m in models:
        ys = []
        for p in PROFILES:
            row = d[(d.model == m) & (d.profile == p)].iloc[0]
            ax.plot([row["lo"], row["hi"]], [y, y], color=COL[m], lw=2.6, alpha=0.85)
            ax.plot(row["point_diff"], y, marker=MARK[p], color=COL[m], ms=8, mec="white", mew=0.5)
            ys.append(y); y += 1
        yticks.append(np.mean(ys)); ylabels.append(LABEL[m])
        y += 1.2
    ax.axvline(0, color="black", lw=1)
    ax.set_yticks(yticks); ax.set_yticklabels([l.replace(" (", "\n(") for l in ylabels], fontsize=11)
    ax.invert_yaxis()
    ax.set_xlabel(f"Δ {'Sharpe' if metric=='sharpe' else 'CVaR₉₅'} vs 1/N under the same rules")
    ax.set_title("95% block-bootstrap CI, one row per rule-set", fontsize=12)
    ax.grid(axis="x", color="#DDDDDD", lw=0.6)
    save(fig, f"fig_bootstrap_{metric}")


# ------------------------------------------------------------------ 6. summary table (LaTeX)
TEXLABEL = {"markowitz": "Markowitz (sample)", "markowitz_lw": "Markowitz + Ledoit--Wolf",
            "robust": "Robust (ellipsoid on $\\mu$)", "cvar": "CVaR limit", "equal": "$1/N$ equal weight",
            "SPY": "S\\&P 500 (SPY)"}


def table_models():
    mo = pd.read_csv(OUT / "bootstrap_models.csv")
    rows = []
    for m in MODELS + ["SPY"]:
        g = mo[mo.model == m].set_index("metric")
        rows.append(
            f"{TEXLABEL[m]} & {g.loc['cagr','point']*100:.1f} & {g.loc['sharpe','point']:.2f} "
            f"[{g.loc['sharpe','lo']:.2f}, {g.loc['sharpe','hi']:.2f}] & "
            f"{g.loc['max_drawdown','point']*100:.0f} & {g.loc['cvar_95_daily','point']*100:.2f} \\\\")
    body = "\n".join(rows)
    tex = ("\\begin{tabular}{lcccc}\n\\toprule\nModel & CAGR \\% & Sharpe [95\\% CI] & Max DD \\% & CVaR$_{95}$ \\% \\\\\n"
           "\\midrule\n" + body + "\n\\bottomrule\n\\end{tabular}\n")
    (FIG / "table_models.tex").write_text(tex)
    print("wrote table_models.tex")


if __name__ == "__main__":
    fig_corr()
    fig_growth()
    fig_scatter()
    fig_subperiods()
    fig_bootstrap("sharpe")
    fig_bootstrap("cvar_95_daily")
    table_models()
