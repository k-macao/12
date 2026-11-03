#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可选：把本次看板摘要推送到 webhook。

支持企业微信 / 钉钉 / 飞书 / Slack 风格（按 URL 自动判断），
其它地址发送通用 JSON。未配置 ETF_WEBHOOK_URL 时什么都不做。

GitHub Actions 里把它作为 Secret 配置即可；通知失败不会阻断数据推送。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_message() -> str:
    board = json.loads((ROOT / "docs/data/board.json").read_text(encoding="utf-8"))
    meta, intra, sup = board["meta"], board["intraday"], board["support"]
    top = "、".join(f"{r['name']} {r['turnover_yi']:.2f}亿" for r in intra["rows"][:3])
    inflow = sup.get("net_inflow_yi")
    inflow_text = f"{inflow:+.1f}亿" if isinstance(inflow, (int, float)) else "—"
    return (
        f"【重点ETF资金看板 · {meta['trade_date']}】\n"
        f"20只ETF合计成交额：{intra['total_turnover_yi']:.1f}亿\n"
        f"最新净流入（{sup.get('net_inflow_date') or 'T-1'}）：{inflow_text}\n"
        f"成交额前三：{top}\n"
        f"数据来源：{meta['source_label']}\n"
        f"推送时间：{meta['generated_at']}"
    )


def payload_for(url: str, text: str) -> dict:
    if "qyapi.weixin.qq.com" in url:  # 企业微信
        return {"msgtype": "text", "text": {"content": text}}
    if "oapi.dingtalk.com" in url:  # 钉钉
        return {"msgtype": "text", "text": {"content": text}}
    if "open.feishu.cn" in url or "open.larksuite.com" in url:  # 飞书 / Lark
        return {"msg_type": "text", "content": {"text": text}}
    return {"text": text}  # Slack 及其它通用 webhook


def main() -> int:
    url = os.getenv("ETF_WEBHOOK_URL", "").strip()
    if not url:
        print("[skip] 未配置 ETF_WEBHOOK_URL，跳过通知")
        return 0
    try:
        message = build_message()
        body = json.dumps(payload_for(url, message), ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "ETFBoardBot/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[ok] 通知已发送：HTTP {resp.status}")
    except Exception as exc:  # 通知失败不应影响数据推送
        print(f"[warn] 通知失败（已忽略）：{exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
