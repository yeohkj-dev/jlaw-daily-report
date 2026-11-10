"""盘前提醒：开市前约 30 分钟（美东 09:00 左右）发到 Telegram。规则整理，不用 AI。

内容：期货走向（标普 / 纳指 / 罗素期货、美债、原油、美元）、昨晚选股名单的盘前表现
（J Law 就绪、Luk Leaders）、Luk 的 Premarket 跳空股（实时）、今天的经济数据和业绩、大盘状态。
GitHub 的排程可能会晚，所以每 20 分钟检查一次，只有美东 08:50–09:29 之间才发，同一天只发一次。
用法：python premarket_brief.py [输出目录] [--force]
输出：<输出目录>/早报/盘前_YYYY-MM-DD.json（telegram_html）
仅供学习，不构成投资建议。
"""
import csv
import datetime as dt
import glob
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import tv_scan, yahoo_chart
import news_digest as nd

argv = sys.argv[1:]
FORCE = "--force" in argv
args = [a for a in argv if not a.startswith("--")]
OUT_DIR = args[0] if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://yeohkj-dev.github.io/jlaw-daily-report/"
RISK = "https://yeohkj-dev.github.io/risk-calculator/"
WEEKDAY = "一二三四五六日"
FUTURES = [("ES=F", "标普期货"), ("NQ=F", "纳指期货"), ("RTY=F", "罗素期货")]
MACRO = [("^TNX", "10 年美债"), ("CL=F", "原油"), ("DX-Y.NYB", "美元"), ("GC=F", "黄金"), ("BTC-USD", "比特币")]
CHECKS = []                 # 交叉核对结果，存进盘前 JSON
LIGHT = {"🟢": ("绿灯", "0.5%", "green"), "🟡": ("黄灯", "0.35%", "yellow"), "🔴": ("红灯", "0.25%", "red")}
e = lambda s: html.escape(str(s), quote=False)


def quote(sym):
    try:
        _, m = yahoo_chart(sym, "1d", "5m")
        p, prev = m.get("regularMarketPrice"), m.get("chartPreviousClose")
        return dict(price=p, prev=prev, chg=(p / prev - 1) * 100 if p and prev else None)
    except Exception:
        return None


def premarket(syms):
    """TradingView 盘前涨跌（代码 → %），代码可带交易所前缀。"""
    if not syms:
        return {}
    rows = tv_scan({"symbols": {"tickers": syms}, "columns": ["name", "premarket_change", "premarket_close", "close"]})
    return {r["d"][0]: dict(pm=r["d"][1], pm_px=r["d"][2], close=r["d"][3], ex=r["s"].split(":")[0]) for r in rows}


def link(sym, ex=None):
    """股票代码 → TradingView 日线图链接。"""
    url = "https://www.tradingview.com/chart/?symbol=" + (f"{ex}:{sym}" if ex else sym)
    return '<a href="' + html.escape(url) + '"><b>' + html.escape(sym) + '</b></a>'



def latest(pattern):
    f = sorted(glob.glob(os.path.join(OUT_DIR, pattern)))
    return f[-1] if f else None


def jlaw_ready():
    f = latest("每日选股/20??-??-??.csv")
    if not f:
        return [], None
    rows = [r for r in csv.DictReader(open(f, encoding="utf-8-sig")) if r.get("就绪") in ("META", "VCP")]
    return rows, os.path.basename(f)[:10]


def luk_leaders(n=10):
    f = latest("Luk选股/20??-??-??.json")
    if not f:
        return [], None
    d = json.load(open(f, encoding="utf-8"))
    return d.get("lists", {}).get("leader", [])[:n], os.path.basename(f)[:10]


def luk_gappers(n=8):
    """Luk 的 Premarket 选股器（他本人公布的条件），按盘前涨幅排序。"""
    cols = ["name", "premarket_change", "industry"]
    body = {"filter": [{"left": "type", "operation": "equal", "right": "stock"},
                       {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
                       {"left": "market_cap_basic", "operation": "greater", "right": 1e8},
                       {"left": "average_volume_10d_calc", "operation": "greater", "right": 5e5},
                       {"left": "Value.Traded", "operation": "greater", "right": 5e7},
                       {"left": "premarket_change", "operation": "egreater", "right": 3}],
            "columns": cols, "sort": {"sortBy": "premarket_change", "sortOrder": "desc"}, "range": [0, n]}
    return [dict(zip(cols, r["d"]), ex=r["s"].split(":")[0]) for r in tv_scan(body)]


def today_events(today):
    ev = []
    for p in sorted(glob.glob(os.path.join(OUT_DIR, "新闻", "week_*.json")))[-2:]:
        ev += json.load(open(p, encoding="utf-8"))
    return [x for x in ev if x["when"][:10] == str(today) and x["impact"] == "High"]


def today_earnings(today):
    f = latest("业绩估值/20??-??-??.json")
    if not f:
        return []
    data = json.load(open(f, encoding="utf-8"))
    return [(r["sym"], r.get("exchange") or "") for rs in data.values() for r in rs if r.get("next_er") == str(today)]


def market_state():
    p = os.path.join(OUT_DIR, "大盘报告", "大盘历史.csv")
    last = open(p, encoding="utf-8-sig").read().strip().splitlines()[-1].split(",")
    return last[0], last[1]


def pmtxt(x):
    if x is None:
        return "盘前无成交"
    return f"{'🟢' if x > 0 else '🔴' if x < 0 else '⚪'} {x:+.1f}%"


def build(et):
    today = et.date()
    fut = {s: quote(s) for s, _ in FUTURES}
    mac = {s: quote(s) for s, _ in MACRO}
    es, nq = fut.get("ES=F") or {}, fut.get("NQ=F") or {}
    lead = es.get("chg") or 0
    if nq.get("chg") is not None and abs(nq["chg"]) > abs(lead):
        lead = nq["chg"]
    tone = ("📈 期货偏强，预计高开" if lead >= 0.5 else "📉 期货偏弱，预计低开" if lead <= -0.5 else "➖ 期货平稳，预计平开")
    L = [f"<b>⏰ 盘前提醒 · {today:%m-%d}（周{WEEKDAY[today.weekday()]}）美东 {et:%H:%M}</b>", "", f"<b>{tone}</b>"]
    L.append(" · ".join(f"{n} {fut[s]['chg']:+.2f}%" for s, n in FUTURES if fut.get(s) and fut[s]["chg"] is not None))
    # 交叉核对：Yahoo 的期货价格和 TradingView 比（两边差 >0.3% 就在信息里提醒，不硬算方向）
    try:
        import urllib.request
        tvf = {"ES=F": "CME_MINI:ES1!", "NQ=F": "CME_MINI:NQ1!", "RTY=F": "CME_MINI:RTY1!"}
        req = urllib.request.Request("https://scanner.tradingview.com/global/scan", data=json.dumps(
            {"symbols": {"tickers": list(tvf.values())}, "columns": ["name", "close"]}).encode(), headers={"User-Agent": "Mozilla/5.0"})
        tvp = {r["s"]: r["d"][1] for r in json.load(urllib.request.urlopen(req, timeout=30))["data"]}
        diff = [n for s, n in FUTURES if fut.get(s) and tvp.get(tvf[s]) and abs(fut[s]["price"] / tvp[tvf[s]] - 1) * 100 > 0.3]
        if diff:
            L.append(f"⚠ {'、'.join(diff)}：Yahoo 和 TradingView 的价格相差超过 0.3%，请以 TradingView 为准")
        CHECKS.append(dict(name="期货价格（Yahoo vs TradingView）", ok=not diff, detail=f"{len(tvp)}/{len(tvf)} 个对得上" if not diff else "不一致：" + "、".join(diff)))
    except Exception as ex:
        CHECKS.append(dict(name="期货价格（Yahoo vs TradingView）", ok=None, detail=f"TradingView 取不到（{type(ex).__name__}）"))
    parts = []
    for s, n in MACRO:
        q = mac.get(s)
        if not q or q["chg"] is None:
            continue
        parts.append(f"{n} {q['price']:.2f}%（{(q['price'] - q['prev']) * 100:+.0f} 基点）" if s == "^TNX" else f"{n} {q['chg']:+.1f}%")
    L.append(" · ".join(parts))

    rows, sdate = jlaw_ready()
    leaders, ldate = luk_leaders()
    pm = premarket([r["代码"] for r in rows] + leaders) if rows or leaders else {}
    # 没带交易所前缀时 TradingView 可能取不到，补一次
    missing = [s for s in [r["代码"] for r in rows] + leaders if s not in pm]
    if missing:
        try:
            pm.update(premarket([f"{x}:{s}" for s in missing for x in ("NASDAQ", "NYSE", "AMEX")]))
        except Exception:
            pass

    L += ["", f"<b>🎯 J Law 就绪名单（{sdate or '—'} 收盘选出）</b>"]
    if rows:
        for r in rows[:10]:
            s, kind = r["代码"], r["就绪"]
            q = pm.get(s, {})
            if kind == "VCP":
                pv = float(r["VCP突破点"] or 0)
                px = q.get("pm_px") or q.get("close")
                tag = (" ⚠ 盘前已高于突破点 5%，不追" if px and pv and px > pv * 1.05 else " 盘前已过突破点" if px and pv and px >= pv else "")
                L.append(f"• {link(s, q.get('ex'))} VCP 突破点 {pv:.2f}，止损 {r['VCP止损']} · {pmtxt(q.get('pm'))}{tag}")
            else:
                L.append(f"• {link(s, q.get('ex'))} META 回调，止损 {r['META止损']}（{r['META止损%']}%） · {pmtxt(q.get('pm'))}")
    else:
        L.append("• 没有就绪的股票")

    # 等 2 小时买点（多时间框架：日线信号后 5 天内，盘中会再发「盘中买点提醒」）
    try:
        pend = json.load(open(os.path.join(OUT_DIR, "每日选股", "pending.json"), encoding="utf-8"))
    except (OSError, ValueError):
        pend = []
    if pend:
        pp = premarket([f"{p['ex']}:{p['sym']}" if p["ex"] else p["sym"] for p in pend])
        L += ["", "<b>⏳ 今天等 2 小时买点（盘中触发会另外提醒）</b>"]
        for p in pend:
            rule = ("第一根 2 小时K线（09:30–11:30）高点被收盘突破" if p["kind"] == "BRK" else "2 小时收盘重新站上 2 小时 20 EMA")
            name = "放量突破" if p["kind"] == "BRK" else "A0"
            L.append(f"• {link(p['sym'], p['ex'])} {name}（信号 {p['sig'][5:]}）：{rule} · {pmtxt(pp.get(p['sym'], {}).get('pm'))}")

    L += ["", f"<b>🏆 Luk Leaders 前 10（{ldate or '—'}）</b>"]
    L.append(" · ".join(f"{link(s, pm.get(s, {}).get('ex'))} {pm[s]['pm']:+.1f}%" if pm.get(s, {}).get("pm") is not None
                        else f"{link(s, pm.get(s, {}).get('ex'))} —"
                        for s in leaders) or "没有数据")

    try:
        gaps = luk_gappers()
    except Exception:
        gaps = []
    L += ["", "<b>🚀 Luk 盘前跳空股（实时，盘前涨 ≥3%）</b>"]
    L.append(" · ".join(f"{link(g['name'], g['ex'])} {g['premarket_change']:+.1f}%" for g in gaps) or "目前没有")

    evs, ers = today_events(today), today_earnings(today)
    L += ["", "<b>📅 今天</b>"]
    for x in evs:
        t = nd.to_et(dt.datetime.fromisoformat(x["when"]))
        done = "已公布" if t <= et else "待公布"
        L.append(f"• {t:%H:%M} {e(nd.CAL_ZH.get(x['title'], x['title']))}（预期 {e(x.get('forecast') or '—')}）{done}")
    if ers:
        pe = premarket([f"{ex}:{s}" if ex else s for s, ex in ers])
        L.append("• 业绩：" + "、".join(f"{link(s, ex)} {pe[s]['pm']:+.1f}%" if pe.get(s, {}).get("pm") is not None else link(s, ex)
                                        for s, ex in ers[:10]))
    if not evs and not ers:
        L.append("• 没有高影响力数据或大公司业绩")

    mdate, st = market_state()
    li = LIGHT.get(st[:1])
    L += ["", f"<b>🚦 大盘：{e(st)}</b>（{mdate}）" + (f" → {li[0]}，每笔风险 {li[1]}" if li else ""),
          f"<a href=\"{SITE}\">每日报告</a> · <a href=\"{RISK}?light={li[2] if li else ''}\">仓位计算</a>",
          "<i>仅供学习，不构成投资建议</i>"]
    return "\n".join(L), today


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    now = dt.datetime.now(dt.timezone.utc)
    et = nd.to_et(now)
    in_window = et.weekday() < 5 and (8, 50) <= (et.hour, et.minute) <= (9, 29)
    if not (in_window or FORCE):
        print(f"美东现在 {et:%a %H:%M}，不在 08:50–09:29 的发送时间，跳过")
        return
    text, today = build(et)
    os.makedirs(os.path.join(OUT_DIR, "早报"), exist_ok=True)
    with open(os.path.join(OUT_DIR, "早报", f"盘前_{today}.json"), "w", encoding="utf-8") as f:
        json.dump(dict(date=str(today), telegram_html=text, checks=CHECKS), f, ensure_ascii=False, indent=1)
    print(text)


if __name__ == "__main__":
    main()
