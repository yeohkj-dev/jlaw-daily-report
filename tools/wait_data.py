"""等 Yahoo 日线更新到最新交易日再开始（daily.yml 的第一步）。

2026-11-17 的教训：GitHub 在美东收盘后约 2 小时运行，Yahoo 的日线还没有 11-17 那一根（meta 的现价已经是 11-17），
大盘、量化、选股、主题雷达全部用了 11-16 的数据，页面看起来像「没更新」。
做法：抽查几只大股票，比较「日线最后一根的日期」和「meta.regularMarketTime 的日期」（美东）。
全部一致就开始；不一致就每 5 分钟再查一次，最多等 60 分钟，然后照样继续（报告里各模块会显示数据日期）。
只在平日版用；周末版不用等。结果写到 GITHUB_STEP_SUMMARY（有的话）。
用法：python tools/wait_data.py [--max-min 60] [--every-min 5]
"""
import datetime as dt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import yahoo_chart

SYMS = ["SPY", "QQQ", "AAPL", "MSFT", "JPM", "XLE"]
ET = dt.timezone(dt.timedelta(hours=-5))      # 冬令时；夏令时差 1 小时不影响「日期」判断（收盘 16:00 美东）


def status():
    """回传 (全部已更新?, 说明)。"""
    lag = []
    for s in SYMS:
        try:
            bars, meta = yahoo_chart(s, "5d", "1d")
        except Exception as e:
            lag.append(f"{s} 取不到（{type(e).__name__}）")
            continue
        last = dt.datetime.fromtimestamp(bars[-1]["t"], dt.timezone.utc).astimezone(ET).date() if bars else None
        mt = meta.get("regularMarketTime")
        cur = dt.datetime.fromtimestamp(mt, dt.timezone.utc).astimezone(ET).date() if mt else None
        if cur and last and last < cur:
            lag.append(f"{s} 日线到 {last}，现价是 {cur}")
    return (not lag), "；".join(lag) or "日线都已更新到最新交易日"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    max_min = int(argv[argv.index("--max-min") + 1]) if "--max-min" in argv else 60
    every = int(argv[argv.index("--every-min") + 1]) if "--every-min" in argv else 5
    t0 = time.time()
    while True:
        ok, why = status()
        waited = (time.time() - t0) / 60
        print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M} UTC，已等 {waited:.0f} 分钟] {why}", flush=True)
        if ok or waited + every > max_min:
            break
        time.sleep(every * 60)
    msg = (f"✔ Yahoo 日线已更新（等了 {waited:.0f} 分钟）" if ok else f"⚠ 等了 {waited:.0f} 分钟 Yahoo 日线还没更新：{why}。照样继续，页面会显示数据日期。")
    print(msg)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
