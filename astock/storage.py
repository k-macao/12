"""SQLite persistence for quotes, candles and the tradable universe."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .sources.tencent import Candle, Quote

SCHEMA = """
CREATE TABLE IF NOT EXISTS stocks (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    code TEXT NOT NULL,
    time TEXT NOT NULL,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    prev_close REAL NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    change REAL NOT NULL,
    change_pct REAL NOT NULL,
    volume REAL NOT NULL,
    amount REAL NOT NULL,
    turnover_rate REAL NOT NULL,
    pe_ttm REAL NOT NULL,
    pb REAL NOT NULL,
    float_mcap REAL NOT NULL,
    total_mcap REAL NOT NULL,
    amplitude REAL NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, time)
);
CREATE INDEX IF NOT EXISTS idx_quotes_time ON quotes(time);

CREATE TABLE IF NOT EXISTS candles (
    code TEXT NOT NULL,
    period TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    close REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (code, period, date)
);
"""

DEFAULT_DB = Path("data/astock.db")


class Storage:
    def __init__(self, path: str | Path = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._conn:
            yield self._conn

    # --- writes -------------------------------------------------------
    def save_stocks(self, stocks: Iterable[tuple[str, str, str]]) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        rows = [(code, name, code[:2], kind, now) for code, name, kind in stocks]
        with self._tx() as conn:
            conn.executemany(
                "INSERT INTO stocks(code, name, market, kind, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(code) DO UPDATE SET name=excluded.name, kind=excluded.kind, "
                "updated_at=excluded.updated_at",
                rows,
            )
        return len(rows)

    def save_quotes(self, quotes: Sequence[Quote]) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        rows = [
            (
                q.code, q.time, q.name, q.price, q.prev_close, q.open, q.high, q.low,
                q.change, q.change_pct, q.volume, q.amount, q.turnover_rate, q.pe_ttm,
                q.pb, q.float_mcap, q.total_mcap, q.amplitude, q.kind, now,
            )
            for q in quotes
        ]
        with self._tx() as conn:
            conn.executemany(
                "INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(code, time) DO UPDATE SET price=excluded.price, "
                "change=excluded.change, change_pct=excluded.change_pct, "
                "volume=excluded.volume, amount=excluded.amount, fetched_at=excluded.fetched_at",
                rows,
            )
            conn.executemany(
                "INSERT INTO stocks(code, name, market, kind, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(code) DO UPDATE SET name=excluded.name, kind=excluded.kind",
                [(q.code, q.name, q.code[:2], q.kind, now) for q in quotes],
            )
        return len(rows)

    def save_candles(self, code: str, period: str, candles: Sequence[Candle]) -> int:
        rows = [
            (code, period, c.date, c.open, c.close, c.high, c.low, c.volume) for c in candles
        ]
        with self._tx() as conn:
            conn.executemany(
                "INSERT INTO candles VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(code, period, date) DO UPDATE SET open=excluded.open, "
                "close=excluded.close, high=excluded.high, low=excluded.low, "
                "volume=excluded.volume",
                rows,
            )
        return len(rows)

    # --- reads --------------------------------------------------------
    def latest_quotes(self, limit: int = 50, offset: int = 0, order_by: str = "change_pct",
                      desc: bool = True, keyword: str | None = None) -> list[dict]:
        allowed = {
            "change_pct", "price", "amount", "volume", "turnover_rate",
            "total_mcap", "pe_ttm", "code",
        }
        if order_by not in allowed:
            raise ValueError(f"unsupported sort column: {order_by}")
        where, params = "", []
        if keyword:
            where = "WHERE q.code LIKE ? OR q.name LIKE ?"
            params = [f"%{keyword}%", f"%{keyword}%"]
        sql = f"""
            SELECT q.* FROM quotes q
            JOIN (SELECT code, MAX(time) AS time FROM quotes GROUP BY code) latest
              ON q.code = latest.code AND q.time = latest.time
            {where}
            ORDER BY q.{order_by} {"DESC" if desc else "ASC"}
            LIMIT ? OFFSET ?
        """
        rows = self._conn.execute(sql, [*params, limit, offset]).fetchall()
        return [dict(row) for row in rows]

    def quote_history(self, code: str, limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM quotes WHERE code = ? ORDER BY time DESC LIMIT ?", (code, limit)
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def candles(self, code: str, period: str = "day", limit: int = 320) -> list[dict]:
        rows = self._conn.execute(
            "SELECT date, open, close, high, low, volume FROM candles "
            "WHERE code = ? AND period = ? ORDER BY date DESC LIMIT ?",
            (code, period, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def stocks(self, keyword: str | None = None, limit: int = 50) -> list[dict]:
        if keyword:
            rows = self._conn.execute(
                "SELECT * FROM stocks WHERE code LIKE ? OR name LIKE ? ORDER BY code LIMIT ?",
                (f"%{keyword}%", f"%{keyword}%", limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM stocks ORDER BY code LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict:
        row = self._conn.execute(
            "SELECT (SELECT COUNT(*) FROM stocks) AS stocks, "
            "(SELECT COUNT(*) FROM quotes) AS quotes, "
            "(SELECT COUNT(*) FROM candles) AS candles, "
            "(SELECT MAX(fetched_at) FROM quotes) AS last_fetch"
        ).fetchone()
        return dict(row)
