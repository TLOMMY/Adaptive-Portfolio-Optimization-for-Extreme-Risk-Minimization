"""Equal-weight benchmark.

The 1/N portfolio is the reference every optimized model is measured against. It
uses no estimated parameters at all, which makes it immune to estimation error --
a genuinely hard benchmark to beat, and the reason it belongs in the comparison
rather than serving as a straw man.

It is implemented against the same interface and receives the same
``MarketDataView`` as every other model, so the comparison stays controlled.
"""

from __future__ import annotations

import numpy as np

from src.backtest.strategy import RebalanceContext
from src.estimation.parameters import EstimatedParameters
from src.portfolio.base import OptimizationOutcome, PortfolioOptimizer
from src.portfolio.constraints import ConstraintError


class EqualWeightOptimizer(PortfolioOptimizer):
    r"""Allocate :math:`x_i = 1/N` to each of the *N* assets.

    No optimization is performed. The constraint set is still validated, and a
    ``max_weight`` below :math:`1/N` is reported as an error rather than
    silently violated.
    """

    name = "Equal Weight"

    def _solve(
        self, parameters: EstimatedParameters, context: RebalanceContext
    ) -> OptimizationOutcome:
        n = len(parameters.tickers)
        weight = 1.0 / n

        if weight > self.constraints.max_weight + 1e-12:
            raise ConstraintError(
                f"equal weight {weight:.4f} exceeds max_weight="
                f"{self.constraints.max_weight} across {n} assets"
            )

        for cls, limit in self.constraints.asset_class_limits.items():
            members = [t for t in self.asset_class_map.get(cls, []) if t in parameters.tickers]
            exposure = weight * len(members)
            if exposure > limit + 1e-12:
                raise ConstraintError(
                    f"equal weight puts {exposure:.4f} in asset class {cls!r}, "
                    f"above its limit of {limit}"
                )

        return OptimizationOutcome(
            weights=np.full(n, weight),
            status="analytic",
            solver="none",
            diagnostics={"n_assets": n},
        )
