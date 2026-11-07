"""早报逐项交叉核对：每个数字都用第二个来源再算一次（TradingView ↔ Yahoo、BLS ↔ 新闻 / Forex Factory）。

用法：python brief_check.py [输出目录] [--date YYYY-MM-DD]
输出：每项一行 dict(item, brief, check, source, ok)；被 morning_brief 调用时结果写进页头「数据核对」。
"""
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import tv_scan, yahoo_chart

# 早报用的 TradingView 代码 → Yahoo 代码、允许误差、单位
PAIRS = {
    "AMEX:SPY": ("SPY", 0.15, "%"), "NASDAQ:QQQ": ("QQQ", 0.15, "%"), "AMEX:IWM": ("IWM", 0.15, "%"),
    "TVC:US10Y": ("^TNX", 0.03, "lvl"), "TVC:VIX": ("^VIX", 0.3, "lvl"), "TVC:DXY": ("DX-Y.NYB", 0.15, "%"),
    # 期货：TradingView 用官方结算价，Yahoo 用收盘前最后成交价，当天涨跌本来就会差一点；
    # 所以核对「前一天结算价」是否一致（同一个合约、同一个基准），再列出两边的涨跌
    "NYMEX:CL1!": ("CL=F", 0.25, "fut"), "COMEX:GC1!": ("GC=F", 0.25, "fut"),
}
for s in ("XLK", "XLY", "XLC", "XLF", "XLI", "XLB", "XLE", "XLV", "XLP", "XLU", "XLRE"):
    PAIRS[f"AMEX:{s}"] = (s, 0.15, "%")


def yahoo_day(sym, day):
    """Yahoo：这一天的收盘和前一个交易日收盘（日线没有这一天时用「最新价」）。"""
    bars, meta = yahoo_chart(sym, "1mo", "1d")
    rows = [(dt.datetime.fromtimestamp(b["t"], dt.timezone.utc).date(), b["c"]) for b in bars]
    if rows and rows[-1][0] < day and meta.get("regularMarketTime"):
        md = dt.datetime.fromtimestamp(meta["regularMarketTime"], dt.timezone.utc).date()
        if md == day:
            rows.append((day, meta["regularMarketPrice"]))
    for i in range(len(rows) - 1, 0, -1):
        if rows[i][0] == day:
            return rows[i][1], rows[i - 1][1]
    return None, None


def check_quotes(tv, day):
    """tv: {TradingView 代码: dict(close, chg)}，逐个和 Yahoo 比。"""
    out = []
    for t, q in tv.items():
        if t not in PAIRS or q is None:
            continue
        ysym, tol, unit = PAIRS[t]
        try:
            c, p = yahoo_day(ysym, day)
        except Exception:
            c = p = None
        if c is None or p is None:
            out.append(dict(item=t, brief=q, check=None, source=f"Yahoo {ysym}", ok=None))
            continue
        if unit == "fut":
            tv_prev = q["close"] / (1 + q["chg"] / 100)
            same = abs(tv_prev / p - 1) * 100 <= tol
            out.append(dict(item=t, brief=round(q["chg"], 2), check=f"前一天结算 {tv_prev:.2f} vs {p:.2f}；Yahoo 最后成交价 {(c / p - 1) * 100:+.2f}%",
                            source=f"Yahoo {ysym}", ok=same))
            continue
        if unit == "%":
            mine, other = q["chg"], (c / p - 1) * 100
        else:                                                   # 美债收益率、VIX：比收盘水平
            mine, other = q["close"], c
        out.append(dict(item=t, brief=round(mine, 2), check=round(other, 2), source=f"Yahoo {ysym}", ok=abs(mine - other) <= tol))
    return out


def check_movers(movers, day):
    out = []
    for k in ("up", "down"):
        for r in movers.get(k, [])[:3]:
            try:
                c, p = yahoo_day(r["name"].replace(".", "-"), day)
                other = (c / p - 1) * 100 if c and p else None
            except Exception:
                other = None
            out.append(dict(item=r["name"], brief=round(r["change"], 2), check=None if other is None else round(other, 2),
                            source="Yahoo", ok=None if other is None else abs(r["change"] - other) <= 0.3))
            if r.get("market_cap_basic") is not None:
                out.append(dict(item=f"{r['name']} 市值 ≥500 亿", brief=round(r["market_cap_basic"] / 1e9), check=None,
                                source="TradingView", ok=r["market_cap_basic"] >= 5e10))
    return out


def check_bls(past, stories):
    """BLS 实际值 vs 新闻里的数字和描述（例如「stronger-than-expected」「165,000」）。"""
    import bls
    out = []
    for ev in past:
        a = bls.actual(ev["title"], dt.datetime.fromisoformat(ev["when"]))
        if not a:
            continue
        vs = bls.versus(a, ev.get("forecast"))
        text = " ".join((s["title"] + " " + (s.get("desc") or "")) for s in stories).lower()
        n = abs(a["value"])
        found = (f"{int(n):,}" in text or f"{int(n)},000" in text) if ev["title"].startswith("Non-Farm") else (f"{a['value']:.1f}%" in text)
        tone = None
        if ev["title"].startswith("Non-Farm") and vs == "高于预期":
            tone = any(w in text for w in ("stronger", "blowout", "strong jobs", "hiring picks up"))
        elif ev["title"] == "Unemployment Rate" and vs:
            down = vs == "低于预期"
            tone = bool(re.search(r"unemployment (rate )?(falls|fell|drops|dropped|dips|ticks down|declines)" if down else
                                  r"unemployment (rate )?(rises|rose|climbs|jumps|ticks up|increases)", text))
        out.append(dict(item=ev["title"], brief=a["actual"], check=("新闻里有相同数字" if found else "新闻方向一致" if tone else "新闻里没有找到这个数字"),
                        source="BLS 官方 vs 当天新闻", ok=True if (found or tone) else None))
    return out


def check_earnings(ers, day):
    if not ers:
        return []
    rows = tv_scan({"symbols": {"tickers": [f"{ex}:{s}" if ex else s for s, ex in ers]}, "columns": ["name", "earnings_release_next_date"]})
    out = []
    for r in rows:
        ts = r["d"][1]
        d = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date() if ts else None
        out.append(dict(item=f"{r['d'][0]} 业绩日期", brief="下个交易日", check=str(d), source="TradingView", ok=None if d is None else d > day))
    return out


def summary(rows):
    bad = [r for r in rows if r["ok"] is False]
    unk = [r for r in rows if r["ok"] is None]
    return dict(name="早报逐项核对", ok=not bad, critical=False,
                detail=f"{len(rows) - len(bad) - len(unk)}/{len(rows)} 项一致" + (f"；不一致：{'、'.join(r['item'] for r in bad)}" if bad else "")
                + (f"；无法核对 {len(unk)} 项" if unk else ""))
