# J Law 每日报告

每个美股交易日收盘后，GitHub Actions 自动运行，生成一个有两个分页的网页：

- **大盘报告**：J Law 大盘体温计（躺赚 / 警戒 / 血汗钱），包括出货日、突兀走势、市场宽度和见底信号
- **每日选股**：第二阶段股票池里的「META 回调」和「VCP 突破」候选股，附买点、止损和业绩日期

网页：在仓库 Settings → Pages 打开后，网址是 `https://<你的用户名>.github.io/jlaw-daily-report/`；历史报告在 `archive/`（保留最近 60 份）。

## 运行时间
每周一至周五 UTC 22:30（马来西亚/香港时间次日早上 6:30）。也可以在 **Actions → 每日报告 → Run workflow** 手动运行。

## 在自己电脑上运行
```
python tools/jlaw_daily_report.py
```
会在本地生成 `每日报告/最新报告.html` 并自动打开。

## 文件
| 路径 | 内容 |
|---|---|
| `tools/market_regime.py` | 大盘报告 |
| `tools/jlaw_daily_screen.py` | 每日选股 |
| `tools/jlaw_daily_report.py` | 依次运行上面两个，合并成两个分页的网页 |
| `docs/` | 网站（GitHub Pages 从这里发布） |
| `大盘报告/大盘历史.csv`、`每日选股/*.csv` | 每天的数据，用来和前一天比较 |

数据来自 Yahoo Finance 和 TradingView 公开选股器。规则依据 J Law 的 TTT 课程与公开视频整理，是程序化的近似。

**仅供学习，不构成投资建议。**
