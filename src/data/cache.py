"""Local parquet cache for fetched price panels.

The cache is a pure performance/robustness layer: it never changes the data a
provider returns, and a cache miss is always recoverable by refetching.  Cache
files are machine-local and gitignored; the *committed* reproducibility artefact
is the CSV snapshot under ``data/snapshots/`` (see ``csv_provider``).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from src.config.settings import CACHE_DIR

logger = logging.getLogger(__name__)


def cache_key(source: str, tickers: list[str], start: date | None, end: date | None) -> str:
    """Stable filename-safe key for one request.

    Ticker order is normalised so that logically identical requests share a key.
    """
    payload = "|".join(
        [source, ",".join(sorted(tickers)), str(start or "min"), str(end or "max")]
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"{source}_{digest}"


class ParquetCache:
    """Read/write price panels to parquet files under a cache directory."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else CACHE_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.parquet"

    def load(self, key: str) -> pd.DataFrame | None:
        path = self.path_for(key)
        if not path.exists():
            return None
        try:
            panel = pd.read_parquet(path)
        except Exception as exc:  # pragma: no cover - corrupt cache is recoverable
            logger.warning("Discarding unreadable cache file %s: %s", path, exc)
            path.unlink(missing_ok=True)
            return None
        logger.debug("Cache hit: %s", path)
        return panel

    def store(self, key: str, panel: pd.DataFrame) -> Path:
        path = self.path_for(key)
        panel.to_parquet(path)
        logger.debug("Cached panel to %s", path)
        return path

    def clear(self) -> int:
        """Delete all cached parquet files. Returns the number removed."""
        removed = 0
        for path in self.directory.glob("*.parquet"):
            path.unlink()
            removed += 1
        return removed
