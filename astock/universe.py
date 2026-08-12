"""Discovery of the tradable A-share universe.

Tencent has no public "list every stock" endpoint, so the universe is
discovered by probing the documented code ranges of each exchange in batches
and keeping the symbols that resolve to a real A-share instrument.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from .sources.tencent import Quote, TencentSource

# (prefix, market, first, last) — inclusive numeric suffix ranges.
CODE_RANGES: tuple[tuple[str, str, int, int], ...] = (
    ("sh", "主板", 600000, 605999),
    ("sh", "科创板", 688000, 689999),
    ("sz", "主板", 1, 3999),
    ("sz", "创业板", 300000, 301999),
    ("bj", "北交所", 430000, 439999),
    ("bj", "北交所", 830000, 839999),
    ("bj", "北交所", 870000, 879999),
    ("bj", "北交所", 920000, 920999),
)

# 沪深 A 股为 GP-A / GP-A-CYB / GP-A-KCB，北交所标记为 GP。
A_SHARE_KINDS = ("GP-A",)
BEIJING_KINDS = ("GP",)


def candidate_symbols() -> Iterator[str]:
    for prefix, _label, first, last in CODE_RANGES:
        for number in range(first, last + 1):
            yield f"{prefix}{number:06d}"


def is_a_share(quote: Quote) -> bool:
    kinds = BEIJING_KINDS if quote.code.startswith("bj") else A_SHARE_KINDS
    return quote.kind.startswith(kinds) and quote.price > 0


def discover(
    source: TencentSource,
    batch_size: int = 60,
    progress: Callable[[int, int], None] | None = None,
) -> list[Quote]:
    """Probe every candidate symbol and return the ones that are A-shares."""
    symbols = list(candidate_symbols())
    found: list[Quote] = []
    for start in range(0, len(symbols), batch_size):
        batch = symbols[start : start + batch_size]
        try:
            quotes = source.quotes(batch)
        except Exception:  # a single bad batch must not abort a long scan
            continue
        found.extend(q for q in quotes if is_a_share(q))
        if progress:
            progress(min(start + batch_size, len(symbols)), len(symbols))
    return found
