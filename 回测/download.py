"""回测第 1 步：股票池（TradingView 现有美股）+ Yahoo 5 年日线，存到 回测/cache/。

股票池：NYSE / NASDAQ / AMEX 普通股，市值 ≥3 亿美元，30 日平均成交额 ≥1,000 万美元。
注意：只能拿到「今天还在交易」的股票（幸存者偏差）。
"""
import datetime as dt
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from common import tv_scan, yahoo_chart

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)

COLS = ["name", "description", "exchange", "market_cap_basic", "close", "sector", "industry", "average_volume_30d_calc"]


def universe():
    body = {"filter": [{"left": "type", "operation": "equal", "right": "stock"},
                       {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
                       {"left": "market_cap_basic", "operation": "egreater", "right": 3e8}],
            "columns": COLS, "range": [0, 6000]}
    rows = [dict(zip(COLS, r["d"])) for r in tv_scan(body)]
    rows = [r for r in rows if (r["close"] or 0) * (r["average_volume_30d_calc"] or 0) >= 1e7 and "." not in r["name"][1:]]
    return rows


def one(sym):
    path = os.path.join(CACHE, sym + ".json")
    if os.path.exists(path):
        return True
    try:
        bars, meta = yahoo_chart(sym.replace(".", "-"), "5y", "1d")
    except Exception:
        return False
    if len(bars) < 300:
        return False
    out = {"d": [dt.datetime.fromtimestamp(b["t"], dt.timezone.utc).date().isoformat() for b in bars],
           "o": [b["o"] for b in bars], "h": [b["h"] for b in bars], "l": [b["l"] for b in bars],
           "c": [b["c"] for b in bars], "v": [b["v"] for b in bars]}
    with open(path, "w") as f:
        json.dump(out, f)
    return True


def main():
    rows = universe()
    for x in ("SPY", "QQQ"):
        rows.append(dict(name=x, description=x, exchange="AMEX", market_cap_basic=None, close=None, sector="ETF", industry="ETF"))
    with open(os.path.join(HERE, "universe.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    print("股票池", len(rows), flush=True)
    with ThreadPoolExecutor(8) as ex:
        ok = list(ex.map(one, [r["name"] for r in rows]))
    print("下载成功", sum(ok), "/", len(rows))


if __name__ == "__main__":
    main()
