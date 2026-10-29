# J Law 每日报告

GitHub Actions 自动运行，生成一个多分页的网页：

| 分页 | 内容 | 更新 |
|---|---|---|
| 大盘报告 | J Law 大盘体温计（躺赚 / 警戒 / 血汗钱）：出货日、突兀走势、市场宽度、见底信号 | 每个交易日 |
| 每日选股 | 第二阶段股票池里的「META 回调」和「VCP 突破」候选股，附买点、止损和业绩日期 | 每个交易日 |
| 今日新闻 / 周末新闻 | 最上面是「本周重大事件」（本周走势、重要经济数据、大公司财报、本周最重大新闻，逐日累加；周末变成本周回顾），下面是当天影响市场的新闻（按主题归类、多家媒体报道的优先）、市场快照、美国经济日历 | 每个交易日；周日晚上出周末版 |
| 业绩与估值 | 11 个板块各前 10 大公司：最新季度业绩 vs 预期、公司展望原文（SEC 8-K）、分析师预期修正、两年估值情景 | 每天 |
| 每周展望 | 9 个因素打分判断下周方向（偏多 / 中性 / 偏空）、板块轮动、下周经济日历和大公司业绩 | 每周日晚上 |

顶部的「数据核对」汇总各模块的检查结果（来源数量、数据新鲜度、Yahoo 与 TradingView 两源对照等）。
有严重问题时，这次运行会失败、网站保留上一份报告，GitHub 会发邮件通知。

网页：`https://<你的用户名>.github.io/jlaw-daily-report/`；历史报告在 `archive/`（保留最近 30 份）。

## 运行时间
- 平日版：周一至周五 UTC 22:30（马来西亚/香港时间次日早上 6:30）
- 周末版：周日 UTC 23:00（马来西亚/香港时间周一早上 7:00）

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
| `tools/news_digest.py` | 新闻整理（RSS + 规则，不用 AI） |
| `tools/weekly_events.py` | 本周重大事件 / 本周回顾（合并本周每天的新闻 JSON，存放在 `新闻/`） |
| `tools/earnings_valuation.py` | 业绩与两年估值 |
| `tools/weekly_outlook.py` | 每周展望 |
| `tools/common.py` | 共用的数据下载和网页小部件 |
| `tools/jlaw_daily_report.py` | 依次运行上面各模块，合并成多分页网页 |
| `docs/` | 网站（GitHub Pages 从这里发布） |

数据来自 Yahoo Finance、TradingView 公开选股器、SEC EDGAR、CNBC / MarketWatch / Yahoo Finance / Google News 的 RSS、Forex Factory 经济日历。
规则依据 J Law 的 TTT 课程与公开视频整理，是程序化的近似；新闻和业绩总结都按规则生成，没有使用 AI 改写。

**仅供学习，不构成投资建议。**
