"""Predefined historical evaluation periods.

These support **historical subperiod robustness analysis**: running the identical
experiment over different stretches of history to see whether conclusions hold
across them. They are not evidence of future generalisability -- each period is
still a single realised path, and three subperiods of one decade are three
overlapping views of the same decade.

The estimation lookback extends *before* each evaluation period's start, exactly
as it does for the full period. Every other setting -- universe, lookback length,
rebalance cadence, estimators, constraints -- is held fixed. Parameters are never
retuned per period.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class EvaluationPeriod:
    """One named evaluation window."""

    key: str
    label: str
    start: date
    end: date
    description: str

    @property
    def years(self) -> float:
        return (self.end - self.start).days / 365.25


FULL = EvaluationPeriod(
    key="full",
    label="Full period (2016-2024)",
    start=date(2016, 1, 1),
    end=date(2024, 12, 31),
    description="Nine years spanning several distinct market environments.",
)

PERIOD_A = EvaluationPeriod(
    key="a",
    label="2016-2018",
    start=date(2016, 1, 1),
    end=date(2018, 12, 31),
    description="Subperiod A.",
)

PERIOD_B = EvaluationPeriod(
    key="b",
    label="2019-2021",
    start=date(2019, 1, 1),
    end=date(2021, 12, 31),
    description="Subperiod B.",
)

PERIOD_C = EvaluationPeriod(
    key="c",
    label="2022-2024",
    start=date(2022, 1, 1),
    end=date(2024, 12, 31),
    description="Subperiod C.",
)

PERIODS: dict[str, EvaluationPeriod] = {
    p.key: p for p in (FULL, PERIOD_A, PERIOD_B, PERIOD_C)
}

DEFAULT_PERIOD = FULL
