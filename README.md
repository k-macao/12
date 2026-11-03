# 12 · 重点ETF资金看板（复制版 + 每天两次自动推送）

> 复制自 [【东财策略 金科】重点ETF资金看板](https://etf-fund-flow-board.app.workbuddy.host/)，
> 并把原来人工/手动刷新的看板改成**每天自动推送两次**的静态站点。

A 股行情抓取 agent。原站是动态页面，本仓库把它复刻成「静态 HTML + JSON 数据」：
`update_board.py` 定时抓数 → 重写 `docs/data/board.json` → GitHub Actions `git commit` & `git push`，
每次运行就是一次推送；工作日/非交易日都会推送一次状态更新。

## 一、看板内容（与原站三部分一致）

| 部分 | 内容 |
| --- | --- |
| ① 盘中分钟观测 | 20 只重点宽基 ETF 当日成交额、占比、涨跌幅；成交额条形背景、涨跌幅红涨绿跌；放量案例图 |
| ② ETF托底信号 | 今日实时成交额、T-1 净流入、前一日成交额、托底日样本数；日度净流入柱图（红=托底日 / 黄=近期 / 虚线=最新值） |
| ③ 日度资金全景 | 篮子版本与区间说明、日度合计净流入折线、最新交易日分类构成、最近一个月分类型净流入热力表 |

原站的分钟级分时曲线 / 732 个交易日的历史序列并未对外暴露数据接口，因此本复制版用
抓取到的公开表格数据重绘图表，不伪造缺失的历史数值；新抓到的日度数据会累积进
`docs/data/history.json`，历史区间随时间增长。

页面保留了原站的「立即刷新」「暂停自动刷新」「下次刷新」控件，前端每 60 秒重新读取
`board.json`（推两次/天之后，页面打开时也能自动跟上最新快照）。

## 二、目录

```
docs/
  index.html          看板页面（复制版）
  style.css           样式
  app.js              表格 / KPI / SVG 图表渲染（零外部依赖）
  data/board.json     看板数据（自动任务每次推送时更新）
  data/board.js       同一份数据的 JS 包装，file:// 直接打开也能显示
  data/history.json   日度净流入历史，跨次累积
  latest.md           本次推送摘要（也是 webhook 通知的底稿）
scripts/
  update_board.py     抓数 + 解析 + 生成数据（仅 Python 标准库）
  notify.py           可选 webhook 通知（企业微信/钉钉/飞书/Slack）
snapshots/
  source_2026-11-03.md 复制原站时留存的快照，断网兜底
tests/
  test_update_board.py 离线解析测试
.github/workflows/etf-board.yml  每天两次自动推送 + 可选 Pages 发布
```

## 三、每天两次自动推送

工作流：`.github/workflows/etf-board.yml`

| 北京时间 | UTC（cron） | 用途 |
| --- | --- | --- |
| 11:30 | `30 3 * * *` | 盘中快照 |
| 15:30 | `30 7 * * *` | 收盘后快照 |

每次运行依次：跑离线测试 → 抓源站表格 + 东方财富 20 只 ETF 实时行情 →
写 `board.json` / `board.js` / `history.json` / `latest.md` →
（可选）发送 webhook 摘要 → **git commit + git push**。
`board.json` 里的 `generated_at` 每次都会变，所以两次运行各产生一次推送，不会因「无变化」被跳过。

改推送时间：改 workflow 里的两条 `cron`（UTC = 北京时间 − 8 小时），同时把
`ETF_PUSH_TIMES` 的说明文字改成对应时间即可。

> ⚠️ GitHub 规定 `schedule` 只在**默认分支**上生效。本分支是 `arena/2f3ce2a9-12`，
> 因此定时推送会在 PR 合并进 `main` 之后自动启用；合并前可以用
> `gh workflow run "ETF 资金看板 · 每天两次自动推送" --ref arena/2f3ce2a9-12` 手动验证。

### 可选的「推送」增强

- **消息通知**：在仓库 Settings → Secrets 添加 `ETF_WEBHOOK_URL`（企业微信 / 钉钉 / 飞书 / Slack
  机器人地址，脚本按域名自动适配报文）；不配置就跳过，不影响数据推送。
- **线上站点**：Settings → Pages 把 Source 设为 `GitHub Actions`，再添加仓库变量
  `ENABLE_PAGES=true`，`deploy-pages` 任务就会把 `docs/` 发布到 Pages，随每天两次推送同步更新。
  （未开启变量时该任务自动跳过，工作流不会失败。）

## 四、本地运行

```bash
# 看页面（浏览器打开 http://localhost:8000）
python3 -m http.server 8000 --bind 0.0.0.0 --directory docs

# 手动抓一次（联网）
python3 scripts/update_board.py

# 离线重算 / 跑测试 / 语法
python3 scripts/update_board.py --offline
python3 -m unittest discover -s tests -v
python3 scripts/notify.py     # 需 ETF_WEBHOOK_URL 才会真的发
```

`update_board.py` 的数据源优先级：源站 Markdown 视图 → 源站 HTML 表格 →
东方财富 push2 实时行情（成交额/涨跌幅）→ 仓库内快照。任一环节失败都不会写出空数据。

环境变量：`ETF_SOURCE_URL`（源站）、`ETF_READER_URL`（Markdown 代理）、
`ETF_PUSH_TIMES`（页面上的推送时间说明）、`ETF_WEBHOOK_URL`（通知）。

## 五、说明

- 数据来自公开页面 / 公开行情接口，仅供研究参考，不构成投资建议。
- 原站联系人署名：陈果 / 金科。本仓库仅做界面与数据结构的复刻，不主张原创数据。
