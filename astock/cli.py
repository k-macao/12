"""Command line entry point: python -m astock <command>."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .service import Collector
from .sources.tencent import TencentSource
from .storage import DEFAULT_DB, Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="astock", description="A 股行情抓取 agent")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite 文件路径")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sync-universe", help="扫描并保存全部 A 股代码")

    quotes = sub.add_parser("quotes", help="抓取实时行情快照")
    quotes.add_argument("codes", nargs="*", help="股票代码，省略则抓取库中全部股票")

    candles = sub.add_parser("candles", help="抓取前复权 K 线")
    candles.add_argument("codes", nargs="+")
    candles.add_argument("--period", default="day", choices=["day", "week", "month"])
    candles.add_argument("--count", type=int, default=320)

    watch = sub.add_parser("watch", help="按固定间隔持续抓取行情")
    watch.add_argument("codes", nargs="*")
    watch.add_argument("--interval", type=int, default=60)
    watch.add_argument("--always", action="store_true", help="非交易时段也抓取")

    search = sub.add_parser("search", help="按代码/名称/拼音搜索股票")
    search.add_argument("keyword")

    sub.add_parser("stats", help="展示数据库统计")

    serve = sub.add_parser("serve", help="启动 Web 界面")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not args.verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.command == "serve":
        import uvicorn

        from .web.app import create_app

        uvicorn.run(create_app(args.db), host=args.host, port=args.port)
        return 0

    with Storage(args.db) as storage:
        if args.command == "stats":
            print(json.dumps(storage.stats(), ensure_ascii=False, indent=2))
            return 0

        collector = Collector(storage, TencentSource())
        try:
            if args.command == "sync-universe":
                result = collector.sync_universe()
                print(f"已收录 {result.stocks} 只 A 股")
            elif args.command == "quotes":
                result = collector.fetch_quotes(args.codes or None)
                print(f"已保存 {result.quotes} 条行情")
            elif args.command == "candles":
                result = collector.fetch_candles(args.codes, args.period, args.count)
                print(f"已保存 {result.candles} 根 K 线，失败 {result.errors} 只")
            elif args.command == "search":
                for hit in collector.source.search(args.keyword):
                    print(f"{hit['code']}\t{hit['name']}\t{hit['pinyin']}")
            elif args.command == "watch":
                collector.run_forever(
                    interval=args.interval,
                    codes=args.codes or None,
                    only_when_open=not args.always,
                )
        except KeyboardInterrupt:
            return 130
        finally:
            collector.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
