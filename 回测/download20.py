"""20 年版数据：同一个股票池（universe.json，今天还在交易的约 2,250 只 + SPY/QQQ），Yahoo 全部历史日线，
只留 2005-01-01 之后，存到 回测/cache20/（格式同 cache/）。K线已按拆股调整（yahoo_chart）。
注意：只能拿到今天还在交易的股票（幸存者偏差），年份越长偏差越大。"""
import datetime as dt
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from common import fetch_json
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cache20")
os.makedirs(OUT, exist_ok=True)
START = "2005-01-01"


def one(sym):
    path = os.path.join(OUT, sym + ".json")
    if os.path.exists(path):
        return "have"
    for attempt in range(3):
        try:
            p1 = int(dt.datetime(2005, 1, 1, tzinfo=dt.timezone.utc).timestamp()); p2 = int(time.time())
            j = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym.replace('.', '-'))}?period1={p1}&period2={p2}&interval=1d&events=split")
            r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]
            bars = [dict(t=t, o=q["open"][i], h=q["high"][i], l=q["low"][i], c=q["close"][i], v=q["volume"][i] or 0)
                    for i, t in enumerate(r.get("timestamp") or []) if q["close"][i] is not None]
            break
        except Exception:
            time.sleep(2 + 3 * attempt)
    else:
        return "fail"
    d = [dt.datetime.fromtimestamp(b["t"], dt.timezone.utc).date().isoformat() for b in bars]
    keep = [i for i, x in enumerate(d) if x >= START]
    if len(keep) < 300:
        return "short"
    out = {"d": [d[i] for i in keep]}
    for k in "ohlcv":
        out[k] = [bars[i][k] for i in keep]
    with open(path, "w") as f:
        json.dump(out, f)
    return "ok"


def main():
    rows = json.load(open(os.path.join(HERE, "universe.json"), encoding="utf-8"))
    syms = [r["name"] for r in rows]
    t0 = time.time()
    res = {}
    with ThreadPoolExecutor(6) as ex:
        for n, (s, r) in enumerate(zip(syms, ex.map(one, syms))):
            res[r] = res.get(r, 0) + 1
            if n % 200 == 0:
                print(n, s, r, res, round(time.time() - t0), "s", flush=True)
    print("完成", res, round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
