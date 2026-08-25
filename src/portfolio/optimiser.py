"""Thin amplpy layer shared by every optimising model.

`ampl_solve` loads model/common.mod plus one model-specific file, fills the
sets and parameters it is given, runs the chosen solver and returns the weights
and any requested expression values.  It knows nothing about dates or backtests;
everything time-related lives in estimate.py and backtest.py so the look-ahead
rule is enforced in exactly one place.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from amplpy import AMPL, OutputHandler, modules

MODEL_DIR = Path(__file__).resolve().parents[2] / "model"
COMMON = MODEL_DIR / "common.mod"

SOLVER_OPTIONS = {
    "highs": "outlev=0 mip_rel_gap=1e-4 timelim=60",
    "gurobi": "outlev=0 mipgap=1e-3 timelim=120 feastol=1e-8 threads=2",
}

_ampl: AMPL | None = None


class _Quiet(OutputHandler):
    def output(self, kind, msg):
        pass


def _get_ampl() -> AMPL:
    """One AMPL session per process; creating one is slow, re-reading a model is not."""
    global _ampl
    if _ampl is None:
        modules.load()
        _ampl = AMPL()
        _ampl.set_output_handler(_Quiet())
        _ampl.option["solver_msg"] = 0
    return _ampl


@dataclass
class Solution:
    weights: pd.Series
    exp_return: float          # expected daily return, mu . w
    risk: float                # the model's own risk measure at the solution (CVaR or volatility)
    cvar: float                # realised CVaR of these weights over the scenarios (comparable across models)
    turnover: float            # sum of |trades| as a fraction of portfolio value
    status: str
    solve_time: float
    n_holdings: int = field(default=0)


def ampl_solve(
    model_file: Path,
    solver: str,
    sets: dict[str, list],
    params: dict[str, object],
    values: tuple[str, ...] = (),
) -> tuple[pd.Series, dict[str, float], str, float]:
    """Solve common.mod + model_file.  Returns (weights, {expr: value}, status, seconds)."""
    ampl = _get_ampl()
    ampl.reset()
    ampl.read(str(COMMON))
    ampl.read(str(model_file))
    ampl.option["solver"] = solver
    ampl.option[f"{solver}_options"] = SOLVER_OPTIONS.get(solver, "")
    for k, v in sets.items():
        ampl.set[k] = v
    for k, v in params.items():
        ampl.param[k] = v

    t0 = time.perf_counter()
    ampl.solve()
    dt = time.perf_counter() - t0
    status = ampl.solve_result
    # "limit" means the solver stopped on a time/iteration limit with a feasible incumbent
    # (AMPL solve_result_num 400-499); that solution is usable, just not proven optimal.
    if status not in ("solved", "limit"):
        raise RuntimeError(f"{solver} returned {status} on {model_file.name}")
    w = pd.Series(ampl.var["w"].to_dict())
    w[w.abs() < 1e-6] = 0.0
    return w, {v: float(ampl.get_value(v)) for v in values}, status, dt
