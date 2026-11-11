"""财报前的期权：市场预期涨跌多少、期权大单堆在哪些价位。

对象：未来 14 天公布业绩的大公司（业绩估值的 110 家）+ 每日选股「等 2 小时买点」名单里 14 天内有财报的。
数据：Yahoo 期权链（免费），用财报日之后最近的一个到期日：
  预期波动 = 平值跨式（最接近现价的看涨 + 看跌，用买卖价中间价；没有买卖价就用最后成交价）÷ 现价
  再用平值隐含波动率算一次（现价 × IV × √(到期天数/365)）核对，两个差太多会标 ⚠
  看涨未平仓最多的价位（常被当成上方压力）、看跌未平仓最多的价位（下方支撑）、最大痛点（期权买方合计最亏的到期价）、看跌 / 看涨未平仓比
  财报日：Yahoo 和业绩估值的日期要一致，不一致会标 ⚠
用法：python earnings_options.py [输出目录] → 业绩估值/财报期权_YYYY-MM-DD.html / .json
仅供学习，不构成投资建议。
"""
import datetime as dt
import glob
import html
import json
import math
import os
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fetch_json, yahoo_crumb

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAYS = 14


def chain(sym, date=None):
    url = f"https://query2.finance.yahoo.com/v7/finance/options/{urllib.parse.quote(sym.replace('.', '-'))}?crumb={urllib.parse.quote(yahoo_crumb())}"
    if date:
        url += f"&date={date}"
    return fetch_json(url)["optionChain"]["result"][0]


def mid(o):
    b, a = o.get("bid") or 0, o.get("ask") or 0
    return (b + a) / 2 if b > 0 and a > 0 else (o.get("lastPrice") or 0)


def analyse(item):
    sym, ex, er_date, src = item
    try:
        r = chain(sym)
    except Exception as e:
        return dict(sym=sym, ex=ex, err=type(e).__name__)
    q = r["quote"]
    px = q.get("regularMarketPrice")
    ets = q.get("earningsTimestampStart") or q.get("earningsTimestamp")
    y_er = dt.datetime.fromtimestamp(ets, dt.timezone.utc).date() if ets else None
    er = dt.date.fromisoformat(er_date) if er_date else y_er
    if not px or not er:
        return dict(sym=sym, ex=ex, err="没有价格或财报日")
    exps = [dt.datetime.fromtimestamp(x, dt.timezone.utc).date() for x in r.get("expirationDates", [])]
    after = [d for d in exps if d >= er + dt.timedelta(days=1)]
    if not after:
        return dict(sym=sym, ex=ex, err="没有财报后的到期日")
    exp = after[0]
    ts = int(dt.datetime(exp.year, exp.month, exp.day, tzinfo=dt.timezone.utc).timestamp())
    try:
        o = chain(sym, ts)["options"][0]
    except Exception as e:
        return dict(sym=sym, ex=ex, err=type(e).__name__)
    calls, puts = o.get("calls", []), o.get("puts", [])
    if not calls or not puts:
        return dict(sym=sym, ex=ex, err="期权链是空的")
    strikes = sorted({c["strike"] for c in calls} & {p["strike"] for p in puts})
    atm = min(strikes, key=lambda k: abs(k - px))
    cm = {c["strike"]: c for c in calls}
    pm = {p["strike"]: p for p in puts}
    straddle = mid(cm[atm]) + mid(pm[atm])
    move = straddle / px * 100
    dte = max(1, (exp - dt.date.today()).days)
    iv = ((cm[atm].get("impliedVolatility") or 0) + (pm[atm].get("impliedVolatility") or 0)) / 2
    iv_move = iv * math.sqrt(dte / 365) * 100
    coi = {c["strike"]: c.get("openInterest") or 0 for c in calls}
    poi = {p["strike"]: p.get("openInterest") or 0 for p in puts}
    call_wall = max((k for k in coi if k >= px), key=lambda k: coi[k], default=None)
    put_wall = max((k for k in poi if k <= px), key=lambda k: poi[k], default=None)
    allk = sorted(set(coi) | set(poi))
    pain = min(allk, key=lambda s: sum(oi * max(0, s - k) for k, oi in coi.items()) + sum(oi * max(0, k - s) for k, oi in poi.items()))
    pc = sum(poi.values()) / sum(coi.values()) if sum(coi.values()) else None
    warn = []
    if y_er and er_date and abs((y_er - er).days) > 1:
        warn.append(f"Yahoo 财报日 {y_er:%m-%d} 和业绩估值 {er:%m-%d} 不一样")
    # 核对 1：收盘后 Yahoo 的隐含波动率常是 0，只在有效（> 5%）时才拿来和跨式比
    if iv > 0.05 and move and abs(move / iv_move - 1) > 0.35:
        warn.append(f"跨式 {move:.1f}% 和隐含波动率算的 {iv_move:.1f}% 差很多")
    # 核对 2：没有买卖价时用的是最后成交价，太旧（> 3 天）就提醒
    for leg in (cm[atm], pm[atm]):
        if not ((leg.get("bid") or 0) > 0 and (leg.get("ask") or 0) > 0):
            lt = leg.get("lastTradeDate")
            if lt and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromtimestamp(lt, dt.timezone.utc)).days > 3:
                warn.append(f"平值期权最后成交在 {dt.datetime.fromtimestamp(lt, dt.timezone.utc):%m-%d}，价格可能过时")
                break
    quoted = all((leg.get("bid") or 0) > 0 and (leg.get("ask") or 0) > 0 for leg in (cm[atm], pm[atm]))
    return dict(sym=sym, ex=ex, src=src, px=px, er=str(er), exp=str(exp), dte=dte, move=move, iv_move=iv_move, iv=iv * 100, quoted=quoted,
                lo=px - straddle, hi=px + straddle, call_wall=call_wall, call_oi=coi.get(call_wall), put_wall=put_wall, put_oi=poi.get(put_wall),
                pain=pain, pc=pc, warn=warn)


def targets(today):
    out = {}
    f = sorted(glob.glob(os.path.join(OUT_DIR, "业绩估值", "20??-??-??.json")))
    if f:
        for rs in json.load(open(f[-1], encoding="utf-8")).values():
            for r in rs:
                d = r.get("next_er")
                if d and 0 <= (dt.date.fromisoformat(d) - today).days <= DAYS:
                    out[r["sym"]] = (r["sym"], r.get("exchange") or "", d, "大公司")
    try:
        for p in json.load(open(os.path.join(OUT_DIR, "每日选股", "pending.json"), encoding="utf-8")):
            out.setdefault(p["sym"], (p["sym"], p.get("ex") or "", None, "等 2 小时买点"))
    except (OSError, ValueError):
        pass
    return list(out.values())


def fragment(rows, today):
    td = 'style="padding:5px 7px;border-bottom:1px solid #eee;white-space:nowrap;"'
    th = 'style="padding:5px 7px;background:#f5f5f5;text-align:left;font-weight:600;border-bottom:1px solid #ddd;white-space:nowrap;"'
    ok = sorted([r for r in rows if "err" not in r and 0 <= (dt.date.fromisoformat(r["er"]) - today).days <= DAYS], key=lambda r: (r["er"], r["sym"]))
    body = ""
    for r in ok:
        url = "https://www.tradingview.com/chart/?symbol=" + (f"{r['ex']}:{r['sym']}" if r["ex"] else r["sym"])
        w = f'<br><span style="color:#B26A00;font-size:11px;">⚠ {html.escape("；".join(r["warn"]))}</span>' if r["warn"] else ""
        body += (f'<tr><td {td}><a href="{html.escape(url)}" target="_blank" rel="noopener" style="color:#1565C0;text-decoration:none;font-weight:700;">{r["sym"]} 📈</a>'
                 f'<br><span style="color:#888;font-size:11px;">{r["src"]}</span></td><td {td}>{r["er"][5:]}</td><td {td}>{r["px"]:,.2f}</td>'
                 f'<td {td}><b>±{r["move"]:.1f}%</b><br><span style="font-size:11px;color:#666;">{r["lo"]:,.2f} – {r["hi"]:,.2f}</span>{w}</td>'
                 f'<td {td}>{r["call_wall"]:,.2f}<br><span style="font-size:11px;color:#666;">{(r["call_oi"] or 0):,} 张</span></td>'
                 f'<td {td}>{r["put_wall"]:,.2f}<br><span style="font-size:11px;color:#666;">{(r["put_oi"] or 0):,} 张</span></td>'
                 f'<td {td}>{r["pain"]:,.2f}</td><td {td}>{r["pc"]:.2f}</td><td {td}>{r["exp"][5:]}' + (f'（IV {r["iv"]:.0f}%）' if r["iv"] > 5 else '') + '</td></tr>'
                 if r["call_wall"] and r["put_wall"] else "")
    tbl = (f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12.5px;"><tr>'
           f'<th {th}>股票</th><th {th}>财报日</th><th {th}>现价</th><th {th}>期权预期波动<br>（财报后到期）</th><th {th}>看涨未平仓最多<br>（上方压力）</th>'
           f'<th {th}>看跌未平仓最多<br>（下方支撑）</th><th {th}>最大痛点</th><th {th}>看跌/看涨<br>未平仓比</th><th {th}>用的到期日<br>（隐含波动率）</th></tr>{body}</table></div>'
           if body else '<p style="color:#888;">未来 14 天没有要公布业绩的公司，或取不到期权数据。</p>')
    return f"""<div style="max-width:1080px;margin:16px auto 0;padding:0 16px;"><div style="background:#fff;border:1px solid #e3e3e3;border-radius:8px;padding:14px 18px;font-size:13.5px;line-height:1.6;">
<h3 style="margin:0 0 6px;color:#1F4E78;">财报前的期权：预期涨跌多少、大单堆在哪里</h3>
<p style="margin:0 0 8px;font-size:12.5px;color:#555;">「预期波动」= 财报后最近到期的平值跨式（同时买看涨和看跌）的价钱 ÷ 现价，是期权市场估计财报后大约会涨或跌多少（不分方向）。
看涨未平仓最多的价位常被当成上方压力，看跌未平仓最多的价位常被当成下方支撑；最大痛点 = 到期时期权买方合计最亏的价位。看跌 / 看涨未平仓比 &gt; 1 代表买保护（看跌）的人较多。</p>
{tbl}
<p style="margin:6px 0 0;font-size:11px;color:#777;">数据来自 Yahoo 期权链（免费，收盘后可能没有买卖价，就用最后成交价），并用隐含波动率另算一次核对；财报日和业绩估值的日期核对。期权价位只是市场的仓位分布，不保证会守住。仅供学习，不构成投资建议。</p></div></div>"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    today = dt.date.today()
    tg = targets(today)
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(analyse, tg))
    good = [r for r in rows if "err" not in r]
    warn = [r for r in good if r["warn"]]
    frag = fragment(rows, today)
    d = os.path.join(OUT_DIR, "业绩估值")
    os.makedirs(d, exist_ok=True)
    base = os.path.join(d, f"财报期权_{today}")
    open(base + ".html", "w", encoding="utf-8").write("<!doctype html><html><head><meta charset='utf-8'></head><body style=\"margin:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;\">" + frag + "</body></html>")
    json.dump(rows, open(base + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    checks = [dict(name="财报期权（Yahoo）", ok=len(good) == len(tg), critical=False,
                   detail=f"{len(good)}/{len(tg)} 只取到" + (f"；{len(warn)} 只有提醒" if warn else "") + "".join(f"；{r['sym']} {r['err']}" for r in rows if "err" in r)[:200])]
    print(json.dumps({"html": base + ".html", "fragment": frag, "n": len(good), "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
