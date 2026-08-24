"""Ex-post diagnostics: why did two strategies decide differently?

Everything here reads a **completed** :class:`~src.backtest.results.BacktestResult`
and the diagnostics each optimizer already recorded at decision time. Nothing in
this module is reachable from an optimizer or an estimator, and nothing here can
influence a portfolio decision -- it lives in ``src.risk`` for exactly that
reason, the package boundary that separates ex-post measurement from ex-ante
estimation.

One function, :func:`expected_vs_realised`, deliberately pairs a decision-time
estimate with the return that followed it. That pairing is only legitimate
*after* the fact: the realised leg is read from the recorded value path, never
passed back into anything. A test asserts these functions leave decisions
unchanged.

These diagnostics explain differences. They do not rank strategies, and no
function here returns a "winner".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.backtest.results import BacktestResult

MATERIAL_WEIGHT = 0.05
"""A position at or above this is counted as 'materially held'."""

BINDING_TOLERANCE = 1e-4
"""How close realised turnover must sit to its cap to count as binding.

The solver lands on an active constraint to within its own tolerance rather
than exactly on it, so 'bound' has to be a numerical test, not equality.
"""


# ---------------------------------------------------------------------------
# Concentration
# ---------------------------------------------------------------------------


def largest_position(weights: pd.Series | np.ndarray) -> float:
    """The single biggest weight in a portfolio, ``max_i x_i``."""
    values = _as_array(weights)
    return float(values.max()) if values.size else 0.0


def materially_held(
    weights: pd.Series | np.ndarray, threshold: float = MATERIAL_WEIGHT
) -> int:
    """How many assets are held at or above ``threshold``.

    A portfolio can spread across ten names while putting 97% into two of them;
    counting only material positions describes how many holdings actually matter.
    """
    return int((_as_array(weights) >= threshold - 1e-12).sum())


def herfindahl(weights: pd.Series | np.ndarray) -> float:
    r"""Herfindahl concentration index, :math:`\\mathrm{HHI} = \\sum_i x_i^2`.

    Ranges from ``1/N`` (perfectly even) to ``1`` (everything in one asset), so
    **higher means more concentrated**. For a ten-asset universe an equal-weight
    portfolio scores 0.10.
    """
    values = _as_array(weights)
    return float(np.square(values).sum())


def concentration_by_rebalance(result: BacktestResult) -> pd.DataFrame:
    """Concentration measures at every rebalance date."""
    rows = [
        {
            "date": record.as_of,
            "largest_position": largest_position(record.weights_after),
            "n_material": materially_held(record.weights_after),
            "hhi": herfindahl(record.weights_after),
        }
        for record in result.rebalances
    ]
    return pd.DataFrame(rows).set_index("date")


def concentration_summary(result: BacktestResult) -> dict[str, float]:
    """Average concentration across the evaluation period."""
    frame = concentration_by_rebalance(result)
    if frame.empty:
        return {"avg_largest_position": 0.0, "avg_n_material": 0.0, "avg_hhi": 0.0}
    return {
        "avg_largest_position": float(frame["largest_position"].mean()),
        "avg_n_material": float(frame["n_material"].mean()),
        "avg_hhi": float(frame["hhi"].mean()),
    }


# ---------------------------------------------------------------------------
# Allocation comparison
# ---------------------------------------------------------------------------


def allocation_distance(
    weights_a: pd.Series | np.ndarray, weights_b: pd.Series | np.ndarray
) -> float:
    r"""How far apart two portfolios are: :math:`\\tfrac12\\sum_i |x_i^A - x_i^B|`.

    Ranges 0 (identical) to 1 (no overlap at all). The one-half matches the
    one-way turnover convention: it is the fraction of the portfolio that would
    have to change hands to turn A into B.
    """
    a, b = _as_array(weights_a), _as_array(weights_b)
    if a.shape != b.shape:
        raise ValueError(f"weight vectors differ in length: {a.shape} vs {b.shape}")
    return float(0.5 * np.abs(a - b).sum())


def allocation_distance_series(
    result_a: BacktestResult, result_b: BacktestResult
) -> pd.Series:
    """Allocation distance at every rebalance date the two strategies share."""
    a, b = result_a.weights_history, result_b.weights_history
    dates = a.index.intersection(b.index)
    assets = [c for c in a.columns if c in b.columns]
    return pd.Series(
        [allocation_distance(a.loc[d, assets], b.loc[d, assets]) for d in dates],
        index=dates,
        name="allocation_distance",
    )


def largest_disagreement(
    result_a: BacktestResult, result_b: BacktestResult
) -> tuple[pd.Timestamp | None, pd.DataFrame]:
    """The date the two strategies differed most, and the breakdown by asset.

    Returns ``(date, frame)`` where ``frame`` has one row per asset sorted by
    absolute difference. ``(None, empty)`` when they share no rebalance dates.
    """
    distances = allocation_distance_series(result_a, result_b)
    if distances.empty:
        return None, pd.DataFrame()

    date = distances.idxmax()
    assets = [c for c in result_a.weights_history.columns if c in result_b.weights_history.columns]
    a = result_a.weights_history.loc[date, assets]
    b = result_b.weights_history.loc[date, assets]

    frame = pd.DataFrame({"A": a, "B": b})
    frame["difference"] = frame["A"] - frame["B"]
    frame = frame.reindex(frame["difference"].abs().sort_values(ascending=False).index)
    frame.index.name = "asset"
    return date, frame


def average_allocation_comparison(
    result_a: BacktestResult, result_b: BacktestResult
) -> pd.DataFrame:
    """Average weight per asset for each strategy, sorted by absolute difference."""
    a, b = result_a.weights_history, result_b.weights_history
    assets = [c for c in a.columns if c in b.columns]
    frame = pd.DataFrame({"A": a[assets].mean(), "B": b[assets].mean()})
    frame["difference"] = frame["A"] - frame["B"]
    frame = frame.reindex(frame["difference"].abs().sort_values(ascending=False).index)
    frame.index.name = "asset"
    return frame


def weight_path(result: BacktestResult, asset: str) -> pd.Series:
    """One asset's weight at each rebalance date."""
    if asset not in result.weights_history.columns:
        raise KeyError(f"{asset!r} is not in this result's universe")
    return result.weights_history[asset].rename(result.strategy_name)


# ---------------------------------------------------------------------------
# Turnover
# ---------------------------------------------------------------------------


def turnover_by_rebalance(result: BacktestResult, exclude_initial: bool = True) -> pd.Series:
    """Realised one-way turnover at each rebalance.

    The first rebalance establishes the position from cash and is excluded by
    default: it is not a rebalance in the usual sense.
    """
    records = result.rebalances[1:] if exclude_initial else result.rebalances
    return pd.Series(
        [r.turnover for r in records],
        index=pd.DatetimeIndex([r.as_of for r in records], name="date"),
        name=result.strategy_name,
    )


def turnover_diagnostics(
    result: BacktestResult, limit: float | None = None
) -> dict[str, Any]:
    """Turnover summary, including how often a configured cap actually bound.

    A cap that never binds cannot have changed any decision, so 'bound' is
    reported as a count rather than assumed from the cap's presence.
    """
    series = turnover_by_rebalance(result)
    n = len(series)
    bound = 0
    if limit is not None and n:
        bound = int((series >= limit - BINDING_TOLERANCE).sum())

    return {
        "limit": limit,
        "avg_turnover": float(series.mean()) if n else 0.0,
        "max_turnover": float(series.max()) if n else 0.0,
        "n_rebalances": n,
        "n_binding": bound,
        "pct_binding": (bound / n) if n else 0.0,
        "n_relaxed": sum(
            1 for r in result.rebalances if r.diagnostics.get("turnover_limit_relaxed")
        ),
    }


def equal_weight_drift(result: BacktestResult) -> pd.DataFrame:
    """Drift and restoring trade for a strategy that targets a fixed allocation.

    For Equal Weight there is no optimization: turnover arises purely because
    market movements pull the weights away from 1/N between rebalances.
    """
    rows = []
    for record in result.rebalances[1:]:
        before, after = record.weights_before, record.weights_after
        rows.append(
            {
                "date": record.as_of,
                "max_drift": float((before - after).abs().max()),
                "most_drifted_asset": (before - after).abs().idxmax(),
                "traded_to_restore": record.turnover,
            }
        )
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# Expected vs realised
# ---------------------------------------------------------------------------


def expected_vs_realised(result: BacktestResult) -> pd.DataFrame:
    """Decision-time expected return beside the return that actually followed.

    **Ex-post only.** The realised leg is read from the recorded value path after
    the experiment completed; it is never available to the optimizer, which had
    already committed to weights before any of it existed.

    Columns
    -------
    expected_return
        Annualised expected return estimated at the decision date. ``NaN`` for
        strategies that estimate nothing (Equal Weight).
    realised_period_return
        The portfolio's actual return from this rebalance to the next.
    realised_annualised
        That period return scaled to an annual rate, so the two columns are
        comparable. A single quarter annualised is a noisy figure and should be
        read as such.
    """
    values = result.portfolio_values
    rows = []

    for i, record in enumerate(result.rebalances):
        start = record.as_of
        is_last = i == len(result.rebalances) - 1
        end = values.index[-1] if is_last else result.rebalances[i + 1].as_of

        if start not in values.index or end not in values.index or end <= start:
            realised = np.nan
            days = 0
        else:
            realised = float(values.loc[end] / values.loc[start] - 1.0)
            days = int(values.loc[start:end].shape[0] - 1)

        expected = record.diagnostics.get("expected_return", np.nan)
        annualised = (
            float((1.0 + realised) ** (252.0 / days) - 1.0)
            if days > 0 and np.isfinite(realised) and (1.0 + realised) > 0
            else np.nan
        )

        rows.append(
            {
                "date": start,
                "strategy": result.strategy_name,
                "expected_return": float(expected) if expected is not None else np.nan,
                "realised_period_return": realised,
                "realised_annualised": annualised,
                "period_trading_days": days,
            }
        )

    return pd.DataFrame(rows).set_index("date")


def expectation_accuracy(frame: pd.DataFrame) -> dict[str, Any]:
    """How often the decision-time estimate overshot what followed.

    Purely descriptive. An estimate that overshoots is not evidence of a flawed
    model: a single quarter is one draw from a distribution the estimate
    describes only in expectation.
    """
    usable = frame.dropna(subset=["expected_return", "realised_annualised"])
    if usable.empty:
        return {"n": 0, "n_overshot": 0, "pct_overshot": 0.0, "mean_gap": np.nan}

    gap = usable["expected_return"] - usable["realised_annualised"]
    return {
        "n": int(len(usable)),
        "n_overshot": int((gap > 0).sum()),
        "pct_overshot": float((gap > 0).mean()),
        "mean_gap": float(gap.mean()),
    }


# ---------------------------------------------------------------------------
# Model-specific diagnostics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModelDiagnostics:
    """Model-specific fields pulled from what the optimizer already recorded."""

    model: str
    explanation: str
    fields: dict[str, Any]


MODEL_EXPLANATIONS = {
    "markowitz": (
        "Markowitz balances estimated expected return against variance. It treats "
        "the estimated covariance as if it were known exactly, and penalises "
        "upside and downside variation equally."
    ),
    "cvar": (
        "CVaR directly targets severe tail losses rather than ordinary variance. "
        "It minimises the average loss across the worst (1 - alpha) of historical "
        "scenarios and is indifferent to variation outside that tail."
    ),
    "robust": (
        "Robust Min-Variance minimises risk under the most adverse covariance "
        "estimate in the predefined uncertainty set, rather than trusting a single "
        "estimate."
    ),
    "equal_weight": (
        "Equal Weight performs no optimization. Turnover arises only because market "
        "movements cause weights to drift away from the 1/N target between "
        "rebalances."
    ),
}


def _infer_model(record_diagnostics: dict[str, Any]) -> str:
    if "risk_aversion" in record_diagnostics:
        return "markowitz"
    if "cvar" in record_diagnostics:
        return "cvar"
    if "robust_objective" in record_diagnostics:
        return "robust"
    return "equal_weight"


def model_diagnostics(result: BacktestResult, index: int = -1) -> ModelDiagnostics:
    """Model-specific diagnostics for one rebalance, defaulting to the last."""
    if not result.rebalances:
        return ModelDiagnostics("unknown", "", {})

    record = result.rebalances[index]
    diagnostics = record.diagnostics
    model = _infer_model(diagnostics)

    common = {
        "Return target": diagnostics.get("return_target"),
        "Return shortfall": diagnostics.get("return_shortfall", 0.0),
        "Turnover limit": diagnostics.get("turnover_limit"),
        "Turnover this rebalance": record.turnover,
        "Turnover limit relaxed": bool(diagnostics.get("turnover_limit_relaxed", False)),
    }

    if model == "markowitz":
        fields = {
            "Risk aversion (lambda)": diagnostics.get("risk_aversion"),
            "Estimated expected return": diagnostics.get("expected_return"),
            "Estimated annualised volatility": diagnostics.get("expected_volatility"),
            **common,
        }
    elif model == "cvar":
        fields = {
            "Confidence level (alpha)": diagnostics.get("cvar_confidence"),
            "Estimated 1-day VaR": diagnostics.get("var"),
            "Estimated 1-day CVaR": diagnostics.get("cvar"),
            "Scenarios used": diagnostics.get("n_scenarios"),
            "Estimated expected return": diagnostics.get("expected_return"),
            **common,
        }
    elif model == "robust":
        variances = diagnostics.get("variance_by_scenario") or []
        fields = {
            "Covariance scenarios": diagnostics.get("n_covariance_scenarios"),
            "Worst-case variance": diagnostics.get("worst_case_variance"),
            "Worst-case volatility": diagnostics.get("worst_case_volatility"),
            "Binding scenario index": diagnostics.get("worst_case_scenario_index"),
            "Binding scenario": diagnostics.get("worst_case_scenario_label"),
            "Variance spread across scenarios": (
                float(max(variances) - min(variances)) if variances else None
            ),
            "Estimated expected return": diagnostics.get("expected_return"),
            **common,
        }
    else:
        n = len(record.weights_after)
        fields = {
            "Target allocation": f"1/{n} = {1.0 / n:.1%} per asset",
            "Largest pre-rebalance drift": float(
                (record.weights_before - record.weights_after).abs().max()
            ),
            "Traded to restore equal weights": record.turnover,
            "Estimated expected return": diagnostics.get("expected_return"),
        }

    return ModelDiagnostics(model, MODEL_EXPLANATIONS[model], fields)


# ---------------------------------------------------------------------------
# Factual interpretation
# ---------------------------------------------------------------------------


def interpretation_statements(
    label_a: str,
    result_a: BacktestResult,
    label_b: str,
    result_b: BacktestResult,
    limit_a: float | None = None,
    limit_b: float | None = None,
) -> list[str]:
    """Factual observations about how the two strategies differed.

    Every statement is a direct restatement of a computed quantity. Nothing here
    asserts causation, ranks the strategies, or characterises a model's
    behaviour beyond what the numbers show -- the one interpretive phrasing
    used, "consistent with", is hedged deliberately.
    """
    statements: list[str] = []

    conc_a, conc_b = concentration_summary(result_a), concentration_summary(result_b)
    if abs(conc_a["avg_hhi"] - conc_b["avg_hhi"]) > 0.005:
        higher, lower = (
            (label_a, label_b) if conc_a["avg_hhi"] > conc_b["avg_hhi"] else (label_b, label_a)
        )
        statements.append(
            f"**{higher}** held a more concentrated portfolio than **{lower}** on "
            f"average (HHI {max(conc_a['avg_hhi'], conc_b['avg_hhi']):.3f} vs "
            f"{min(conc_a['avg_hhi'], conc_b['avg_hhi']):.3f})."
        )

    turn_a = turnover_diagnostics(result_a, limit_a)
    turn_b = turnover_diagnostics(result_b, limit_b)
    if turn_a["n_rebalances"] and turn_b["n_rebalances"]:
        statements.append(
            f"**{label_a}** changed {turn_a['avg_turnover']:.1%} of its portfolio per "
            f"rebalance versus {turn_b['avg_turnover']:.1%} for **{label_b}**."
        )
    for label, turn in ((label_a, turn_a), (label_b, turn_b)):
        if turn["limit"] is not None and turn["n_binding"]:
            statements.append(
                f"The turnover limit bound on {turn['n_binding']} of "
                f"{turn['n_rebalances']} **{label}** rebalances "
                f"({turn['pct_binding']:.0%})."
            )
        elif turn["limit"] is not None:
            statements.append(
                f"**{label}**'s turnover limit of {turn['limit']:.0%} never bound, so "
                f"it did not constrain any decision."
            )

    allocation = average_allocation_comparison(result_a, result_b)
    if not allocation.empty:
        top = allocation.iloc[0]
        if abs(top["difference"]) > 0.01:
            more, less = (label_a, label_b) if top["difference"] > 0 else (label_b, label_a)
            statements.append(
                f"**{more}** allocated an average of "
                f"{abs(top['difference']) * 100:.1f} percentage points more to "
                f"{allocation.index[0]} than **{less}**."
            )

    date, _ = largest_disagreement(result_a, result_b)
    if date is not None:
        distances = allocation_distance_series(result_a, result_b)
        statements.append(
            f"The two strategies differed most in {date:%B %Y}, when "
            f"{distances.max():.1%} of the portfolio was allocated differently."
        )

    for label, result in ((label_a, result_a), (label_b, result_b)):
        accuracy = expectation_accuracy(expected_vs_realised(result))
        if accuracy["n"]:
            statements.append(
                f"**{label}**'s expected return exceeded its following-period "
                f"realised return on {accuracy['n_overshot']} of {accuracy['n']} "
                f"decisions."
            )

    shortfalls_a = _shortfall_count(result_a)
    shortfalls_b = _shortfall_count(result_b)
    for label, count, result in (
        (label_a, shortfalls_a, result_a),
        (label_b, shortfalls_b, result_b),
    ):
        if count:
            statements.append(
                f"**{label}** could not reach its return target on {count} of "
                f"{len(result.rebalances)} decisions; the shortfall is reported "
                f"rather than the target being dropped."
            )

    if conc_a["avg_hhi"] > conc_b["avg_hhi"] * 1.5 and turn_a["avg_turnover"] > turn_b["avg_turnover"]:
        statements.append(
            f"**{label_a}** was both more concentrated and traded more than "
            f"**{label_b}**. This pattern is consistent with greater sensitivity "
            f"to estimated inputs, though a single historical path cannot "
            f"establish that."
        )

    return statements


def _shortfall_count(result: BacktestResult) -> int:
    return sum(
        1
        for r in result.rebalances
        if (r.diagnostics.get("return_shortfall") or 0.0) > 0
    )


def _as_array(weights: pd.Series | np.ndarray) -> np.ndarray:
    if isinstance(weights, pd.Series):
        return weights.to_numpy(dtype="float64")
    return np.asarray(weights, dtype="float64")
