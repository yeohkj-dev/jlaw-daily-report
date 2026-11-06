"""量化系统的数据：
1. ETF / 指数 / VIX（1998 起）→ data/macro.pkl
2. 股票池：TradingView 美股（NYSE/NASDAQ/AMEX 普通股，市值 ≥3 亿，日均成交额 ≥1,000 万美元）→ data/universe.json
3. 个股日线（Yahoo，5 年）→ data/stocks/<代号>.json；已有的只补最近 3 个月，发现拆股（重叠日期价格对不上）就整只重下
数据核对结果写到 data/checks.json（报告页头「数据核对」会显示）。
GitHub Actions 用 actions/cache 保存 data/，所以平常每天只补几天的数据。
"""
import datetime as dt
import json
import os
import sys
import time

import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
STK = os.path.join(DATA, "stocks")
os.makedirs(STK, exist_ok=True)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

MACRO = ["SPY", "QQQ", "IWM", "RSP", "TLT", "IEF", "SHY", "BIL", "HYG", "LQD", "GLD", "^VIX", "^VIX3M",
         "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC", "SMH", "EFA", "EEM", "DBC", "UUP"]
ET = dt.timezone(dt.timedelta(hours=-5))
now_et = dt.datetime.now(dt.timezone.utc).astimezone(ET)
# 美股还没收盘时，今天那一根是盘中数据，不要
cutoff = now_et.date() if now_et.hour * 60 + now_et.minute >= 16 * 60 + 30 else now_et.date() - dt.timedelta(days=1)
checks = []


def check(name, ok, detail, critical=False):
    checks.append(dict(name=name, ok=bool(ok), detail=detail, critical=critical))


def dl(tickers, **kw):
    for i in range(3):
        try:
            return yf.download(tickers, progress=False, threads=True, **kw)
        except Exception as e:           # 限流等暂时错误：等一下再试
            print("下载失败，重试", e, flush=True)
            time.sleep(10 * (i + 1))
    return None


# ---------------------------------------------------------------- 1. ETF / 指数
df = dl(MACRO, start="1998-01-01", auto_adjust=True)
if df is not None and not df.empty:
    px = df["Close"]
    px = px[px.index.date <= cutoff]
    px.to_pickle(os.path.join(DATA, "macro.pkl"))
px = pd.read_pickle(os.path.join(DATA, "macro.pkl"))
last = px["SPY"].dropna().index[-1].date()
age = (cutoff - last).days
check("ETF/VIX 数据日期", age <= 4, f"SPY 最新 {last}（{age} 天前）", critical=age > 6)

# ---------------------------------------------------------------- 2. 股票池
uni_path = os.path.join(DATA, "universe.json")
try:
    from common import tv_scan
    cols = ["name", "description", "exchange", "market_cap_basic", "close", "sector", "industry", "average_volume_30d_calc"]
    body = {"filter": [{"left": "type", "operation": "equal", "right": "stock"},
                       {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
                       {"left": "market_cap_basic", "operation": "egreater", "right": 3e8}],
            "columns": cols, "range": [0, 6000]}
    rows = [dict(zip(cols, r["d"])) for r in tv_scan(body)]
    rows = [r for r in rows if (r["close"] or 0) * (r["average_volume_30d_calc"] or 0) >= 1e7 and "." not in r["name"][1:] and "/" not in r["name"]]   # 不要优先股（WFC/PL 等）
    if len(rows) > 1500:
        json.dump(rows, open(uni_path, "w", encoding="utf-8"), ensure_ascii=False)
except Exception as e:
    print("TradingView 股票池失败，沿用上一份：", e, flush=True)
uni = json.load(open(uni_path, encoding="utf-8"))
syms = sorted({u["name"] for u in uni} - {"SPY", "QQQ"})
check("股票池（TradingView）", len(syms) > 1500, f"{len(syms)} 只")

# ---------------------------------------------------------------- 3. 个股日线
def save(sym, frame):
    frame = frame.dropna(subset=["Close"])
    frame = frame[frame.index.date <= cutoff]
    if len(frame) < 300:
        return False
    out = {"d": [t.strftime("%Y-%m-%d") for t in frame.index]}
    for k, c in zip("ohlcv", ["Open", "High", "Low", "Close", "Volume"]):
        out[k] = [None if pd.isna(x) else round(float(x), 4) for x in frame[c]]
    json.dump(out, open(os.path.join(STK, sym + ".json"), "w"))
    return True


def batch(symbols, period):
    got = {}
    for i in range(0, len(symbols), 100):
        part = symbols[i:i + 100]
        d = dl([s.replace(".", "-") for s in part], period=period, auto_adjust=False, group_by="ticker")
        if d is None or d.empty:
            continue
        for s in part:
            try:
                x = d[s.replace(".", "-")] if len(part) > 1 else d
                got[s] = x.dropna(subset=["Close"])
            except KeyError:
                pass
        print(f"  {period}: {min(i + 100, len(symbols))}/{len(symbols)}", flush=True)
    return got


have = {f[:-5] for f in os.listdir(STK) if f.endswith(".json")}
for f in have - set(syms):                    # 不在股票池了就删掉
    os.remove(os.path.join(STK, f + ".json"))
new = [s for s in syms if s not in have]
old = [s for s in syms if s in have]
redo = []
recent = batch(old, "3mo") if old else {}
for s in old:
    x = recent.get(s)
    if x is None or x.empty:
        continue
    d = json.load(open(os.path.join(STK, s + ".json")))
    known = dict(zip(d["d"], d["c"]))
    over = [(t.strftime("%Y-%m-%d"), c) for t, c in zip(x.index, x["Close"]) if t.strftime("%Y-%m-%d") in known]
    if over and any(abs(c / known[t] - 1) > 0.02 for t, c in over[-5:] if known[t]):
        redo.append(s); continue                  # 拆股 / 调整：整只重下
    add = x[(x.index.strftime("%Y-%m-%d") > d["d"][-1]) & (x.index.date <= cutoff)]
    for t, r in add.iterrows():
        d["d"].append(t.strftime("%Y-%m-%d"))
        for k, c in zip("ohlcv", ["Open", "High", "Low", "Close", "Volume"]):
            d[k].append(None if pd.isna(r[c]) else round(float(r[c]), 4))
    json.dump(d, open(os.path.join(STK, s + ".json"), "w"))
full = batch(new + redo, "5y") if new + redo else {}
n_new = sum(save(s, x) for s, x in full.items())
print(f"个股：更新 {len(old)}，新下载 {n_new}/{len(new)}，重下 {len(redo)}", flush=True)

fresh = 0
for s in syms:
    p = os.path.join(STK, s + ".json")
    if os.path.exists(p):
        with open(p) as fh:
            txt = fh.read()
        i = txt.find('"d": [')
        dates = json.loads(txt[i + 5: txt.index("]", i) + 1])
        fresh += dates[-1] == str(last)
share = fresh / max(1, len(syms))
check("个股日线（Yahoo）", share > 0.85, f"{fresh}/{len(syms)} 只更新到 {last}（{share:.0%}）", critical=share < 0.5)
json.dump(checks, open(os.path.join(DATA, "checks.json"), "w", encoding="utf-8"), ensure_ascii=False)
for c in checks:
    print("✔" if c["ok"] else "✘", c["name"], c["detail"])
