"""Fetch jobs that glue the data source to storage."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from datetime import time as dtime
from pathlib import Path

from .sources.tencent import DataSourceError, Quote, TencentSource, normalize_code
from .storage import Storage
from .universe import discover

log = logging.getLogger("astock")

MORNING = (dtime(9, 15), dtime(11, 35))
AFTERNOON = (dtime(12, 55), dtime(15, 5))

DEFAULT_WATCHLIST = Path("watchlist.txt")


def is_market_open(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    current = now.time()
    return any(start <= current <= end for start, end in (MORNING, AFTERNOON))


def load_watchlist(path: str | Path = DEFAULT_WATCHLIST) -> list[str]:
    file = Path(path)
    if not file.exists():
        return []
    codes = []
    for line in file.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            codes.append(normalize_code(entry))
    return codes


@dataclass
class FetchResult:
    quotes: int = 0
    candles: int = 0
    stocks: int = 0
    errors: int = 0


class Collector:
    def __init__(self, storage: Storage, source: TencentSource | None = None):
        self.storage = storage
        self.source = source or TencentSource()

    def close(self) -> None:
        self.source.close()

    def sync_universe(self, verbose: bool = True) -> FetchResult:
        """Discover all listed A-shares and persist them with a snapshot quote."""

        def progress(done: int, total: int) -> None:
            if verbose and done % 3000 == 0:
                log.info("universe scan %s/%s", done, total)

        quotes = discover(self.source, progress=progress)
        self.storage.save_stocks([(q.code, q.name, q.kind) for q in quotes])
        self.storage.save_quotes(quotes)
        return FetchResult(quotes=len(quotes), stocks=len(quotes))

    def target_codes(self, codes: list[str] | None = None, limit: int | None = None) -> list[str]:
        if codes:
            return [normalize_code(c) for c in codes]
        known = [row["code"] for row in self.storage.stocks(limit=limit or 100000)]
        return known or load_watchlist()

    def fetch_quotes(self, codes: list[str] | None = None) -> FetchResult:
        targets = self.target_codes(codes)
        if not targets:
            raise DataSourceError("no stock codes to fetch; run `sync-universe` first")
        quotes: list[Quote] = self.source.quotes(targets)
        saved = self.storage.save_quotes(quotes)
        return FetchResult(quotes=saved)

    def fetch_candles(self, codes: list[str], period: str = "day", count: int = 320) -> FetchResult:
        result = FetchResult()
        for code in codes:
            try:
                candles = self.source.kline(code, period=period, count=count)
            except Exception as exc:
                log.warning("kline failed for %s: %s", code, exc)
                result.errors += 1
                continue
            result.candles += self.storage.save_candles(normalize_code(code), period, candles)
        return result

    def run_forever(self, interval: int = 60, codes: list[str] | None = None,
                    only_when_open: bool = True) -> None:
        """Poll quotes on a fixed interval until interrupted."""
        while True:
            try:
                if only_when_open and not is_market_open():
                    log.info("market closed, sleeping")
                else:
                    result = self.fetch_quotes(codes)
                    log.info("saved %s quotes", result.quotes)
            except Exception as exc:
                log.warning("fetch cycle failed: %s", exc)
            time.sleep(interval)
