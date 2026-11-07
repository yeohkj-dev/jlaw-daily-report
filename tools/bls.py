"""美国劳工统计局（BLS）官方数据：非农、失业率、平均时薪、CPI、PPI 的实际值。

Forex Factory 的免费日历只有预期和前值，没有实际值；这里用 BLS 免费公开 API（v1，不用注册）补上。
一次请求取全部数列，结果缓存 6 小时（新闻/_bls_cache.json，不进仓库），避免超过每天 25 次的限制。
只在 BLS 最新一期正好是这次公布的那个月时才给实际值（公布当天 BLS 已更新）。
"""
import datetime as dt
import json
import os
import time
import urllib.request

# Forex Factory 标题 → (BLS 数列, 计算方式)
SERIES = {
    "Non-Farm Employment Change": ("CES0000000001", "diffK"),
    "Unemployment Rate": ("LNS14000000", "level"),
    "Average Hourly Earnings m/m": ("CES0500000003", "mom"),
    "CPI m/m": ("CUSR0000SA0", "mom"),
    "Core CPI m/m": ("CUSR0000SA0L1E", "mom"),
    "CPI y/y": ("CUUR0000SA0", "yoy"),
    "Core CPI y/y": ("CUUR0000SA0L1E", "yoy"),
    "PPI m/m": ("WPSFD4", "mom"),
    "Core PPI m/m": ("WPSFD49104", "mom"),
}
_DATA = None


def _fetch(cache_dir):
    global _DATA
    if _DATA is not None:
        return _DATA
    path = os.path.join(cache_dir, "_bls_cache.json") if cache_dir else None
    try:
        if path and time.time() - os.path.getmtime(path) < 6 * 3600:
            _DATA = json.load(open(path, encoding="utf-8"))
            return _DATA
    except (OSError, ValueError):
        pass
    ids = sorted({s for s, _ in SERIES.values()})
    req = urllib.request.Request("https://api.bls.gov/publicAPI/v1/timeseries/data/", data=json.dumps({"seriesid": ids}).encode(),
                                 headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=40))
    if d.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(" ".join(d.get("message") or ["BLS 请求失败"]))
    out = {}
    for s in d["Results"]["series"]:
        rows = [x for x in s["data"] if x["period"].startswith("M") and x["period"] != "M13"
                and x["value"].replace(".", "", 1).replace("-", "", 1).isdigit()]          # 有的月份是「-」（没有数据）
        out[s["seriesID"]] = [(int(x["year"]), int(x["period"][1:]), float(x["value"])) for x in rows]
    _DATA = out
    if path:
        os.makedirs(cache_dir, exist_ok=True)
        json.dump(out, open(path, "w", encoding="utf-8"))
    return out


def _num(s):
    """Forex Factory 的数字：'65K' → 65、'0.3%' → 0.3、'-12K' → -12。"""
    try:
        return float(str(s).replace("K", "").replace("%", "").replace("M", "").strip())
    except ValueError:
        return None


def actual(title, when, cache_dir=None):
    """返回 dict(actual='+165K', prev='+60K', vs='高于预期'…)；没有对应数列或 BLS 还没更新时返回 None。"""
    if title not in SERIES:
        return None
    sid, mode = SERIES[title]
    try:
        rows = _fetch(cache_dir).get(sid) or []
    except Exception:
        return None
    if len(rows) < 3:
        return None
    rel = when.date() if isinstance(when, dt.datetime) else when
    want = (rel.year, rel.month - 1) if rel.month > 1 else (rel.year - 1, 12)     # 公布的是上个月的数据
    (y0, m0, v0), (_, _, v1), (_, _, v2) = rows[0], rows[1], rows[2]
    if (y0, m0) != want:
        return None
    if mode == "diffK":
        a, p, unit = v0 - v1, v1 - v2, "K"
        fmt = lambda x: f"{x:+.0f}K"
    elif mode == "level":
        a, p = v0, v1
        fmt = lambda x: f"{x:.1f}%"
    elif mode == "mom":
        a, p = (v0 / v1 - 1) * 100, (v1 / v2 - 1) * 100
        fmt = lambda x: f"{x:.1f}%"
    else:                                                     # yoy：同月去年
        yr = {(y, m): v for y, m, v in rows}
        last = yr.get((y0 - 1, m0))
        prev_m = (rows[1][0], rows[1][1])
        last_p = yr.get((prev_m[0] - 1, prev_m[1]))
        if not last or not last_p:
            return None
        a, p = (v0 / last - 1) * 100, (v1 / last_p - 1) * 100
        fmt = lambda x: f"{x:.1f}%"
    return dict(actual=fmt(a), prev=fmt(p), value=round(a, 1), month=f"{y0}-{m0:02d}")


def versus(act, forecast):
    """和预期比较：高于 / 低于 / 符合预期。"""
    f = _num(forecast)
    if act is None or f is None:
        return ""
    tol = 5 if abs(f) >= 10 else 0.05
    d = act["value"] - f
    return "符合预期" if abs(d) <= tol else ("高于预期" if d > 0 else "低于预期")
