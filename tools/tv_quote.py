"""TradingView 报价（图表页用的公开 websocket，不用登录）+ 债券到期收益率计算。

2026-11-12 起 TradingView 债券选股器（scanner.tradingview.com/bond/scan）不理会筛选、指定代码和 range，
只回传固定的 10 只欧洲债券，所以「信用市场」改用这里：按代码直接要报价（FINRA 美国成交价，延迟约 4 小时；
德国交易所 FWB / GETTEX 当第二来源）。到期收益率自己用价格、票息、到期日算（每半年付息），TradingView 有给就拿来核对。
需要 pip install websocket-client。
"""
import datetime as dt
import json
import random
import re
import string
import time


def _msg(m, p):
    s = json.dumps({"m": m, "p": p}, separators=(",", ":"))
    return f"~m~{len(s)}~m~{s}"


def quotes(syms, fields=("lp", "lp_time", "description", "yield_to_maturity", "update_mode"), wait=20):
    """{代码: {lp, lp_time, description, yield_to_maturity, _s}}；取不到的代码不在结果里或 _s='error'。"""
    import websocket
    ws = websocket.create_connection("wss://data.tradingview.com/socket.io/websocket",
                                     header=["Origin: https://www.tradingview.com"], timeout=15)
    qs = "qs_" + "".join(random.choice(string.ascii_lowercase) for _ in range(12))
    for m, p in (("set_auth_token", ["unauthorized_user_token"]), ("quote_create_session", [qs]),
                 ("quote_set_fields", [qs, *fields]), ("quote_add_symbols", [qs, *syms])):
        ws.send(_msg(m, p))
    out, t0 = {}, time.time()
    try:
        while time.time() - t0 < wait:
            try:
                raw = ws.recv()
            except Exception:
                break
            for part in re.split(r"~m~\d+~m~", raw):
                if part.startswith("~h~"):                      # 心跳要回传，否则会被断线
                    ws.send(f"~m~{len(part)}~m~{part}")
                elif part.startswith("{"):
                    j = json.loads(part)
                    if j.get("m") == "qsd":
                        d = j["p"][1]
                        out.setdefault(d["n"], {}).update(d.get("v", {}))
                        out[d["n"]]["_s"] = d.get("s")
            if len(out) == len(syms) and all("lp" in v or v.get("_s") == "error" for v in out.values()):
                break
    finally:
        ws.close()
    return out


MON = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}


def parse_bond(desc):
    """'Oracle Corporation 5.7% 04-FEB-2036' → (5.7, date(2036, 2, 4))；看不懂返回 None。"""
    m = re.search(r"([\d.]+)%\s+(\d{2})-([A-Z]{3})-(\d{4})", desc or "")
    if not m:
        return None
    return float(m.group(1)), dt.date(int(m.group(4)), MON[m.group(3)], int(m.group(2)))


def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    import calendar
    return dt.date(d.year + y, m + 1, min(d.day, calendar.monthrange(d.year + y, m + 1)[1]))


def ytm(clean, coupon, maturity, settle):
    """到期收益率（%，每半年复利），clean = 不含应计利息的价格（每 100 面值）。30/360 近似应计利息，误差约 0.01 个百分点。"""
    if not clean or clean <= 0 or maturity <= settle:
        return None
    dates = [maturity]
    while dates[-1] > settle:
        dates.append(_add_months(dates[-1], -6))
    prev, flows = dates[-1], sorted(dates[:-1])          # 上一次付息日、之后每次付息日
    nxt = flows[0]
    period = (nxt - prev).days or 182
    accr = coupon / 2 * (settle - prev).days / period
    dirty = clean + accr
    frac = (nxt - settle).days / period                  # 到下一次付息还有几分之几期

    def price(y):
        r = y / 200
        return sum((coupon / 2 + (100 if i == len(flows) - 1 else 0)) / (1 + r) ** (frac + i) for i in range(len(flows)))
    lo, hi = -5.0, 60.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if price(mid) > dirty:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
