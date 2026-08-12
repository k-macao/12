from astock import universe
from astock.sources.tencent import Quote


def quote(code: str, kind: str, price: float = 10.0) -> Quote:
    return Quote(
        code=code, name="测试", price=price, prev_close=price, open=price, high=price,
        low=price, change=0.0, change_pct=0.0, volume=0.0, amount=0.0, turnover_rate=0.0,
        pe_ttm=0.0, pb=0.0, float_mcap=0.0, total_mcap=0.0, amplitude=0.0, kind=kind,
        time="2026-08-12T15:00:00",
    )


def test_is_a_share_accepts_all_boards():
    assert universe.is_a_share(quote("sh600000", "GP-A"))
    assert universe.is_a_share(quote("sz300750", "GP-A-CYB"))
    assert universe.is_a_share(quote("sh688981", "GP-A-KCB"))
    assert universe.is_a_share(quote("bj920002", "GP"))


def test_is_a_share_rejects_non_stocks_and_delisted():
    assert not universe.is_a_share(quote("sh000001", "ZS"))  # 指数
    assert not universe.is_a_share(quote("sh510300", "JJ"))  # ETF
    assert not universe.is_a_share(quote("sh600000", "GP-A", price=0.0))


def test_candidate_symbols_are_padded_and_unique():
    symbols = list(universe.candidate_symbols())
    assert all(len(s) == 8 for s in symbols)
    assert len(set(symbols)) == len(symbols)
    assert "sz000001" in symbols
    assert "sh688981" in symbols


def test_discover_filters_and_survives_batch_errors(monkeypatch):
    calls = []

    class FakeSource:
        def quotes(self, batch):
            calls.append(list(batch))
            if len(calls) == 1:
                raise RuntimeError("upstream hiccup")
            return [quote("sh600000", "GP-A"), quote("sh510300", "JJ")]

    monkeypatch.setattr(universe, "CODE_RANGES", (("sh", "test", 600000, 600004),))
    found = universe.discover(FakeSource(), batch_size=2)

    assert [q.code for q in found] == ["sh600000", "sh600000"]
    assert len(calls) == 3
