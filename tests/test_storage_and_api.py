import pytest
from fastapi.testclient import TestClient

from astock.sources.tencent import Candle, Quote
from astock.storage import Storage
from astock.web.app import create_app


def make_quote(code: str, name: str, price: float, change_pct: float, time: str) -> Quote:
    return Quote(
        code=code, name=name, price=price, prev_close=price - 0.1, open=price,
        high=price, low=price, change=0.1, change_pct=change_pct, volume=1000.0,
        amount=1e8, turnover_rate=1.5, pe_ttm=10.0, pb=1.2, float_mcap=100.0,
        total_mcap=200.0, amplitude=2.0, kind="GP-A", time=time,
    )


@pytest.fixture()
def storage(tmp_path):
    with Storage(tmp_path / "test.db") as store:
        store.save_quotes(
            [
                make_quote("sh600000", "浦发银行", 9.17, -0.43, "2026-08-12T15:00:00"),
                make_quote("sh600000", "浦发银行", 9.20, 0.10, "2026-08-12T15:01:00"),
                make_quote("sz000001", "平安银行", 11.25, 2.50, "2026-08-12T15:01:00"),
            ]
        )
        store.save_candles(
            "sh600000", "day",
            [Candle("2026-08-12", 9.21, 9.17, 9.22, 9.12, 467825.0)],
        )
        yield store


def test_latest_quotes_returns_one_row_per_code(storage):
    rows = storage.latest_quotes()
    assert [r["code"] for r in rows] == ["sz000001", "sh600000"]
    assert rows[1]["price"] == 9.20


def test_latest_quotes_keyword_and_sort(storage):
    assert [r["code"] for r in storage.latest_quotes(keyword="平安")] == ["sz000001"]
    ascending = storage.latest_quotes(order_by="price", desc=False)
    assert [r["price"] for r in ascending] == [9.20, 11.25]


def test_latest_quotes_rejects_unknown_sort_column(storage):
    with pytest.raises(ValueError):
        storage.latest_quotes(order_by="price; DROP TABLE quotes")


def test_stats_and_stocks(storage):
    stats = storage.stats()
    assert stats["stocks"] == 2
    assert stats["quotes"] == 3
    assert stats["candles"] == 1
    assert {s["name"] for s in storage.stocks()} == {"浦发银行", "平安银行"}


def test_api_endpoints(tmp_path, storage):
    client = TestClient(create_app(storage.path))

    quotes = client.get("/api/quotes", params={"limit": 10}).json()
    assert quotes["count"] == 2

    assert client.get("/api/quotes/600000").json()["name"] == "浦发银行"
    assert client.get("/api/quotes/605999").status_code == 404
    assert client.get("/api/quotes/bad-code").status_code == 400
    assert client.get("/api/quotes", params={"sort": "evil"}).status_code == 400

    candles = client.get("/api/candles/600000").json()
    assert candles["items"][0]["close"] == 9.17

    assert client.get("/").status_code == 200
