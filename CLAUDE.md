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
2026-11-06 起分页分成 **4 大类**（`tools/jlaw_daily_report.py` 的 `GROUPS`），每类下面是小分页；网站默认打开「今天怎么做 → 综合名单」：
- **今天怎么做**：综合名单 · 早报 · 风险计算
- **大盘**：大盘报告 · 量化系统 · 每周展望
- **选股**：每日选股 · Luk 选股
- **新闻·业绩**：今日新闻 · 业绩与估值

面板仍是平的 `<div class="panel" id="p-<key>">`（`published_panel()` 靠这个取上一份）；小分页按钮的 class 是 `stab`（不要用 `sub`，各分页内容里 `.sub` 是小字样式）。记住上次打开的小分页用 localStorage `jlaw-tab2`。用户要求网站简单、不要太多分页，加新内容优先放进现有分页或大类。

| 分页 | 程序 | 内容 |
|---|---|---|
| 早报 | `tools/morning_brief.py` | 昨晚美股发生什么、相关新闻（为什么）、行业、大公司异动、今晚要看什么 |
| 大盘报告 | `tools/market_regime.py` | J Law 大盘体温计（躺赚 / 警戒 / 血汗钱）、恐惧指数（CNN + VIX）、行业 ETF 追踪、信用市场（科技 / AI 公司债利差）、见底信号 |
| 每日选股 | `tools/jlaw_daily_screen.py` | J Law META 回调、VCP 突破、观察名单、Stage 1→2 候选、Stage 2 名单 |
| Luk 选股 | `tools/luk_screens.py` | Martin Luk 的 Leaders / Strong Day / Gappers（条件来自 Luk 本人公布的 TradingView 设置） |
| 今日新闻 | `tools/news_digest.py` + `tools/weekly_events.py` | 上面是本周重大事件（周末是本周回顾 + 下周看点），下面是当天新闻 |
| 业绩与估值 | `tools/earnings_valuation.py` | 11 个板块各前 10 大公司的业绩、指引原文（SEC 8-K）、两年估值情景 |
| 每周展望 | `tools/weekly_outlook.py` | 9 个因素打分判断下周方向（周日更新） |
| 综合名单 | `量化/combined.py`（由 `combined_tab()` 在每日选股、Luk 选股之后运行，写 `量化/data/combined.html`） | 量化红绿灯和 J Law 大盘灯取较严的；J Law 就绪/观察、量化动量前 40、Luk 名单合并；只用回测「有效」的K线形态（看涨加分，看跌放进「要小心」）。分三组：买点已出现 / 等买点（≥2 个系统看好）/ 要小心（J Law 或量化名单里跌破 50 日线或出现有效看跌K线，最多 15 只） |
| 量化系统 | `量化/run.py`（分页内容 `量化/data/tab.html`，完整报告发布成 `docs/quant.html`） | 8 信号市场状态分、个股交易开关（进攻 / 谨慎 / 现金）、今天出现买点的动量股、链接到完整量化报告（研究、23 年回测、进出场规则） |
| 风险计算 | `tools/jlaw_daily_report.py` 里的 `risk_tab()` | 用 iframe 嵌入风险计算器，网址带 `?light=green|yellow|red`（按大盘状态预选灯号） |

### RS Rating（2026-11-07 加入）
- `tools/rs_rating.py`：IBD 式 1–99。分数 = `2×c/c[63] + c/c[126] + c/c[189] + c/c[252]`，在量化系统的股票池（`量化/data/stocks/`，约 2,250 只）里排百分位。`jlaw_daily_report.py` 的 `main()` 一开始就算（每日选股、Luk、综合名单要读），写 `量化/data/rs_rating.json`，发布时把 1–99 门槛表写成 `docs/rs_table.json`。
- 显示：每日选股、Luk 选股、综合名单的股票代码旁有「RS 92」小标记（`badge()`）；每日选股最后有「D. RS Rating 前 30」（`top_table()`）。
- **每日选股「A0. 回测最佳」（2026-11-08 加入）**：META 就绪（A1 同条件）里 RS ≥ 90 的股票，附白话做法（次日开盘买、收盘比买价跌 8% 次日开盘卖、预挂 −12% 保护单、否则拿 60 个交易日、每只约账户 12.5%）、按今天收盘估的 −8% / −12% 价位、最迟卖出日（只跳周末，标「约」），以及今天 SPY 在不在 200 天线上（回测里 SPY 在 200 天线下时这系统没优势 → 页面写「不开新仓」；账户回测 SPY 跌破就不买、没持股的钱放 QQQ 每年 +19.3% vs 一直拿 QQQ +14.4%，见用户本机 交易系统总结 8d）。回测数字是 `jlaw_daily_screen.py` 顶部的 `BEST_BT` 常数（来自 `回测/meta_trades20_rs.pkl`、`回测/K线形态/rs_sys20.json`），重跑回测要人工同步。RS 门槛不要放宽：RS ≥ 80 在 2016–2026 账户回测 10 次全输 SPY。
- 排名日 = 最近一个 ≥90% 股票有收盘的交易日（Yahoo 收盘后一段时间只有部分股票更新）。如果不是最新交易日（个股和 SPY 取较新的），三个名单上方显示红字提示、RS 标记带「*」（`stale_note()`），用户要求「RS 是前天的要让我知道」。
- 数据核对：前 40 名收盘价逐只对 TradingView 选股器 `close`（差 ≤0.5%）；3 个月涨幅对 `Perf.3M` 看差距中位数 ≤5 个百分点（日历月 vs 63 根K线，只用来抓拆股之类的大错）。排名日不是最新交易日时这项跳过并提醒。
- 2026-11-07 用户决定 TradingView 的 Pine 指标**不放 RS Rating**（TradingView 读不到每天的门槛表），RS Rating 只在这个网站。`docs/rs_table.json` 仍照常发布，目前没有程序读它。

`tools/jlaw_daily_report.py` 依次运行各模块，合并成一个多分页网页，写到 `docs/`（GitHub Pages 从 `main` 分支的 `docs/` 发布）。页头有更新时间、下次更新时间和「数据核对」汇总。

## 2. 自动运行（GitHub Actions）

| 工作流 | 时间（UTC） | 马来西亚时间 | 做什么 |
|---|---|---|---|
| `.github/workflows/daily.yml`「每日报告」 | 周一至五 22:30；周日 23:30 | 周二至六 06:30；周一 07:30 | 生成报告 → 发布网站 → 发 Telegram 早报（周一发周末版） → 把数据提交回仓库 |
| `.github/workflows/premarket.yml`「盘前提醒」 | 周一至五 12:00–14:40 每 20 分钟 | 美国冬令时约晚上 10:00，夏令时约 9:00 | 只在美东 08:50–09:29 之间（开市前约 30 分钟）发 Telegram 盘前提醒，一天只发一次 |
| `.github/workflows/intraday.yml`「盘中买点提醒」 | 周一至五 13:05–21:35 每 30 分钟 | 晚上 9:30 至早上 5:30 | 读 `每日选股/pending.json`，2 小时K线出现买点就发 Telegram（同一只同一天一次，记录在 `早报/_intraday_sent.json`） |
| `.github/workflows/telegram-test.yml`「Telegram 测试」 | 只能手动 | — | 把最新早报再发一次，测试 Telegram 设置 |

- **Secrets**（仓库 Settings → Secrets and variables → Actions）：`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`。由用户自己填，**不要让用户把 token 贴给你，也不要代填**。
- 平日版用 `--strict`：数据核对有严重问题时这次运行失败、网站保留上一份，GitHub 会发邮件给用户。
- 周末版不重跑大盘、选股、Luk、早报，改用网站上一份（`published_panel()` 从 `docs/index.html` 取出分页）。
- **GitHub 会停用 60 天没有活动的公开仓库排程**。机器人每天都会提交，所以正常不会发生；如果 Actions 页面出现「This scheduled workflow is disabled」，点 **Enable workflow** 即可。
- 手动运行：Actions → 选工作流 → **Run workflow**。

- **量化系统**在 daily.yml 里先于报告运行（`continue-on-error`，失败时分页沿用网站上一份，页头数据核对显示「量化」的提醒，不会阻止报告发布）。个股数据约 2,250 只 × 5 年存在 `量化/data/`（不进仓库），靠 `actions/cache` 在每天之间保存；缓存不见了（7 天没用或被清）会整份重下，约多 5–10 分钟。

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
- **早报的数字用 TradingView**（指数、行业 ETF、`TVC:US10Y` / `TVC:VIX` / `TVC:DXY` / `NYMEX:CL1!` / `COMEX:GC1!`，期货按结算价），Yahoo 只用来核对指数（相差 >0.15 个百分点会在数据核对提醒）。用户在 TradingView 看到的是同一个数字。
- **早报「为什么」只能用当天的新闻**（上一个交易日美东 16:00 之后发布的）；以前连前一天的新闻也读，大涨日会出现前一天「大跌」的标题。个股异动的新闻可以多看一天（公司常在前一天收盘后公布业绩）。
- **经济数据的实际值**：Forex Factory 免费日历只有预期和前值。非农、失业率、平均时薪、CPI、PPI 的实际值来自 `tools/bls.py`（美国劳工统计局免费 API v1，一次请求、缓存 6 小时，每天限 25 次），早报和本周重大事件都会显示「实际 / 预期 / 高于或低于预期」。**不要把预期值写得像实际值**（用户曾以为 65K 是非农实际值，其实是预期；实际是 +165K）。
- **早报逐项交叉核对**：`tools/brief_check.py` 每天把早报的每个数字用第二来源再算一次（TradingView ↔ Yahoo、BLS ↔ 新闻、业绩日期），结果存在 `早报/<日期>.json` 的 `crosscheck`，摘要在页头「数据核对」。期货（油、金）TradingView 用结算价、Yahoo 用最后成交价，所以核对的是前一天结算价是否一致。
- **周末版**（`tools/weekend_brief.py`，2026-11-09 加入）：周日 UTC 23:30 的周末运行里产生（期货美东周日 18:00 开盘后），内容是周末新闻（周五收盘后）、周日晚期货、上周涨跌（周五对周五）、下周经济日历和大公司业绩；网站「早报」分页周末换成这份，Telegram 用 `telegram_send.py --weekend` 发（记录在 `早报/_weekend_sent.txt`）。本机测试：`python tools/weekend_brief.py . --force --asof <某个周日>`。TradingView 的 `Perf.W` 是最近 7 天、不一定是周五对周五，不要拿来当「上周」。
- 新闻挑选会排除纯政治新闻（`POLITICS_RX`：调查、选举、议员…），除非标题同时讲到关税、利率、油价、战争等（`POLICY_RX`）。
- Telegram 一则信息最多 4,096 字，`telegram_send.split()` 会在段落之间切成几则。
- **所有股票代码都要链接到 TradingView 图表**（`https://www.tradingview.com/chart/?symbol=交易所:代码`），网站和 Telegram 都一样；交易所从 TradingView 选股器结果的 `s` 字段（如 `NASDAQ:AMD`）或业绩估值 JSON 的 `exchange` 取。共用的 `tools/rs_rating.py` `tv_link(sym, rs=None, ex=None)`（交易所查不到就只用代码，TradingView 也认得）；2026-11-08 已把综合名单、量化分页 / 完整报告、Luk「一眼看懂」、每日选股「新进入就绪名单」、业绩与估值的摘要都改成链接。新加名单一律用它。
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
- **K线形态回测（`回测/K线形态/`）**：2026-11-06 先用 5 年数据（`回测/cache`），**2026-11-07 改用 20 年数据**（`回测/download20.py` → `回测/cache20`，2005 起，不进仓库；`cd 回测/K线形态 && bash run20.sh`，环境变量 `BT_TAG=20`，输出文件名都带 20，例如 `stats20.json`、`stats220.json`（第二批）、`stats320.json`（经典图形）、`stats420.json`（Order Block））。说明和完整结果表在 `回测/K线形态/README.md`（由用户本机 `回测/K线形态/gen_readme.py` 生成）。**20 年里没有一个形态过「有效」**（评级规则：20 天超额 ≥0.25、60 天 ≥0.4、t ≥2、≥70% 年份方向对），5 年版的「有效」都是那几年的运气。`tools/market_regime.py` 的 `bt_note()` 显示「K线形态回测提示」（固定文字，已改成 20 年数字；重跑回测后要人工同步）。`量化/combined.py` 的 `BULL`/`BEAR` 仍是 5 年版的有效形态，改不改等用户决定。用户的持仓清单不放进这个公开仓库。
- **进场 / 止损 / 离场回测（`回测/K线形态/exit_bt.py`，BT_TAG=20 → `exit_bt20.json`）**：逐笔模拟。20 年结论：最稳 = 放量突破 50 日高点（个股升势 + SPY 在 200 天线上）+ 收盘跌 15% 才卖 + 拿 60 天（逐笔比 SPY 多 +0.55%，账户回测 2006–2015、2016–2026 两段都赢 SPY）；紧止损、20 日线跟踪、2R 卖 1/3、拿 20 天都较差；长下影只在几次大恐慌后有效。J Law META 回调（`回测/meta_sig.py` + `meta_exit.py`）用原版卖法 ≈ SPY，改 8% 止损逐笔略好但放进账户输给 SPY。账户回测 `system_bt.py` 和总结页在用户本机（`交易系统总结.html`）。
- **写给用户的 % 一定要说清楚是跟什么比**（同一天全部股票平均？同期 SPY？还是股价本身涨跌？），并附「每投入 $1 万约多少钱」。用户 2026-11-07 反映看不懂没说明的 %。
- **META + RS 最佳系统的后续（2026-11-08）**：`回测/meta_more.py`（同一批进场多测几种卖法 + 跟 QQQ 比）、`回测/K线形态/variants_qqq.py`（账户回测，`system_bt.run(base="SPY"|"QQQ"|"QQQ_T")`，`_T` = SPY 跌破 200 天线时闲钱拿现金）。结论：2006–2026 一直拿 QQQ 每年 14.4%（价格不含股息）；原版钱放 QQQ 15.2% 只勉强赢；**唯一有用的改进 = SPY 站上 200 天线才开新仓 → 19.3%**（回撤 −54% 同 QQQ；闲钱也择时 → 14.6%、回撤 −39%）；放宽止损、RS 高先买、RS≥95、50 天线续拿都没更好；超额主要来自 2020/2024/2025。
- **财报（2026-11-08）**：`回测/earn_fetch.py`（yfinance 历史财报日，约 24 年）→ `earn_test.py` → `K线形态/earn_acct.py`。⭐ 版本照拿过财报每年 19.3%，财报前一天全卖 16.2%，「14 天内有财报不买」18.4%；提前卖没有减少最大回落。所以 A0 名单不因财报提前卖。
- 2026-11 的结论：J Law META / VCP 只有约 +0.1R 的薄优势（只在 5R 目标卖法下），均线移动止损略亏，2026 年转负；Stage 名单没有优势；Luk 名单平均跑赢 SPY 约 0.5%（20 天）但靠少数大赢家；有幸存者偏差。

## 6b. 量化系统（`量化/`，2026-11-06 加入）

- `run.py` 依次运行：`fetch_data.py`（ETF/VIX 1998 起、TradingView 股票池、Yahoo 个股日线增量更新，发现拆股整只重下，写 `data/checks.json`）→ `quant_lab.py`（8 信号市场状态分 + 择时/杠杆/轮动/组合回测，2003 起）→ `signals.py`（个股进出场规则回测约 27 万笔 + 今日信号）→ `oversold.py`（深跌前强势股之后的表现）→ `build_report.py` + `trade_section.py`（完整报告 `data/量化系统.html`）→ 写 `data/tab.html`、`data/summary.json`。分页和完整报告最上面是白话版「今天怎么做」（`simple.py`：红黄绿灯 + 4 个问答 + 3 条规则），研究和回测折叠在完整报告下面。用户看不懂术语，新内容先用白话写结论。
- `jlaw_daily_report.py`：`quant_tab()` 读 `tab.html`（36 小时内的才用），`publish()` 把完整报告复制成 `docs/quant.html`，`quant_checks()` 把量化的数据核对加到页头（一律不算严重）。
- 结论（2026-11）：状态分预测风险不预测涨幅；最佳个股规则 = 动量 Top100 + 52 周新高放量突破 + 跌破 50 日线 / 3×ATR 出场（约 +0.25R/笔，胜率约 31%）；20 日线出场太紧；弱市（宽度 <40%）新买的胜率反而最高；个股回测只有约 3 年且有幸存者偏差。
- **私人持仓**：`signals.py` 只在设置环境变量 `QUANT_HOLDINGS`（本机 Portfolio Dashboard 的 `_engine` 文件夹）时读持仓，GitHub 上不设置，公开网站不会有持仓；代码里也不要写死用户的持股代号。本机私人版：设 `QUANT_HOLDINGS` 和 `QUANT_OUT`（输出到仓库外）后跑 `python 量化/run.py`。
- `combined.py` 用 `回测/K线形态/patterns.py`、`patterns2.py` 的 `detect()`/`detect2()` 判断形态；形态名单 `BULL` / `BEAR` 要和 `回测/K线形态/README.md` 里评为「有效」的一致。
- 本机运行要 `pip install yfinance pandas numpy`；第一次没有 `量化/data/stocks/` 会下载约 2,250 只（约 5–10 分钟）。

## 6c. 多时间框架买卖点（`回测/mtf/`，2026-11-10）

- 研究：`research21.py`（21 年日线 / 周线：A0、META、放量突破 50 日高 BRK、C9 × 买进 D0/D1/D2/+周线 × 卖出 X0/20 天线/50 天线/10 周线）、`mtf_bt.py` + `mtf_exit_bt.py`（3 年 1 / 2 / 4 小时，Yahoo 60 分钟线只有约 3 年，2 / 4 小时由 60 分钟合成）、`c9_rules.py`（C9 课程规则的程序版）、`report_mtf.py` → `多时间框架研究报告.html`、`make_charts.py` → 图例 `docs/img/mtf/*.png`。数据缓存（`cache60/`、pkl）不进仓库；日线缓存和信号读仓库旁边的 `回测/`（`cache20`、`jlaw_sig20.pkl`、`meta_trades20_rs.pkl`）。
- **结论**：小周期用来「买」、不要用来「卖」。最好的是 **2 小时**：BRK 用「当天第一根 2 小时K线高点被收盘突破」（3 年每笔比 SPY +1.27% vs 次日开盘 +0.91%）；A0 用「2 小时收盘重新站上 20 EMA」（+4.82% vs +3.78%，样本小、不显著）。等确认其实是过滤器：同一批信号买得更贵约 1–2%，但避开一半以上会亏的信号。小周期移动止损会砍掉赢家（全部系统变差）；日线 20 天线也太紧。META（全部）和 C9 程序版 21 年都没赢 SPY。
- **数据坑**：Yahoo 有些股票的 60 分钟数据是别的证券（BNY、B、MOD、RGR、SUPN），所以回测只用「60 分钟最后一根收盘和日线收盘差 ≤2%」的日子。
- **网站 / Telegram**：每日选股 A0 的买法改成「5 天内等 2 小时收盘站上 20 EMA」（不方便看盘照旧次日开盘买）；新增「A3. 放量突破 50 日高 · 等 2 小时买点」（`brk_signal()`，SPY 在 200 天线上才出）；`save_pending()` 把 A0（SPY 在 200 天线上时）和 A3 写进 `每日选股/pending.json`（5 个交易日后移除）；`tools/intraday_alerts.py` 盘中检查并发提醒（`--dry-run --force-date --force-time --pending` 可重播过去某天测试）；盘前提醒列出「今天等 2 小时买点」。回测数字在 `jlaw_daily_screen.py` 的 `MTF_BT`。

## 7. 待办 / 还没验证

- 周末版「下周看点」的经济日历只在周六测过（取不到），周日的真实运行还要看结果。
- 盘中买点提醒（2026-11-10 加入）只用过去的日子重播测试过，第一次真正在交易时段运行后要检查 Actions 记录。
- FRED 利差取不到，可考虑其他免费来源。
- 回测建议的改进还没测：分批止盈（2–3R 先卖一半）、只做 RS 最强的前几名、要求热门产业组。

**仅供学习，不构成投资建议。**
