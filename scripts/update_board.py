#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《重点ETF资金看板》数据抓取器。

复制自 https://etf-fund-flow-board.app.workbuddy.host/ 的看板，用本脚本把
数据刷新成静态 JSON，然后由 GitHub Actions 每天两次自动 commit + push。

数据源优先级：
  1. 原看板页面（r.jina.ai 的 Markdown 视图，或直接抓 HTML 表格）
  2. 东方财富 push2 实时行情（20 只 ETF 的当日成交额 / 涨跌幅）
  3. 仓库内快照 snapshots/source_*.md（离线、断网兜底，永不写空数据）

输出：
  docs/data/board.json    看板数据（前端读取）
  docs/data/board.js      同一份数据的 JS 包装（file:// 直接打开时兜底）
  docs/data/history.json  日度净流入历史，跨次累积
  docs/latest.md          本次推送摘要（也是 webhook 通知正文）

只用 Python 标准库，CI 不需要安装任何依赖。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DATA_DIR = DOCS / "data"
BOARD_JSON = DATA_DIR / "board.json"
BOARD_JS = DATA_DIR / "board.js"
HISTORY_JSON = DATA_DIR / "history.json"
LATEST_MD = DOCS / "latest.md"
SNAPSHOT_DIR = ROOT / "snapshots"

SOURCE_URL = os.getenv("ETF_SOURCE_URL", "https://etf-fund-flow-board.app.workbuddy.host/")
READER_URL = os.getenv("ETF_READER_URL", "https://r.jina.ai/" + SOURCE_URL)
QUOTE_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
CST = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (compatible; ETFBoardBot/1.0; +https://github.com/k-macao/12)"

# 2026-10-15 版新篮子：20 只重点宽基 ETF（代码 -> 名称）
BASKET = [
    ("510310", "沪深300ETF易方达"),
    ("588000", "科创50ETF华夏"),
    ("159915", "创业板ETF易方达"),
    ("510300", "沪深300ETF华泰柏瑞"),
    ("563360", "A500ETF华泰柏瑞"),
    ("159352", "A500ETF南方"),
    ("512100", "中证1000ETF南方"),
    ("159338", "中证A500ETF国泰"),
    ("510500", "中证500ETF南方"),
    ("159949", "创业板50ETF华安"),
    ("588080", "科创50ETF易方达"),
    ("510050", "上证50ETF华夏"),
    ("510210", "上证指数ETF富国"),
    ("159845", "中证1000ETF华夏"),
    ("159952", "创业板ETF广发"),
    ("159361", "A500ETF易方达"),
    ("512050", "A500ETF华夏"),
    ("159633", "中证1000ETF易方达"),
    ("560010", "中证1000ETF广发"),
    ("159919", "沪深300ETF嘉实"),
]
BASKET_NAMES = dict(BASKET)

SCHEDULE_DEFAULT = os.getenv("ETF_PUSH_TIMES", "每天 11:30 / 15:30（北京时间，交易日）")


# --------------------------------------------------------------------------- #
# 网络
# --------------------------------------------------------------------------- #
def http_get(url: str, timeout: float = 20.0, retries: int = 2) -> str | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/json,text/plain,*/*",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
        },
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return raw.decode(resp.headers.get_content_charset() or "utf-8", "replace")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if attempt == retries:
                print(f"[warn] 抓取失败 {url}: {exc}", file=sys.stderr)
                return None
    return None


def fetch_quotes() -> list[dict] | None:
    """东方财富实时行情：20 只 ETF 的当日累计成交额与涨跌幅。"""
    secids = ",".join(("1." if code[0] in "56" else "0.") + code for code, _ in BASKET)
    params = urllib.parse.urlencode(
        {
            "fltt": 2,
            "invt": 2,
            "fields": "f2,f3,f6,f12,f14",
            "secids": secids,
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        }
    )
    text = http_get(f"{QUOTE_URL}?{params}")
    if not text:
        return None
    try:
        payload = json.loads(text)
        diff = (payload.get("data") or {}).get("diff") or []
        if isinstance(diff, dict):
            diff = list(diff.values())
    except (ValueError, AttributeError):
        return None

    rows: list[dict] = []
    for item in diff:
        try:
            code = str(item["f12"])
            amount = float(item["f6"]) / 1e8  # 元 -> 亿元
            change = float(item["f3"])
            if amount <= 0 or code not in BASKET_NAMES:
                continue
            rows.append(
                {
                    "code": code,
                    "name": BASKET_NAMES[code],
                    "turnover_yi": round(amount, 2),
                    "change_pct": round(change, 2),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    # 行情接口偶尔只返回部分标的，数量不够就回退到原看板表格。
    return rows if len(rows) >= 15 else None


def fetch_source_text() -> tuple[str, str]:
    """优先取在线视图；全部失败时回退到仓库里的复制快照。

    加时间戳参数绕开 CDN / 阅读器缓存，确保每次推送拿到的是最新一版表格。
    """
    bust = str(int(time.time()))
    urls = [
        (READER_URL, "r.jina.ai"),
        (SOURCE_URL, "源站"),
    ]
    for base, label in urls:
        url = base + ("&" if "?" in base else "?") + "_=" + bust
        text = http_get(url)
        if text and ("当日成交额" in text or "<table" in text.lower()):
            return text, f"{label}（实时）"
    snap = latest_snapshot()
    return snap.read_text(encoding="utf-8"), f"本地快照 {snap.name}"


def latest_snapshot() -> Path:
    files = sorted(SNAPSHOT_DIR.glob("source_*.md"))
    if not files:
        raise FileNotFoundError("缺少 snapshots/source_*.md 复制快照")
    return files[-1]


# --------------------------------------------------------------------------- #
# 解析（同时支持 Markdown 表格与 HTML 表格）
# --------------------------------------------------------------------------- #
class HTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def parse_md_block(block: list[str]) -> list[list[str]]:
    rows = []
    for line in block:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells):
            continue  # 分隔行
        rows.append(cells)
    return rows


def extract_tables(text: str) -> list[list[list[str]]]:
    if "<table" in text.lower():
        parser = HTMLTableParser()
        parser.feed(text)
        tables = parser.tables
    else:
        tables, block = [], []
        for line in text.splitlines() + [""]:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                block.append(stripped)
            elif block:
                tables.append(parse_md_block(block))
                block = []
    return [t for t in tables if len(t) >= 2]


def find_table(tables, *keywords) -> list[list[str]] | None:
    for table in tables:
        header = " ".join(table[0])
        if all(k in header for k in keywords):
            return table
    return None


def num(value: str) -> float | None:
    value = (value or "").strip().replace(",", "").replace("%", "").replace("+", "")
    if value in ("", "-", "—", "–"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_etf_table(table: list[list[str]]) -> list[dict]:
    rows = []
    for cells in table[1:]:
        if len(cells) < 5 or not re.fullmatch(r"\d{6}", cells[0]):
            continue
        rows.append(
            {
                "code": cells[0],
                "name": cells[1],
                "turnover_yi": num(cells[2]),
                "share_pct": num(cells[3]),
                "change_pct": num(cells[4]),
            }
        )
    return rows


def parse_daily_table(table: list[list[str]]) -> tuple[list[str], list[dict]]:
    columns = [c.strip() for c in table[0][1:]]
    rows = []
    for cells in table[1:]:
        if not cells or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[0].strip()):
            continue
        row = {"date": cells[0].strip()}
        for key, value in zip(columns, cells[1:]):
            row[key] = num(value)
        rows.append(row)
    return columns, rows


def parse_meta(text: str) -> dict:
    def search(pattern, default=None, cast=str):
        m = re.search(pattern, text)
        if not m:
            return default
        try:
            return cast(m.group(1) if m.lastindex == 1 else m.groups())
        except (TypeError, ValueError):
            return default

    meta: dict = {}
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*分时\s*更新于\s*(\d{2}:\d{2}:\d{2})", text)
    meta["intraday_date"] = m.group(1) if m else None
    meta["intraday_time"] = m.group(2) if m else None
    if not meta["intraday_date"]:
        m = re.search(r"(\d{4}-\d{2}-\d{2})\s*分时", text)
        meta["intraday_date"] = m.group(1) if m else None

    m = re.search(r"今日成交额（(\d{4}-\d{2}-\d{2})，实时）：([\d.]+)亿", text)
    meta["today_date"], meta["today_turnover_yi"] = (
        (m.group(1), float(m.group(2))) if m else (meta["intraday_date"], None)
    )
    m = re.search(
        r"最新净流入（(\d{4}-\d{2}-\d{2})，T-1）：([+-]?[\d.]+)亿\s*[｜|]\s*成交额\s*([\d.]+)亿",
        text,
    )
    meta["net_inflow_date"], meta["net_inflow_yi"], meta["net_inflow_turnover_yi"] = (
        (m.group(1), float(m.group(2)), float(m.group(3)))
        if m
        else (None, None, None)
    )
    meta["support_days"] = search(r"共\s*(\d+)\s*天", 53, int)
    meta["history_start"] = search(r"区间：\s*([\d-]+)\s*~", "2023-10-09")
    meta["history_end"] = search(r"区间：\s*[\d-]+\s*~\s*([\d-]+)", "2026-10-15")
    meta["history_days"] = search(r"（(\d+)个交易日）", 732, int)
    meta["basket_version"] = search(r"(已切换至[^｜|\n]+版新篮子)", "已切换至2026-10-15版新篮子")
    meta["support_note"] = (
        "托底日 = 单日净流入 > 100亿（申赎口径），剔除 2024-09-24~10-18 狂热申购窗 "
        "与 2026-01-14~01-30 及 02-02/13/26 抛售窗 ｜ 成交额图蓝柱 / "
        "净流入图红柱=托底日，黄柱=近期交易日 ｜ 虚线=最新柱的数值水平线"
    )
    meta["panorama_note"] = (
        "柱：20只ETF日度成交额 / 净流入（申赎口径）｜线：上证综指收盘"
    )
    return meta


# --------------------------------------------------------------------------- #
# 组装 / 输出
# --------------------------------------------------------------------------- #
def load_history() -> dict:
    if HISTORY_JSON.is_file():
        try:
            return json.loads(HISTORY_JSON.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"rows": []}


def merge_daily_rows(new_rows: list[dict], history: dict) -> list[dict]:
    merged = {row["date"]: row for row in history.get("rows", []) if "date" in row}
    for row in new_rows:
        merged[row["date"]] = row  # 新抓到的数据覆盖旧值
    return sorted(merged.values(), key=lambda r: r["date"], reverse=True)[:40]


def build_board(text: str, source_label: str, quotes: list[dict] | None, now: datetime) -> dict:
    tables = extract_tables(text)
    meta = parse_meta(text)

    etf_table = find_table(tables, "代码", "当日成交额")
    daily_table = find_table(tables, "日期", "合计")
    if etf_table is None or daily_table is None:
        raise ValueError("源页面里没找到「单只ETF当日表现」或「日度净流入」表格")

    source_rows = parse_etf_table(etf_table)
    daily_columns, daily_new = parse_daily_table(daily_table)
    daily_rows = merge_daily_rows(daily_new, load_history())

    if quotes:
        total = sum(r["turnover_yi"] for r in quotes)
        etf_rows = [
            {
                "code": r["code"],
                "name": r["name"],
                "turnover_yi": r["turnover_yi"],
                "share_pct": round(r["turnover_yi"] / total * 100, 1) if total else None,
                "change_pct": r["change_pct"],
            }
            for r in sorted(quotes, key=lambda r: r["turnover_yi"], reverse=True)
        ]
        quote_status = "eastmoney"
    else:
        etf_rows = source_rows
        quote_status = "source_table"

    turnover_total = round(sum(r["turnover_yi"] or 0 for r in etf_rows), 1)
    if not turnover_total and meta.get("today_turnover_yi"):
        turnover_total = meta["today_turnover_yi"]

    board = {
        "meta": {
            "title": "【东财策略 金科】重点ETF资金看板",
            "contact": "联系人：陈果 / 金科（欢迎随缘打赏π点 ❤️）",
            "source": SOURCE_URL,
            "copied_from": SOURCE_URL,
            "source_label": source_label,
            "quote_status": quote_status,
            "generated_at": now.isoformat(timespec="seconds"),
            "trade_date": meta.get("today_date") or meta.get("intraday_date") or now.strftime("%Y-%m-%d"),
            "intraday_updated_at": meta.get("intraday_time"),
            "schedule": SCHEDULE_DEFAULT,
            "basket_version": meta.get("basket_version"),
            "history_range": f"{meta.get('history_start')} ~ {meta.get('history_end')}（{meta.get('history_days')}个交易日）",
            "disclaimer": "本页为公开看板的复制版，数据仅供参考，不构成投资建议。",
        },
        "sections": [
            {"id": "part1", "title": "第一部分 · 盘中分钟观测", "nav": "① 盘中分钟观测"},
            {"id": "part2", "title": "第二部分 · ETF托底信号", "nav": "② 托底信号对比"},
            {"id": "part3", "title": "第三部分 · 日度资金全景", "nav": "③ 日度资金全景"},
        ],
        "intraday": {
            "date": meta.get("intraday_date") or now.strftime("%Y-%m-%d"),
            "updated_at": meta.get("intraday_time"),
            "total_turnover_yi": turnover_total,
            "rows": etf_rows,
            "cases": etf_rows[:10],
            "note": "单只ETF当日表现（按成交额降序，条形背景按成交额相对最大值比例）",
        },
        "support": {
            "note": meta.get("support_note"),
            "support_days": meta.get("support_days"),
            "today_date": meta.get("today_date"),
            "today_turnover_yi": meta.get("today_turnover_yi") or turnover_total,
            "net_inflow_date": meta.get("net_inflow_date"),
            "net_inflow_yi": meta.get("net_inflow_yi"),
            "net_inflow_turnover_yi": meta.get("net_inflow_turnover_yi"),
        },
        "daily": {
            "note": meta.get("panorama_note"),
            "table_title": "最近一个月 · 各类宽基ETF日度净流入（亿元，红=净申购 / 绿=净赎回，颜色深浅按当列相对大小）",
            "columns": daily_columns,
            "rows": daily_rows,
            "note_color": "红=净申购 / 绿=净赎回，颜色深浅按当列相对大小",
        },
    }
    return board


def summary_md(board: dict) -> str:
    m, intra, sup = board["meta"], board["intraday"], board["support"]
    top = intra["rows"][:3]
    top_text = "、".join(f"{r['name']} {r['turnover_yi']:.2f}亿" for r in top)
    inflow = sup.get("net_inflow_yi")
    inflow_text = f"{inflow:+.1f}亿" if isinstance(inflow, (int, float)) else "—"
    lines = [
        "# 重点ETF资金看板 · 本次推送", "",
        f"- 抓取时间：{m['generated_at']}",
        f"- 交易日：{m['trade_date']}",
        f"- 数据来源：{m['source_label']}（行情：{m['quote_status']}）",
        f"- 20只ETF合计成交额：{intra['total_turnover_yi']:.1f}亿",
        f"- 最新净流入（{sup.get('net_inflow_date') or 'T-1'}）：{inflow_text}",
        f"- 成交额前三：{top_text}",
        f"- 自动推送：{m['schedule']}",
        "", "完整看板见 docs/index.html。", "",
    ]
    return "\n".join(lines)


def write_outputs(board: dict, dry_run: bool = False) -> None:
    if dry_run:
        print(json.dumps(board, ensure_ascii=False, indent=2)[:1500] + "\n...")
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(board, ensure_ascii=False, indent=2)
    BOARD_JSON.write_text(payload + "\n", encoding="utf-8")
    BOARD_JS.write_text("window.__BOARD_DATA__ = " + payload + ";\n", encoding="utf-8")
    HISTORY_JSON.write_text(
        json.dumps(
            {"updated_at": board["meta"]["generated_at"], "rows": board["daily"]["rows"]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    LATEST_MD.write_text(summary_md(board), encoding="utf-8")
    print(f"[ok] 已写入 {BOARD_JSON.relative_to(ROOT)} / board.js / history.json / latest.md")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="刷新重点ETF资金看板数据")
    ap.add_argument("--source", type=Path, help="本地 Markdown/HTML 快照文件")
    ap.add_argument("--offline", action="store_true", help="完全不访问网络（用本地快照）")
    ap.add_argument("--timestamp", help="覆盖生成时间，ISO8601，便于测试")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = ap.parse_args(argv)

    now = datetime.fromisoformat(args.timestamp) if args.timestamp else datetime.now(CST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=CST)

    if args.source:
        text = args.source.read_text(encoding="utf-8")
        source_label = f"本地快照 {args.source.name}"
    elif args.offline:
        snap = latest_snapshot()
        text = snap.read_text(encoding="utf-8")
        source_label = f"本地快照 {snap.name}"
    else:
        text, source_label = fetch_source_text()

    quotes = None if args.offline else fetch_quotes()
    if quotes:
        print(f"[info] 东方财富行情：{len(quotes)} 只 ETF")
    else:
        print("[info] 行情接口不可用，沿用源看板表格")

    try:
        board = build_board(text, source_label, quotes, now)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    write_outputs(board, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
