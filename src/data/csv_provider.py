"""CSV snapshot provider -- the reproducible, offline default.

The committed snapshot under ``data/snapshots/`` is what makes this project
reproducible: results do not depend on network availability, on a vendor's
rate limiting, or on a vendor silently restating history.  ``scripts/fetch_data.py``
regenerates it.

Expected file format: a wide CSV whose first column is the date and whose
remaining columns are tickers holding adjusted closes.

    date,SPY,IJR,...
    2004-11-18,86.42,...
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.config.settings import DEFAULT_SNAPSHOT
from src.data.provider import DATE_INDEX_NAME, DataProviderError, MarketDataProvider


class CsvProvider(MarketDataProvider):
    """Load adjusted prices from a local CSV snapshot."""

    name = "csv"

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_SNAPSHOT

    def _fetch(self, tickers: list[str], start: date | None, end: date | None) -> pd.DataFrame:
        if not self.path.exists():
            raise DataProviderError(
                f"snapshot not found at {self.path}. "
                "Run `python scripts/fetch_data.py` to generate it."
            )

        panel = pd.read_csv(self.path, index_col=0, parse_dates=[0])
        panel.index.name = DATE_INDEX_NAME

        missing = [t for t in tickers if t not in panel.columns]
        if missing:
            raise DataProviderError(
                f"snapshot {self.path.name} has no column(s) for {missing}. "
                f"Available: {sorted(panel.columns)[:20]}"
            )

        panel = panel.loc[:, tickers]

        # Inclusive slicing on both bounds, matching the provider contract.
        if start is not None:
            panel = panel.loc[panel.index >= pd.Timestamp(start)]
        if end is not None:
            panel = panel.loc[panel.index <= pd.Timestamp(end)]

        if panel.empty:
            raise DataProviderError(
                f"snapshot {self.path.name} has no rows in [{start}, {end}]"
            )
        return panel

    @staticmethod
    def write_snapshot(panel: pd.DataFrame, path: Path | str) -> Path:
        """Persist a validated panel in the snapshot format."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        out = panel.copy()
        out.index.name = DATE_INDEX_NAME
        out.to_csv(path, float_format="%.6f")
        return path
