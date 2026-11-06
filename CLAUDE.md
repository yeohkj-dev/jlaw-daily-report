# 交接说明（给以后接手的 Claude / 任何人）

> 用户以后只会说「去看 https://github.com/yeohkj-dev/jlaw-daily-report 」。先读完这一页再动手。
> 这个系统**完全在 GitHub 上自动运行**，不依赖任何 Claude 账号，也不需要用户的电脑开着。

## 1. 这是什么

| 项目 | 网址 |
|---|---|
| 每日报告网站 | https://yeohkj-dev.github.io/jlaw-daily-report/ |
| 本仓库（公开） | https://github.com/yeohkj-dev/jlaw-daily-report |
| 仓位风险计算器（另一个仓库，被报告的「风险计算」分页嵌入） | https://yeohkj-dev.github.io/risk-calculator/ · https://github.com/yeohkj-dev/risk-calculator |
| 自动运行记录 | https://github.com/yeohkj-dev/jlaw-daily-report/actions |

用户是马来西亚的美股交易者（GMT+8），用这些资料规划投资。用户用**简体中文**沟通，报告也全部是简体中文。

### 网站分页
| 分页 | 程序 | 内容 |
|---|---|---|
| 早报 | `tools/morning_brief.py` | 昨晚美股发生什么、相关新闻（为什么）、行业、大公司异动、今晚要看什么 |
| 大盘报告 | `tools/market_regime.py` | J Law 大盘体温计（躺赚 / 警戒 / 血汗钱）、恐惧指数（CNN + VIX）、行业 ETF 追踪、信用市场（科技 / AI 公司债利差）、见底信号 |
| 每日选股 | `tools/jlaw_daily_screen.py` | J Law META 回调、VCP 突破、观察名单、Stage 1→2 候选、Stage 2 名单 |
| Luk 选股 | `tools/luk_screens.py` | Martin Luk 的 Leaders / Strong Day / Gappers（条件来自 Luk 本人公布的 TradingView 设置） |
| 今日新闻 | `tools/news_digest.py` + `tools/weekly_events.py` | 上面是本周重大事件（周末是本周回顾 + 下周看点），下面是当天新闻 |
| 业绩与估值 | `tools/earnings_valuation.py` | 11 个板块各前 10 大公司的业绩、指引原文（SEC 8-K）、两年估值情景 |
| 每周展望 | `tools/weekly_outlook.py` | 9 个因素打分判断下周方向（周日更新） |
| 风险计算 | `tools/jlaw_daily_report.py` 里的 `risk_tab()` | 用 iframe 嵌入风险计算器，网址带 `?light=green|yellow|red`（按大盘状态预选灯号） |

`tools/jlaw_daily_report.py` 依次运行各模块，合并成一个多分页网页，写到 `docs/`（GitHub Pages 从 `main` 分支的 `docs/` 发布）。页头有更新时间、下次更新时间和「数据核对」汇总。

## 2. 自动运行（GitHub Actions）

| 工作流 | 时间（UTC） | 马来西亚时间 | 做什么 |
|---|---|---|---|
| `.github/workflows/daily.yml`「每日报告」 | 周一至五 22:30；周日 23:00 | 周二至六 06:30；周一 07:00 | 生成报告 → 发布网站 → 发 Telegram 早报 → 把数据提交回仓库 |
| `.github/workflows/premarket.yml`「盘前提醒」 | 周一至五 12:00–14:40 每 20 分钟 | 美国冬令时约晚上 10:00，夏令时约 9:00 | 只在美东 08:50–09:29 之间（开市前约 30 分钟）发 Telegram 盘前提醒，一天只发一次 |
| `.github/workflows/telegram-test.yml`「Telegram 测试」 | 只能手动 | — | 把最新早报再发一次，测试 Telegram 设置 |

- **Secrets**（仓库 Settings → Secrets and variables → Actions）：`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`。由用户自己填，**不要让用户把 token 贴给你，也不要代填**。
- 平日版用 `--strict`：数据核对有严重问题时这次运行失败、网站保留上一份，GitHub 会发邮件给用户。
- 周末版不重跑大盘、选股、Luk、早报，改用网站上一份（`published_panel()` 从 `docs/index.html` 取出分页）。
- **GitHub 会停用 60 天没有活动的公开仓库排程**。机器人每天都会提交，所以正常不会发生；如果 Actions 页面出现「This scheduled workflow is disabled」，点 **Enable workflow** 即可。
- 手动运行：Actions → 选工作流 → **Run workflow**。

## 3. 用户的规则（一定要遵守）

1. **改动先给用户看本地 HTML 预览，用户说「同意推送」才推送到 GitHub。** 每一次都要问，上一次的同意不算这次的。
2. **不用 AI 生成报告内容**（用户选了免费、规则整理）。新闻只显示原标题和来源；「为什么」是新闻配对，要写明「相关新闻，不是因果分析」，找不到就照实写。
3. **数据要交叉核对**（Yahoo vs TradingView vs 其他来源），核对结果显示在页头「数据核对」。不确定的东西不要写成事实。
4. 给用户的成品输出做成**本地 HTML 文件**。
5. GitHub 操作用 `git push`（Git Credential Manager 已登录）或内置浏览器里已登录的 github.com；**不要安装或要求登录 gh CLI**。
6. 用户的 `D:\AI\Claude AI` 里有私人投资资料，**只推这个仓库的文件**。
7. 本机 git 没有设置身份，提交时用：`git -c user.name=jlaw-report -c user.email=noreply@example.com commit ...`

## 4. 在本机修改和预览

```
python tools/jlaw_daily_report.py . --no-open               # 生成 每日报告/YYYY-MM-DD.html（不发布）
python tools/jlaw_daily_report.py . --no-open --weekday     # 强制平日版（--weekend 强制周末版）
python tools/<模块>.py .                                    # 单独跑一个模块
```
- Windows 终端要加 `PYTHONIOENCODING=utf-8`，否则中文输出会报错。
- 预览：`.claude/launch.json`（在 `D:\AI\Claude AI`）有 `jlaw-report-preview`，端口 8767，目录是 `jlaw-daily-report/每日报告`。把生成的报告复制成 `每日报告/预览_xxx.html` 给用户看。
- 预览「风险计算」分页时可用环境变量 `RISK_URL=risk-calc.html`（把计算器复制到 `每日报告/`）。
- 用户要网站**马上**更新时（不等排程）：先 `git pull`，再跑 `python tools/jlaw_daily_report.py . --no-open --weekday --publish docs --strict`，然后
  `git add -A docs 大盘报告 每日选股 每周展望 业绩估值/cache 新闻 Luk选股 早报` 加上改过的程序，提交并推送。
- 推送前把本机测试产生的数据还原（`git checkout -- <数据文件夹>`，删掉测试生成的新文件），只提交需要的。

### 仓库里的数据（机器人每天提交）
`大盘报告/大盘历史.csv`、`行业历史.csv`、`信用历史.csv`（每家固定追踪同一只债券）、`每日选股/*.csv|md`、`Luk选股/*.json`（标「新上榜」用）、`新闻/*_daily.json` 和 `week_*.json`（本周重大事件逐日累加用）、`早报/*.json` 和 `_sent.txt` / `_premarket_sent.txt`（避免重复发送）、`业绩估值/cache/`、`每周展望/`。
各模块的 HTML 不进仓库（`.gitignore`），只有 `docs/` 里的网站。

## 5. 已知的坑

- **Yahoo 收盘后一段时间，日线可能还没有当天那一根**，但 `meta.regularMarketPrice` 已是当天收盘 → `morning_brief.daily_moves()` 已处理；新模块也要注意。
- **FRED（ICE BofA 利差）在本机和 GitHub 都连不上**，大盘报告的信用市场改用 HYG / IEF 走势；数据核对会显示这项提醒。
- **CNN 恐惧贪婪指数**是 CNN 网页用的接口，不是公开 API；GitHub 上目前取得到。
- **Forex Factory 日历**有调用次数限制，缓存 3 小时（`新闻/_calendar_*.json`，不进仓库）。周六取「下周」、周日起「本周」已是新一周。
- **用 bash heredoc 写 Python 时，`\b` 会变成退格字符**，正则就坏了。改代码请用编辑工具，或写好检查 `"\x08" not in s`。
- TradingView 选股器（`scanner.tradingview.com/{america,bond,global}/scan`）是公开接口；债券用 `bond`，美债收益率用 `global` 的 `TVC:US10Y` 等。
- `每日选股`、`Luk选股` 的文件名用运行当天的日期；GitHub 在 UTC 22:30 跑，日期等于美股交易日。在马来西亚本机跑会是下一天，属正常。

## 6. 回测（`回测/`）

- `download.py`：TradingView 股票池 + Yahoo 5 年日线（存 `回测/cache/`，不进仓库）
- `backtest.py`：直接调用 `tools/jlaw_daily_screen.py` 的 `analyse()`（和网站同一份代码），逐日重跑并模拟交易；Stage、Luk 名单算上榜后 5 / 10 / 20 天报酬
- `report.py` + `conclusions.json`：生成 `回测报告.html`
- 运行：`python 回测/download.py` → `python 回测/backtest.py` → `python 回测/report.py`（全部约 15 分钟）
- **K线形态回测（`回测/K线形态/`，2026-11-06）**：43 种K线 / 量价形态在约 2,250 只美股、约 96 万次信号上的超额收益。说明和完整结果表在 `回测/K线形态/README.md`。`tools/market_regime.py` 的 `bt_note()` 按 SPY / QQQ 是否在 200 天线下，在大盘报告「建议」下面显示「K线形态回测提示」（固定文字，数字来自 `stats.json` 和 `crash.json`；重跑回测后要人工同步这些数字）。用户的持仓清单不放进这个公开仓库。
- 2026-11 的结论：J Law META / VCP 只有约 +0.1R 的薄优势（只在 5R 目标卖法下），均线移动止损略亏，2026 年转负；Stage 名单没有优势；Luk 名单平均跑赢 SPY 约 0.5%（20 天）但靠少数大赢家；有幸存者偏差。

## 7. 待办 / 还没验证

- 周末版「下周看点」的经济日历只在周六测过（取不到），周日的真实运行还要看结果。
- FRED 利差取不到，可考虑其他免费来源。
- 回测建议的改进还没测：分批止盈（2–3R 先卖一半）、只做 RS 最强的前几名、要求热门产业组。

**仅供学习，不构成投资建议。**
