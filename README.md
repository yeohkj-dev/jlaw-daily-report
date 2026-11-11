# 每日报告

> **接手维护请先看 [CLAUDE.md](CLAUDE.md)**：系统怎么自动运行、用户的规则、怎么修改和预览、已知的坑。

GitHub Actions 自动运行，生成一个多分页的网页（分成 4 大类：今天怎么做 / 大盘 / 选股 / 新闻·业绩）：

| 分页 | 内容 | 更新 |
|---|---|---|
| 早报 | 昨晚美股发生什么、相关新闻（为什么）、领涨领跌行业、大公司异动、今晚要看的数据和业绩；规则整理，不用 AI | 每个交易日 |
| 大盘报告 | J Law 大盘体温计（躺赚 / 警戒 / 血汗钱）：出货日、突兀走势、市场宽度、见底信号 | 每个交易日 |
| 每日选股 | 第二阶段股票池里的「META 回调」和「VCP 突破」候选股，附买点、止损和业绩日期 | 每个交易日 |
| Luk 选股 | Martin Luk 的三个 TradingView 选股器：Leaders、Strong Day、Gappers，附 EMA 分类（Lead / Mediocre / Lag）、ADR%、主题和新上榜 | 每个交易日 |
| 今日新闻 / 周末新闻 | 最上面是「本周重大事件」（本周走势、重要经济数据、大公司财报、本周最重大新闻，逐日累加；周末变成本周回顾），下面是当天影响市场的新闻（按主题归类、多家媒体报道的优先）、市场快照、美国经济日历 | 每个交易日；周日晚上出周末版 |
| 业绩与估值 | 11 个板块各前 10 大公司：最新季度业绩 vs 预期、公司展望原文（SEC 8-K）、分析师预期修正、两年估值情景 | 每天 |
| 每周展望 | 9 个因素打分判断下周方向（偏多 / 中性 / 偏空）、指数与宏观的中期趋势 | 每周日晚上 |
| 综合名单 | 量化红绿灯 + J Law 大盘灯（取较严的）+ J Law / 量化动量 / Luk 名单 + 回测有效的K线形态，分成「买点已出现 / 等买点 / 要小心」 | 每天 |
| 量化系统 | 8 信号市场状态分、个股交易开关、今天出现买点的动量股；完整量化报告（研究、23 年回测、进出场规则、什么时候拿现金）在 [quant.html](https://yeohkj-dev.github.io/jlaw-daily-report/quant.html) | 每天 |
| 风险计算 | 嵌入仓位风险计算器，按大盘状态预选灯号 | 跟大盘状态 |

顶部的「数据核对」汇总各模块的检查结果（来源数量、数据新鲜度、Yahoo 与 TradingView 两源对照等）。
有严重问题时，这次运行会失败、网站保留上一份报告，GitHub 会发邮件通知。

网页：https://yeohkj-dev.github.io/jlaw-daily-report/ ；历史报告在 `archive/`（保留最近 30 份）。

Telegram：每个交易日早上发「早报」，开市前约 30 分钟发「盘前提醒」（需要 Secrets `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`）。

## 运行时间
- 平日版：周一至周五 UTC 22:30（马来西亚/香港时间次日早上 6:30）
- 周末版：周日 UTC 23:30（马来西亚/香港时间周一早上 7:30）

也可以在 **Actions → 每日报告 → Run workflow** 手动运行。

## 在自己电脑上运行
```
python tools/jlaw_daily_report.py
```
会在本地生成 `每日报告/最新报告.html` 并自动打开。加 `--weekend` 或 `--weekday` 可以强制生成周末版或平日版。

## 文件
| 路径 | 内容 |
|---|---|
| `tools/market_regime.py` | 大盘报告 |
| `tools/jlaw_daily_screen.py` | 每日选股 |
| `tools/luk_screens.py` | Luk 选股（TradingView 选股器，名单存于 `Luk选股/`） |
| `tools/morning_brief.py` | 早报（同一份内容也可用于 Telegram 推送） |
| `tools/premarket_brief.py` | 盘前提醒（开市前约 30 分钟发到 Telegram：期货走向、选股名单盘前表现、Luk 盘前跳空股） |
| `tools/intraday_alerts.py` | 盘中买点提醒（日线信号后在 2 小时图找买点，发 Telegram） |
| `回测/mtf/` | 多时间框架研究（哪个时间框架买、哪个卖）和图例 |
| `tools/weekend_brief.py` | 周末版早报（周末新闻、周日晚期货、上周回顾、下周要看什么；周一早上发 Telegram） |
| `tools/news_digest.py` | 新闻整理（RSS + 规则，不用 AI） |
| `tools/weekly_events.py` | 本周重大事件 / 本周回顾（合并本周每天的新闻 JSON，存放在 `新闻/`） |
| `tools/earnings_valuation.py` | 业绩与两年估值 |
| `tools/earnings_options.py` | 财报前的期权（预期涨跌、看涨/看跌未平仓最多的价位、最大痛点），放在业绩与估值分页最上面 |
| `tools/positioning.py` | 大资金在哪里买卖（CFTC 期货持仓 + CTA 趋势模型估算的买卖价位和金额），接在大盘报告后面 |
| `tools/weekly_outlook.py` | 每周展望 |
| `tools/common.py` | 共用的数据下载和网页小部件 |
| `tools/jlaw_daily_report.py` | 依次运行上面各模块，合并成多分页网页 |
| `tools/telegram_send.py` | 把早报 / 盘前提醒发到 Telegram（同一份只发一次） |
| `回测/` | 选股回测脚本（数据缓存不进仓库） |
| `docs/` | 网站（GitHub Pages 从这里发布） |

数据来自 Yahoo Finance（含期权链）、TradingView 公开选股器、CFTC（期货持仓）、SEC EDGAR、CNBC / MarketWatch / Yahoo Finance / Google News 的 RSS、Forex Factory 经济日历。
规则依据 J Law 的 TTT 课程与公开视频整理，是程序化的近似；新闻和业绩总结都按规则生成，没有使用 AI 改写。

**仅供学习，不构成投资建议。**
