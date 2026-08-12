from datetime import datetime

from astock.service import is_market_open, load_watchlist


def test_is_market_open_windows():
    assert is_market_open(datetime(2026, 8, 12, 10, 0))  # 周三上午
    assert is_market_open(datetime(2026, 8, 12, 14, 30))  # 周三下午
    assert not is_market_open(datetime(2026, 8, 12, 12, 0))  # 午休
    assert not is_market_open(datetime(2026, 8, 12, 20, 0))  # 收盘后
    assert not is_market_open(datetime(2026, 8, 15, 10, 0))  # 周六


def test_load_watchlist_parses_comments(tmp_path):
    file = tmp_path / "watchlist.txt"
    file.write_text("600000  # 浦发\n\n# 整行注释\n000001\n", encoding="utf-8")
    assert load_watchlist(file) == ["sh600000", "sz000001"]


def test_load_watchlist_missing_file(tmp_path):
    assert load_watchlist(tmp_path / "nope.txt") == []
