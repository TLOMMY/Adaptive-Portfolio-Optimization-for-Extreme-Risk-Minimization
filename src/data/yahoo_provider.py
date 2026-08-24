"""Yahoo Finance provider.

Two acquisition paths are attempted in order:

1. ``yfinance``, when importable and functional;
2. a direct call to Yahoo's public chart endpoint with an explicit browser
   ``User-Agent``.

The fallback exists because Yahoo rejects requests carrying default programmatic
user agents from some networks (observed: HTTP 429 with the stdlib UA, HTTP 200
with a browser UA from the same host).  Neither path is a dependency of the demo
itself -- the application defaults to the committed CSV snapshot -- but a working
network path is needed to *produce* that snapshot.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime

import pandas as pd

from src.data.cache import ParquetCache, cache_key
from src.data.provider import DataProviderError, MarketDataProvider

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


def _to_epoch(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


class YahooProvider(MarketDataProvider):
    """Fetch adjusted closes from Yahoo Finance, with local caching."""

    name = "yahoo"

    def __init__(
        self,
        cache: ParquetCache | None = None,
        use_cache: bool = True,
        prefer_yfinance: bool = True,
        request_pause: float = 0.4,
        timeout: int = 30,
    ) -> None:
        self.cache = cache if cache is not None else ParquetCache()
        self.use_cache = use_cache
        self.prefer_yfinance = prefer_yfinance
        self.request_pause = request_pause
        self.timeout = timeout

    # -- public fetch path ---------------------------------------------------

    def _fetch(self, tickers: list[str], start: date | None, end: date | None) -> pd.DataFrame:
        key = cache_key(self.name, tickers, start, end)
        if self.use_cache:
            cached = self.cache.load(key)
            if cached is not None:
                return cached

        panel = None
        if self.prefer_yfinance:
            try:
                panel = self._fetch_via_yfinance(tickers, start, end)
            except Exception as exc:
                logger.warning("yfinance path failed (%s); falling back to direct HTTP", exc)

        if panel is None or panel.empty:
            panel = self._fetch_via_http(tickers, start, end)

        if self.use_cache:
            self.cache.store(key, panel)
        return panel

    # -- path 1: yfinance ----------------------------------------------------

    def _fetch_via_yfinance(
        self, tickers: list[str], start: date | None, end: date | None
    ) -> pd.DataFrame:
        import yfinance as yf

        raw = yf.download(
            tickers=tickers,
            start=start,
            # yfinance treats `end` as exclusive; extend by a day so the caller's
            # inclusive contract holds.
            end=(end + pd.Timedelta(days=1)).date() if end is not None else None,
            auto_adjust=True,
            progress=False,
            actions=False,
            threads=False,
        )
        if raw is None or raw.empty:
            raise DataProviderError("yfinance returned no data")

        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" not in raw.columns.get_level_values(0):
                raise DataProviderError("yfinance response has no Close level")
            panel = raw["Close"]
        else:
            if "Close" not in raw.columns:
                raise DataProviderError("yfinance response has no Close column")
            panel = raw[["Close"]].rename(columns={"Close": tickers[0]})

        missing = [t for t in tickers if t not in panel.columns]
        if missing:
            raise DataProviderError(f"yfinance did not return: {missing}")
        return panel.loc[:, tickers]

    # -- path 2: direct HTTP -------------------------------------------------

    def _fetch_via_http(
        self, tickers: list[str], start: date | None, end: date | None
    ) -> pd.DataFrame:
        series: dict[str, pd.Series] = {}
        failures: dict[str, str] = {}

        for i, ticker in enumerate(tickers):
            if i:
                time.sleep(self.request_pause)
            try:
                series[ticker] = self._fetch_one_http(ticker, start, end)
            except Exception as exc:
                failures[ticker] = str(exc)
                logger.error("Direct fetch failed for %s: %s", ticker, exc)

        if failures:
            raise DataProviderError(f"could not fetch {list(failures)}: {failures}")

        panel = pd.DataFrame(series)
        return panel.loc[:, tickers]

    def _fetch_one_http(self, ticker: str, start: date | None, end: date | None) -> pd.Series:
        params = [
            f"period1={_to_epoch(start) if start else 0}",
            f"period2={_to_epoch(end) if end else int(time.time())}",
            "interval=1d",
            "events=div%2Csplit",
        ]
        url = CHART_URL.format(ticker=ticker) + "?" + "&".join(params)
        request = urllib.request.Request(url, headers={"User-Agent": BROWSER_USER_AGENT})

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise DataProviderError(f"HTTP {exc.code} for {ticker}") from exc

        chart = payload.get("chart") or {}
        if chart.get("error"):
            raise DataProviderError(f"vendor error for {ticker}: {chart['error']}")
        results = chart.get("result")
        if not results:
            raise DataProviderError(f"empty result for {ticker}")

        result = results[0]
        timestamps = result.get("timestamp")
        if not timestamps:
            raise DataProviderError(f"no timestamps for {ticker}")

        adjclose_block = (result.get("indicators") or {}).get("adjclose")
        if not adjclose_block or "adjclose" not in adjclose_block[0]:
            raise DataProviderError(f"no adjusted close for {ticker}")
        values = adjclose_block[0]["adjclose"]

        index = pd.DatetimeIndex(
            [datetime.fromtimestamp(ts, tz=UTC) for ts in timestamps]
        ).tz_convert(None).normalize()

        return pd.Series(values, index=index, name=ticker, dtype="float64")
