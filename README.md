# A 股行情抓取 Agent

抓取 A 股实时行情与前复权 K 线，落库 SQLite，并提供一个自带 Web 界面（行情表格 + K 线图）。

数据源：腾讯财经公开接口（`qt.gtimg.cn` 实时行情、`web.ifzq.gtimg.cn` K 线、`smartbox.gtimg.cn` 搜索）。
无需 token，也不依赖东方财富 / 新浪（这两家在部分网络环境下不可用）。

## 安装

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 抓取

```bash
# 抓指定股票的实时快照（代码可写 600000 / sh600000 / 600000.SS）
python -m astock quotes 600000 000001 600519

# 扫描并收录全部 A 股代码（沪深北，约 5000+ 只，耗时几分钟）
python -m astock sync-universe

# 库里已有股票时，quotes 不带参数即抓取全市场
python -m astock quotes

# 前复权 K 线（day / week / month）
python -m astock candles 600000 300750 --period day --count 320

# 交易时段内每 60 秒轮询一次（--always 表示非交易时段也抓）
python -m astock watch --interval 60

# 按代码 / 名称 / 拼音搜索
python -m astock search 茅台

# 数据库统计
python -m astock stats
```

默认数据库为 `data/astock.db`，可用 `--db` 覆盖。

## Web 界面

```bash
python -m astock serve --port 8000   # 打开 http://localhost:8000
```

界面提供：行情表格（排序、关键字过滤、一键刷新），点击任意一行展开该股 K 线图（日/周/月，含成交量副图，缺数据时自动回源抓取）。

### HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/quotes?limit=&offset=&sort=&desc=&keyword=` | 每只股票的最新快照，`sort` 支持 `change_pct/price/amount/volume/turnover_rate/total_mcap/pe_ttm/code` |
| GET | `/api/quotes/{code}` | 单只股票最新快照 |
| GET | `/api/candles/{code}?period=day&limit=240&refresh=false` | K 线，库中无数据时自动回源 |
| POST | `/api/refresh` | 立即抓取一轮行情（body 可选 `["600000"]`） |
| GET | `/api/search?keyword=` | 股票搜索 |
| GET | `/api/stats` | 数据量统计 |

## 定时抓取

`python -m astock watch` 适合前台常驻；若用 cron，交易时段每分钟抓一次：

```
*/1 9-11,13-14 * * 1-5 cd /path/to/astock-agent && .venv/bin/python -m astock quotes >> logs/fetch.log 2>&1
```

## 数据表

- `stocks`：代码、名称、市场、类型（`GP-A` / `GP-A-CYB` 等）
- `quotes`：按 `(code, time)` 去重的行情快照，含价格、涨跌幅、成交额、换手率、市盈率、市值等
- `candles`：按 `(code, period, date)` 去重的前复权 K 线

## 开发

```bash
pytest -q
ruff check .
```

## 说明

数据来自公开行情接口，仅供学习研究，不构成投资建议；请勿高频请求以免被限流。
