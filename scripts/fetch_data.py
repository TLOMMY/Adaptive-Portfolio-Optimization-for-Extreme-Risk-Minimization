"""Refresh the local cache and regenerate the committed price snapshot.

The snapshot is the project's reproducibility artefact: the application reads it
by default, so a demo or a grader's re-run does not depend on network access or
on a vendor's rate limits.

Usage
-----
    python scripts/fetch_data.py                    # default universe
    python scripts/fetch_data.py --start 2000-01-01
    python scripts/fetch_data.py --no-cache         # force a live refetch
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.assets import DEFAULT_UNIVERSE, UNIVERSES  # noqa: E402
from src.config.settings import DEFAULT_SNAPSHOT, SNAPSHOT_DIR  # noqa: E402
from src.data.csv_provider import CsvProvider  # noqa: E402
from src.data.yahoo_provider import YahooProvider  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--universe", default=DEFAULT_UNIVERSE.name, choices=sorted(UNIVERSES))
    p.add_argument("--start", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
                   default=date(2004, 1, 1),
                   help="Earliest date to fetch (default 2004-01-01: comfortably ahead "
                        "of the earliest estimation window the default experiment needs).")
    p.add_argument("--end", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(name)s: %(message)s",
    )
    log = logging.getLogger("fetch_data")

    universe = UNIVERSES[args.universe]
    out_path = args.out or (
        DEFAULT_SNAPSHOT
        if universe is DEFAULT_UNIVERSE
        else SNAPSHOT_DIR / f"prices_{universe.name.lower().replace(' ', '_')}.csv"
    )

    log.info("Universe: %s (%d assets)", universe.name, len(universe.assets))
    log.info("Fetching %s -> %s", args.start, args.end or "latest")

    provider = YahooProvider(use_cache=not args.no_cache)
    panel = provider.get_adjusted_prices(universe.tickers, start=args.start, end=args.end)

    log.info("Fetched %d rows, %s to %s",
             len(panel), panel.index.min().date(), panel.index.max().date())

    # The vendor returns a partial bar for the session in progress. Including it
    # would put an incomplete price into a reproducibility artefact, so the
    # current day is dropped unless an explicit --end was requested.
    if args.end is None and not panel.empty:
        today = date.today()
        if panel.index.max().date() >= today:
            panel = panel.loc[panel.index.date < today]
            log.info("Dropped in-progress session(s) >= %s; snapshot now ends %s",
                     today, panel.index.max().date())

    missing = panel.isna().sum()
    if missing.any():
        log.info("Leading gaps per asset:\n%s", missing[missing > 0].to_string())

    # Verify the snapshot actually supports the configured experiment. An asset
    # legitimately starts at max(its inception, the requested start); only a later
    # start than that indicates missing history.
    for asset in universe.assets:
        first_real = panel[asset.ticker].first_valid_index()
        if first_real is None:
            log.error("%s: no data at all", asset.ticker)
            return 1
        expected = max(asset.inception, args.start)
        # A few days' slack absorbs weekends and market holidays around the
        # expected first date; a larger gap indicates genuinely missing history.
        gap_days = (first_real.date() - expected).days
        if gap_days > 7:
            log.warning(
                "%s: data starts %s, %d days later than expected %s (inception %s)",
                asset.ticker, first_real.date(), gap_days, expected, asset.inception,
            )

    written = CsvProvider.write_snapshot(panel, out_path)
    size_kb = written.stat().st_size / 1024
    log.info("Wrote snapshot: %s (%.1f KB)", written, size_kb)

    # Round-trip check: the committed artefact must load back through the
    # provider contract cleanly, or it is not a reproducibility artefact.
    reloaded = CsvProvider(written).get_adjusted_prices(universe.tickers)
    log.info("Round-trip OK: %d rows, %d columns", len(reloaded), reloaded.shape[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
