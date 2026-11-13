"""TradingView 经济日历（免费公开接口）：补上 BLS 没有的经济数据实际值，例如每周首次申领失业金（劳工部公布）、
ISM、零售销售、GDP、PCE、密歇根信心、房屋数据等。

Forex Factory 的免费日历只有预期和前值；BLS API 只有非农、失业率、时薪、CPI、PPI。其余数据的实际值从这里取。
BLS 有的数列仍以 BLS 为准，这里的数字用来核对（brief_check.py）。
只在 TradingView 那一项的公布时间和 Forex Factory 同一天（美东）时才配对，避免拿错期。
缓存 20 分钟（新闻/_tvcal_<日期>.json，不进仓库）：公布后几分钟 TradingView 就有实际值。
"""
import datetime as dt
import json
import os
import time
import urllib.request

URL = "https://economic-calendar.tradingview.com/events?from={a}T00:00:00.000Z&to={b}T00:00:00.000Z&countries=US"
# Forex Factory 标题 → (TradingView 标题, 显示方式)。显示方式：chg = 带正负号的变化（非农、ADP），lvl = 水平值，pct = 百分比
MAP = {
    "Unemployment Claims": ("Initial Jobless Claims", "lvl"),
    "Non-Farm Employment Change": ("Non Farm Payrolls", "chg"),
    "ADP Non-Farm Employment Change": ("ADP Employment Change", "chg"),
    "Unemployment Rate": ("Unemployment Rate", "pct"),
    "Average Hourly Earnings m/m": ("Average Hourly Earnings MoM", "pct"),
    "CPI m/m": ("Inflation Rate MoM", "pct"),
    "CPI y/y": ("Inflation Rate YoY", "pct"),
    "Core CPI m/m": ("Core Inflation Rate MoM", "pct"),
    "Core CPI y/y": ("Core Inflation Rate YoY", "pct"),
    "PPI m/m": ("PPI MoM", "pct"),
    "Core PPI m/m": ("Core PPI MoM", "pct"),
    "Core PCE Price Index m/m": ("Core PCE Price Index MoM", "pct"),
    "Retail Sales m/m": ("Retail Sales MoM", "pct"),
    "Core Retail Sales m/m": ("Retail Sales Ex Autos MoM", "pct"),
    "ISM Manufacturing PMI": ("ISM Manufacturing PMI", "lvl"),
    "ISM Services PMI": ("ISM Services PMI", "lvl"),
    "JOLTS Job Openings": ("JOLTs Job Openings", "lvl"),
    "CB Consumer Confidence": ("CB Consumer Confidence", "lvl"),
    "Prelim UoM Consumer Sentiment": ("Michigan Consumer Sentiment Prel", "lvl"),
    "Revised UoM Consumer Sentiment": ("Michigan Consumer Sentiment Final", "lvl"),
    "Advance GDP q/q": ("GDP Growth Rate QoQ Adv", "pct"),
    "Prelim GDP q/q": ("GDP Growth Rate QoQ 2nd Est", "pct"),
    "Final GDP q/q": ("GDP Growth Rate QoQ Final", "pct"),
    "Employment Cost Index q/q": ("Employment Cost Index QoQ", "pct"),
    "Durable Goods Orders m/m": ("Durable Goods Orders MoM", "pct"),
    "Core Durable Goods Orders m/m": ("Durable Goods Orders Ex Transp MoM", "pct"),
    "Existing Home Sales": ("Existing Home Sales", "lvl"),
    "New Home Sales": ("New Home Sales", "lvl"),
    "Pending Home Sales m/m": ("Pending Home Sales MoM", "pct"),
    "Federal Funds Rate": ("Interest Rate", "pct"),
}
_CACHE = {}


def _events(day, cache_dir=None):
    """day 前后各 3 天的美国经济数据（list）。"""
    key = str(day)
    if key in _CACHE:
        return _CACHE[key]
    path = os.path.join(cache_dir, f"_tvcal_{key}.json") if cache_dir else None
    try:
        if path and time.time() - os.path.getmtime(path) < 20 * 60:
            _CACHE[key] = json.load(open(path, encoding="utf-8"))
            return _CACHE[key]
    except (OSError, ValueError):
        pass
    a, b = day - dt.timedelta(days=3), day + dt.timedelta(days=4)
    req = urllib.request.Request(URL.format(a=a, b=b), headers={"User-Agent": "Mozilla/5.0", "Origin": "https://www.tradingview.com",
                                                                "Referer": "https://www.tradingview.com/"})
    ev = json.load(urllib.request.urlopen(req, timeout=30)).get("result") or []
    _CACHE[key] = ev
    if path:
        os.makedirs(cache_dir, exist_ok=True)
        json.dump(ev, open(path, "w", encoding="utf-8"))
    return ev


def _fmt(x, mode, scale):
    unit = "K" if scale == "K" else "M" if scale == "M" else ""
    if mode == "chg":
        return f"{x:+,.0f}{unit}"
    if mode == "pct":
        return f"{x:.1f}%"
    return f"{x:,.1f}{unit}".replace(".0" + unit, unit) if unit else (f"{x:,.1f}" if x < 1000 else f"{x:,.0f}")


def find(title, when, cache_dir=None):
    """Forex Factory 的一项 → TradingView 同一天的那一项（dict）；找不到返回 None。"""
    if title not in MAP:
        return None
    tv_title, _ = MAP[title]
    et = dt.timezone(dt.timedelta(hours=-5))
    w = when if isinstance(when, dt.datetime) else dt.datetime.combine(when, dt.time(12), et)
    day = w.astimezone(et).date()
    try:
        ev = _events(day, cache_dir)
    except Exception:
        return None
    for e in ev:
        if e.get("title") != tv_title:
            continue
        t = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        if t.astimezone(et).date() == day:
            return e
    return None


def actual(title, when, cache_dir=None):
    """和 bls.actual() 一样的格式：dict(actual='200K', prev='191K', value=200.0, period=…, source='TradingView')；还没公布返回 None。"""
    e = find(title, when, cache_dir)
    if not e or e.get("actual") is None:
        return None
    mode, sc = MAP[title][1], e.get("scale")
    a, p = float(e["actual"]), e.get("previous")
    return dict(actual=_fmt(a, mode, sc), prev=_fmt(float(p), mode, sc) if p is not None else "—", value=round(a, 2),
                period=e.get("period") or "", source="TradingView", tv_forecast=e.get("forecast"))
