# -*- coding: utf-8 -*-
"""离线单元测试：解析复制快照 -> 生成看板数据。CI 里先跑它再抓网络数据。"""

from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("update_board", ROOT / "scripts" / "update_board.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

SNAPSHOT = ROOT / "snapshots" / "source_2026-11-03.md"
NOW = datetime(2026, 11, 3, 11, 49, 0, tzinfo=timezone(timedelta(hours=8)))


class ParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SNAPSHOT.read_text(encoding="utf-8")
        cls.tables = mod.extract_tables(cls.text)

    def test_finds_two_tables(self):
        self.assertTrue(any("代码" in " ".join(t[0]) and "当日成交额" in " ".join(t[0]) for t in self.tables))
        self.assertTrue(any("日期" in " ".join(t[0]) and "合计" in " ".join(t[0]) for t in self.tables))

    def test_etf_rows(self):
        table = mod.find_table(self.tables, "代码", "当日成交额")
        rows = mod.parse_etf_table(table)
        self.assertEqual(len(rows), 20)
        self.assertEqual(rows[0]["code"], "588000")
        self.assertAlmostEqual(rows[0]["turnover_yi"], 224.56)
        self.assertAlmostEqual(rows[0]["change_pct"], -3.57)
        self.assertEqual(rows[0]["name"], "科创50ETF华夏")

    def test_daily_rows(self):
        table = mod.find_table(self.tables, "日期", "合计")
        columns, rows = mod.parse_daily_table(table)
        self.assertEqual(columns[0], "合计")
        self.assertEqual(len(rows), 22)
        self.assertEqual(rows[0]["date"], "2026-11-02")
        self.assertAlmostEqual(rows[0]["合计"], 511.5)
        self.assertAlmostEqual(rows[0]["沪深300"], 149.37)
        self.assertAlmostEqual(rows[2]["中证1000"], -27.70)

    def test_meta(self):
        meta = mod.parse_meta(self.text)
        self.assertEqual(meta["intraday_date"], "2026-11-03")
        self.assertEqual(meta["intraday_time"], "11:49:00")
        self.assertEqual(meta["today_date"], "2026-11-03")
        self.assertAlmostEqual(meta["today_turnover_yi"], 1540.1)
        self.assertAlmostEqual(meta["net_inflow_yi"], 451.6)
        self.assertEqual(meta["net_inflow_date"], "2026-11-02")
        self.assertEqual(meta["support_days"], 53)
        self.assertEqual(meta["history_days"], 732)

    def test_build_board(self):
        # 让测试不依赖已提交的 history.json（干净检出也应通过）
        with mock.patch.object(mod, "HISTORY_JSON", ROOT / "tests" / "no_history.json"):
            board = mod.build_board(self.text, "test", None, NOW)
        self.assertEqual(len(board["intraday"]["rows"]), 20)
        self.assertEqual(len(board["daily"]["rows"]), 22)
        self.assertAlmostEqual(board["intraday"]["total_turnover_yi"], 1540.1)
        self.assertEqual(board["meta"]["schedule"], mod.SCHEDULE_DEFAULT)
        self.assertIn("+451.6", mod.summary_md(board))
        # 输出必须能序列化成 UTF-8 JSON
        json.dumps(board, ensure_ascii=False)

    def test_html_table_parser(self):
        html = "<table><tr><th>代码</th><th>名称</th></tr><tr><td>510300</td><td>沪深300ETF</td></tr></table>"
        self.assertEqual(mod.extract_tables(html)[0][1], ["510300", "沪深300ETF"])

    def test_num(self):
        self.assertAlmostEqual(mod.num("+149.37"), 149.37)
        self.assertAlmostEqual(mod.num("-27.70%"), -27.70)
        self.assertIsNone(mod.num("—"))


if __name__ == "__main__":
    unittest.main()
