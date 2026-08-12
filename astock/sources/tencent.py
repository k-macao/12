"""Tencent (gtimg) market data source for A-share quotes and candlesticks."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime

import httpx

QUOTE_URL = "https://qt.gtimg.cn/q="
KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
SEARCH_URL = "https://smartbox.gtimg.cn/s3/"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15.0
QUOTE_BATCH_SIZE = 60

_QUOTE_LINE = re.compile(r'v_([a-z]{2}\d{6})="([^"]*)"')
_HINT_LINE = re.compile(r'v_hint="([^"]*)"')

PERIODS = {
    "day": ("day", "qfqday"),
    "week": ("week", "qfqweek"),
    "month": ("month", "qfqmonth"),
}


class DataSourceError(RuntimeError):
    """Raised when the upstream market data service returns unusable data."""


@dataclass(frozen=True)
class Quote:
    code: str
    name: str
    price: float
    prev_close: float
    open: float
    high: float
    low: float
    change: float
    change_pct: float
    volume: float  # 股
    amount: float  # 元
    turnover_rate: float  # %
    pe_ttm: float
    pb: float
    float_mcap: float  # 亿元
    total_mcap: float  # 亿元
    amplitude: float  # %
    kind: str  # e.g. GP-A, GP-A-CYB, ZS (index)
    time: str  # ISO 8601

    def as_dict(self) -> dict:
        return asdict(self)


def normalize_code(code: str) -> str:
    """Return a ``sh600000`` style symbol for user input such as ``600000``.

    Raises ``ValueError`` when the code cannot be mapped to a market.
    """
    raw = code.strip().lower().replace(".", "")
    if raw.startswith(("sh", "sz", "bj")) and len(raw) == 8 and raw[2:].isdigit():
        return raw
    if raw.endswith(("ss", "sh", "sz", "bj")) and raw[:6].isdigit():
        suffix = raw[6:]
        return ("sh" if suffix in {"ss", "sh"} else suffix) + raw[:6]
    if len(raw) == 6 and raw.isdigit():
        return market_of(raw) + raw
    raise ValueError(f"unrecognised stock code: {code!r}")


def market_of(digits: str) -> str:
    """Map a bare 6-digit code to its exchange prefix."""
    if digits.startswith(("600", "601", "603", "605", "688", "689", "900")):
        return "sh"
    if digits.startswith(("000", "001", "002", "003", "300", "301", "200")):
        return "sz"
    if digits.startswith(("4", "8", "920")):
        return "bj"
    return "sh"


def _to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_time(value: str) -> str:
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(value, fmt).isoformat()
        except ValueError:
            continue
    return datetime.now().isoformat(timespec="seconds")


def _volume_in_shares(raw_volume: float, amount: float, low: float, high: float) -> float:
    """Normalise the volume field to shares.

    Most boards report lots (1 lot = 100 shares) but STAR market symbols report
    raw shares, so pick whichever reading implies an average price inside the
    day's range.
    """
    if raw_volume <= 0:
        return 0.0
    if amount > 0 and low > 0:
        as_shares = amount / raw_volume
        if low * 0.9 <= as_shares <= high * 1.1:
            return raw_volume
    return raw_volume * 100


def _amount_from_detail(field: str, fallback_wan: float) -> float:
    parts = field.split("/")
    if len(parts) == 3:
        exact = _to_float(parts[2])
        if exact > 0:
            return exact
    return fallback_wan * 10000.0


def parse_quote_payload(text: str) -> list[Quote]:
    """Parse the ``v_sh600000="..."`` payload returned by qt.gtimg.cn."""
    quotes: list[Quote] = []
    for symbol, body in _QUOTE_LINE.findall(text):
        fields = body.split("~")
        if len(fields) < 46 or not fields[1]:
            continue
        low, high = _to_float(fields[34]), _to_float(fields[33])
        amount = _amount_from_detail(fields[35], _to_float(fields[37]))
        volume = _volume_in_shares(_to_float(fields[6]), amount, low, high)
        quotes.append(
            Quote(
                code=symbol,
                name=fields[1],
                price=_to_float(fields[3]),
                prev_close=_to_float(fields[4]),
                open=_to_float(fields[5]),
                high=high,
                low=low,
                change=_to_float(fields[31]),
                change_pct=_to_float(fields[32]),
                volume=volume,
                amount=amount,
                turnover_rate=_to_float(fields[38]),
                pe_ttm=_to_float(fields[39]),
                pb=_to_float(fields[46]),
                float_mcap=_to_float(fields[44]),
                total_mcap=_to_float(fields[45]),
                amplitude=_to_float(fields[43]),
                kind=fields[61].strip() if len(fields) > 61 else "",
                time=_parse_time(fields[30]),
            )
        )
    return quotes


@dataclass(frozen=True)
class Candle:
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: float

    def as_dict(self) -> dict:
        return asdict(self)


def parse_kline_payload(payload: dict, symbol: str, period: str) -> list[Candle]:
    data = payload.get("data", {}).get(symbol)
    if not data:
        raise DataSourceError(f"no kline data for {symbol}")
    plain, adjusted = PERIODS[period]
    rows = data.get(adjusted) or data.get(plain) or []
    candles = []
    for row in rows:
        if len(row) < 6:
            continue
        candles.append(
            Candle(
                date=str(row[0]),
                open=_to_float(row[1]),
                close=_to_float(row[2]),
                high=_to_float(row[3]),
                low=_to_float(row[4]),
                volume=_to_float(row[5]),
            )
        )
    return candles


def _chunks(items: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class TencentSource:
    """Thin synchronous client over Tencent's public market data endpoints."""

    def __init__(self, client: httpx.Client | None = None, timeout: float = DEFAULT_TIMEOUT):
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Referer": "https://finance.qq.com/"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TencentSource:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def quotes(self, codes: Iterable[str]) -> list[Quote]:
        symbols = [normalize_code(code) for code in codes]
        results: list[Quote] = []
        for batch in _chunks(symbols, QUOTE_BATCH_SIZE):
            response = self._client.get(QUOTE_URL + ",".join(batch))
            response.raise_for_status()
            results.extend(parse_quote_payload(response.content.decode("gbk", "ignore")))
        return results

    def quote(self, code: str) -> Quote:
        found = self.quotes([code])
        if not found:
            raise DataSourceError(f"no quote for {code}")
        return found[0]

    def kline(self, code: str, period: str = "day", count: int = 320) -> list[Candle]:
        if period not in PERIODS:
            raise ValueError(f"unsupported period: {period}")
        symbol = normalize_code(code)
        params = {"param": f"{symbol},{PERIODS[period][0]},,,{count},qfq"}
        response = self._client.get(KLINE_URL, params=params)
        response.raise_for_status()
        return parse_kline_payload(response.json(), symbol, period)

    def search(self, keyword: str, limit: int = 10) -> list[dict]:
        """Look up stocks by code, name or pinyin abbreviation."""
        response = self._client.get(SEARCH_URL, params={"q": keyword, "t": "all"})
        response.raise_for_status()
        text = response.content.decode("gbk", "ignore")
        match = _HINT_LINE.search(text)
        if not match:
            return []
        hits = []
        for entry in match.group(1).split("^"):
            parts = entry.split("~")
            if len(parts) < 5 or parts[0] not in {"sh", "sz", "bj"}:
                continue
            if not parts[4].startswith("GP-A"):
                continue
            hits.append(
                {
                    "code": parts[0] + parts[1],
                    "name": json.loads(f'"{parts[2]}"') if "\\u" in parts[2] else parts[2],
                    "pinyin": parts[3],
                }
            )
            if len(hits) >= limit:
                break
        return hits


def trading_day(now: datetime | None = None) -> date:
    return (now or datetime.now()).date()
