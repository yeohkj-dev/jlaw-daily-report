"""早报：昨晚美股发生什么、相关新闻（为什么）、谁在带动、今晚要看什么。规则整理，不用 AI。

「为什么」= 把涨跌和同一晚的新闻标题、经济数据配对，是「相关新闻」，不是因果分析；找不到就照实写。
用法：python morning_brief.py [输出目录] [--date YYYY-MM-DD]
输出：<输出目录>/早报/YYYY-MM-DD.json（含 Telegram 文字 telegram_html）
仅供学习，不构成投资建议。
"""
import datetime as dt
import glob
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import card, tv_scan, yahoo_chart
import news_digest as nd
import weekly_events as we
import bls

argv = sys.argv[1:]
DATE = argv[argv.index("--date") + 1] if "--date" in argv else None
args = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i and argv[i - 1] == "--date")]
OUT_DIR = args[0] if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_DIR = os.path.join(OUT_DIR, "新闻")
SITE = "https://yeohkj-dev.github.io/jlaw-daily-report/"
WEEKDAY = "一二三四五六日"
INDEX = [("SPY", "AMEX", "标普"), ("QQQ", "NASDAQ", "纳指"), ("IWM", "AMEX", "小型股")]
# 和 TradingView 一致（期货用结算价算涨跌），用户在 TradingView 看到的是同一个数字
MACRO = [("TVC:US10Y", "10 年美债"), ("TVC:VIX", "VIX"), ("NYMEX:CL1!", "油（结算价）"), ("TVC:DXY", "美元"), ("COMEX:GC1!", "金（结算价）")]
TV_CHART = "https://www.tradingview.com/chart/?symbol="
MY_TZ = dt.timezone(dt.timedelta(hours=8))
nd.CAL_ZH.setdefault("Prelim UoM Inflation Expectations", "密歇根通胀预期初值")
nd.CAL_ZH.setdefault("Revised UoM Inflation Expectations", "密歇根通胀预期终值")
SECTORS = [("XLK", "科技"), ("XLY", "可选消费"), ("XLC", "通讯"), ("XLF", "金融"), ("XLI", "工业"), ("XLB", "原材料"),
           ("XLE", "能源"), ("XLV", "医疗"), ("XLP", "必需消费"), ("XLU", "公用事业"), ("XLRE", "房地产")]
# 公司名（去掉 Inc. 等）用来在新闻标题里找这家公司
SUFFIX = re.compile(r",?\s+(Inc\.?|Corporation|Corp\.?|Company|Co\.?|Ltd\.?|plc|Holdings?|Group|Incorporated|Class [A-C]|N\.V\.|S\.A\.)\b.*$", re.I)


def daily_moves(syms):
    out = {}
    for sym, name in syms:
        try:
            bars, meta = yahoo_chart(sym, "1mo", "1d")
            c = [b["c"] for b in bars]
            d = dt.datetime.fromtimestamp(bars[-1]["t"], dt.timezone.utc).date()
            last, prev = c[-1], c[-2]
            # 收盘后一段时间内，Yahoo 的日线可能还没有当天这一根，但「最新价」已经是当天收盘
            mt = meta.get("regularMarketTime")
            if mt and meta.get("regularMarketPrice"):
                md = dt.datetime.fromtimestamp(mt, dt.timezone.utc).date()
                if md > d:
                    last, prev, d = meta["regularMarketPrice"], c[-1], md
            out[sym] = dict(name=name, close=last, chg=(last / prev - 1) * 100, diff=last - prev, date=d)
        except Exception:
            pass
    return out


def prev_session(day):
    return day - dt.timedelta(days=3 if day.weekday() == 0 else 1)


def news_of(day, wide=False):
    """大市新闻只用这一个交易日的：上一个交易日收盘（美东 16:00）之后发布的。
    以前连前一天的也读，结果大涨日也会出现前一天「大跌」的标题。
    wide=True（找个股新闻用）：多读前一个交易日的新闻，因为公司常在前一天收盘后公布业绩。"""
    p = prev_session(day)
    days = (day, p) if wide else (day,)
    start = (None if wide else
             dt.datetime(p.year, p.month, p.day, 16, 0, tzinfo=nd.et_offset(dt.datetime(p.year, p.month, p.day, 21, tzinfo=dt.timezone.utc))))
    out, seen = [], set()
    for d in days:
        f = os.path.join(NEWS_DIR, f"{d}_daily.json")
        if not os.path.exists(f):
            continue
        for s in json.load(open(f, encoding="utf-8")).get("stories", []):
            t = dt.datetime.fromisoformat(s["latest"]) if s.get("latest") else None
            if t and (start is None or t >= start) and s["title"] not in seen:
                seen.add(s["title"])
                out.append(dict(s, latest_dt=t))
    return out


def tv_quotes(tickers, market="america"):
    """TradingView 收盘价和当日涨跌（代码 → dict）。"""
    import urllib.request
    body = {"symbols": {"tickers": tickers}, "columns": ["name", "close", "change"]}
    if market == "america":
        rows = tv_scan(body)
    else:
        req = urllib.request.Request(f"https://scanner.tradingview.com/{market}/scan", data=json.dumps(body).encode(),
                                     headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"})
        rows = json.load(urllib.request.urlopen(req, timeout=40))["data"]
    return {r["s"]: dict(close=r["d"][1], chg=r["d"][2]) for r in rows if r["d"][1] is not None and r["d"][2] is not None}


def tv_link(sym, ex, text=None):
    """股票代码 → TradingView 日线图链接。"""
    url = TV_CHART + (f"{ex}:{sym}" if ex else sym)
    return '<a href="' + html.escape(url) + '"><b>' + html.escape(text or sym) + '</b></a>'



def company_news(sym, desc, stories):
    name = SUFFIX.sub("", desc or "").strip()
    keys = [re.escape(sym)] + ([re.escape(name)] if len(name) >= 3 else [])
    rx = re.compile(r"\b(" + "|".join(keys) + r")\b", re.I if len(name) >= 3 else 0)
    hits = [s for s in stories if rx.search(s["title"])]
    return max(hits, key=lambda s: (s.get("n_sources", 1), s.get("score", 0))) if hits else None


def movers(stories, n=5):
    cols = ["name", "description", "change", "market_cap_basic", "exchange"]
    body = {"filter": [{"left": "type", "operation": "equal", "right": "stock"},
                       {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ"]},
                       {"left": "market_cap_basic", "operation": "egreater", "right": 5e10}],
            "columns": cols, "range": [0, n]}
    out = {}
    for k, order in (("up", "desc"), ("down", "asc")):
        rows = [dict(zip(cols, r["d"])) for r in tv_scan(dict(body, sort={"sortBy": "change", "sortOrder": order}))]
        for r in rows:
            r["news"] = company_news(r["name"], r["description"], stories)
        out[k] = rows
    return out


MARKET_RX = re.compile(r"\b(stocks?|nasdaq|s&p|dow|wall street|sell-?off|rout|tumbl\w*|plung\w*|slid\w*|slump\w*|sink\w*|"
                       r"rall\w*|surg\w*|soar\w*|volatility|vix|futures|market)\b", re.I)
# 政策 / 地缘新闻只在和市场有关时才算（关税、利率、油价、战争…），一般政治新闻不算
POLICY_RX = re.compile(r"\b(tariffs?|trade|tax|sanctions?|shutdown|budget|debt|fed|treasury|yields?|oil|opec|china|war|iran|israel|"
                       r"russia|ukraine|taiwan|chips?|export)\b", re.I)
# 纯政治新闻（调查、选举、议员…）不算，除非标题同时讲到市场或政策（关税、利率、油价、战争…）
POLITICS_RX = re.compile(r"\b(democrats?|republicans?|gop|investigations?|lawmakers?|elections?|senate|impeach\w*|probes?|"
                         r"indict\w*|lawsuits?|scandal|campaign)\b", re.I)


EARN_RX = re.compile(r"\b(dividend|earnings|estimates|beats?|misses|revenue|guidance|quarter|profit)\b", re.I)   # 个股消息


def macro_news(stories):
    """当晚最受关注的大市新闻：讲大盘涨跌的标题优先，其次媒体数；个股财报只在标题讲到大盘时才算。"""
    macro = ("美联储 / 利率", "通胀", "就业", "经济数据", "市场动态")
    def ok(s):
        t = s["title"]
        if MARKET_RX.search(t):
            return True
        if POLITICS_RX.search(t) and not POLICY_RX.search(t):
            return False
        if EARN_RX.search(t):
            return False
        return s.get("topic") in macro or (s.get("topic") in ("政策 / 关税", "地缘政治") and POLICY_RX.search(t))
    m = [s for s in stories if ok(s)]
    # 讲大盘涨跌的标题最优先，其次媒体数
    return sorted(m, key=lambda s: (-(10 * bool(MARKET_RX.search(s["title"])) + s.get("n_sources", 1)), -s.get("score", 0)))[:4]


def econ(day):
    path = sorted(glob.glob(os.path.join(NEWS_DIR, "week_*.json")))
    ev = []
    for p in path[-2:]:
        ev += json.load(open(p, encoding="utf-8"))
    def on(d):
        return [e for e in ev if e["when"][:10] == str(d)]
    return on(day), on(day + dt.timedelta(days=1) if day.weekday() < 4 else day + dt.timedelta(days=3))


def earnings(next_day):
    files = sorted(glob.glob(os.path.join(OUT_DIR, "业绩估值", "20??-??-??.json")))
    if not files:
        return []
    data = json.load(open(files[-1], encoding="utf-8"))
    return [(r["sym"], r.get("exchange") or "") for rs in data.values() for r in rs if r.get("next_er") == str(next_day)]


def state():
    p = os.path.join(OUT_DIR, "大盘报告", "大盘历史.csv")
    rows = open(p, encoding="utf-8-sig").read().strip().splitlines()
    last = rows[-1].split(",")
    return last[0], last[1]


def build(day):
    idx = tv_quotes([f"{ex}:{s}" for s, ex, _ in INDEX])
    mac = tv_quotes([t for t, _ in MACRO], "global")
    sec = tv_quotes([f"AMEX:{s}" for s, _ in SECTORS])
    yh = daily_moves([(s, n) for s, _, n in INDEX])          # 只用来核对 TradingView 的数字
    stories = news_of(day)
    mv = movers(news_of(day, wide=True))
    past, ahead = econ(day)
    nxt = day + dt.timedelta(days=1 if day.weekday() < 4 else 3)
    ers = earnings(nxt)
    sdate, st = state()
    e = lambda x: html.escape(str(x), quote=False)

    def p(x):
        return f"{x:+.1f}%"
    q = {s: idx.get(f"{ex}:{s}") for s, ex, _ in INDEX}
    spy, qqq = q.get("SPY"), q.get("QQQ")
    big = max(abs(spy["chg"]), abs(qqq["chg"])) if spy and qqq else 0
    mood = ("大跌" if big >= 2 and qqq["chg"] < 0 else "大涨" if big >= 2 else "下跌" if spy and spy["chg"] < -0.3 else
            "上涨" if spy and spy["chg"] > 0.3 else "持平")
    lines = [f"<b>☀️ 早报 · 美股 {day:%m-%d}（周{WEEKDAY[day.weekday()]}）收盘</b>", ""]
    lines.append(f"<b>📉 昨晚：美股{mood}</b>" if "跌" in mood else f"<b>📈 昨晚：美股{mood}</b>")
    lines.append(" · ".join(f"{tv_link(s, ex, n)} {p(q[s]['chg'])}" for s, ex, n in INDEX if q.get(s)))
    parts = []
    for t, n in MACRO:
        x = mac.get(t)
        if not x:
            continue
        if t == "TVC:US10Y":
            prev = x["close"] / (1 + x["chg"] / 100)
            parts.append(f"{n} {x['close']:.2f}%（{(x['close'] - prev) * 100:+.0f} 基点）")
        elif t == "TVC:VIX":
            prev = x["close"] / (1 + x["chg"] / 100)
            parts.append(f"{n} {x['close']:.1f}（{x['close'] - prev:+.1f}）")
        else:
            parts.append(f"{n} {p(x['chg'])}")
    lines.append(" · ".join(parts))

    lines += ["", "<b>❓ 为什么（相关新闻，不是因果分析）</b>"]
    mn = macro_news(stories)
    for s in mn:
        lines.append(f"• <a href=\"{html.escape(s['link'])}\">{e(s['title'])}</a>" + (f"（{s['n_sources']} 家媒体）" if s.get("n_sources", 1) >= 2 else ""))
    # 当天公布的经济数据：附公布之后的相关新闻标题（Forex Factory 免费数据没有实际值）
    st_dt = [dict(s, latest=s["latest_dt"], sources=s.get("sources", [])) for s in stories]
    # 同一则新闻对应几项数据（例如非农、失业率、平均时薪），合成一行
    groups, actuals = [], []
    for ev in past:
        zh = nd.CAL_ZH.get(ev["title"], ev["title"])
        # 实际值来自美国劳工统计局（BLS）官方数据；Forex Factory 只有预期和前值
        a = bls.actual(ev["title"], dt.datetime.fromisoformat(ev["when"]), NEWS_DIR)
        if a:
            vs = bls.versus(a, ev.get("forecast"))
            item = (f"{e(zh)} 实际 <b>{a['actual']}</b>（预期 {e(ev.get('forecast') or '—')}" + (f"，{vs}" if vs else "")
                    + (f"；上月修正为 {a['prev']}（原 {e(ev.get('previous'))}）"
                       if bls._num(ev.get("previous")) is not None and abs(bls._num(a["prev"]) - bls._num(ev.get("previous"))) > 0.05
                       else f"；上月 {a['prev']}") + "）")
            actuals.append(a)
        else:
            item = f"{e(zh)}（预期 {e(ev.get('forecast') or '—')}，前值 {e(ev.get('previous') or '—')}）"
        hit = None
        if ev["impact"] == "High":
            hits = we.match_news(dict(ev, when=dt.datetime.fromisoformat(ev["when"])), st_dt)
            hit = hits[0] if hits else False
        g = next((g for g in groups if hit and g["hit"] and g["hit"]["link"] == hit["link"]), None)
        if g:
            g["items"].append(item)
        else:
            groups.append(dict(hit=hit, items=[item]))
    for g in groups:
        tail = (f" → <a href=\"{html.escape(g['hit']['link'])}\">{e(g['hit']['title'])}</a>" if g["hit"] else
                " → 新闻里还没找到结果" if g["hit"] is False else "")
        lines.append("• 数据：" + "、".join(g["items"]) + tail)
    if not mn and not past:
        lines.append("• 没有找到明显的相关新闻或数据")

    lines += ["", "<b>🏭 行业</b>"]
    ss = sorted(((s, n, sec[f"AMEX:{s}"]["chg"]) for s, n in SECTORS if sec.get(f"AMEX:{s}")), key=lambda x: -x[2])
    if ss:
        top_lab = "领涨" if ss[0][2] > 0 else "最抗跌"
        bot_lab = "领跌" if ss[-1][2] < 0 else "涨最少"
        f = lambda x: f"{tv_link(x[0], 'AMEX', x[1])} {p(x[2])}"
        lines.append(f"{top_lab}：" + "、".join(f(x) for x in ss[:2]) + f"　{bot_lab}：" + "、".join(f(x) for x in ss[-2:][::-1]))
    lines += ["", "<b>🔥 大公司异动（市值 ≥500 亿）</b>"]
    for k in ("up", "down"):
        for r in mv[k][:3]:
            why = f" — <a href=\"{html.escape(r['news']['link'])}\">{e(r['news']['title'][:70])}</a>" if r["news"] else " — 没有找到相关新闻"
            lines.append(f"{'🟢' if k == 'up' else '🔴'} {tv_link(r['name'], r.get('exchange'))} {p(r['change'])}{why}")

    lines += ["", f"<b>👀 {'下个交易日（周一 ' + f'{nxt:%m-%d}' + '）' if day.weekday() == 4 else '今晚'}要看</b>"]
    for ev in ahead:
        if ev["impact"] == "High":
            zh = nd.CAL_ZH.get(ev["title"], ev["title"])
            t = dt.datetime.fromisoformat(ev["when"])
            lines.append(f"• {nd.to_et(t):%H:%M} 美东（马来西亚 {t.astimezone(MY_TZ):%H:%M}）{e(zh)}（预期 {e(ev.get('forecast') or '—')}，前值 {e(ev.get('previous') or '—')}）")
    if ers:
        lines.append("• 业绩：" + "、".join(tv_link(s, ex) for s, ex in ers[:10]))
    if not any(ev["impact"] == "High" for ev in ahead) and not ers:
        lines.append("• 没有高影响力数据或大公司业绩")
    lines += ["", f"<b>🚦 大盘状态：{e(st)}</b>（{sdate}）", f"<a href=\"{SITE}\">打开每日报告 →</a>"]
    return "\n".join(lines), dict(index=q, yahoo=yh, macro_q=mac, sectors=sec, movers=mv, macro=mn, past=past, ahead=ahead,
                                  earnings=ers, n_stories=len(stories), actuals=actuals, tv_all={**idx, **mac, **sec}, stories=stories)


MORE = {"🏭": "大盘报告 → 行业指数追踪", "🔥": "Luk 选股 / 业绩与估值", "👀": "今日新闻 → 本周重大事件", "❓": "今日新闻"}


def web_html(text):
    """把 Telegram 文字排成网页分页：粗体标题行 → 小标题，「•」行 → 列表，其余 → 段落。"""
    lines = text.split("\n")
    title = re.sub(r"</?b>", "", lines[0]).replace("☀️ ", "")
    body, ul = "", []

    def flush():
        nonlocal body, ul
        if ul:
            body += '<ul style="margin:0;padding-left:20px;line-height:1.75;">' + "".join(f"<li>{x}</li>" for x in ul) + "</ul>"
            ul = []
    for ln in lines[1:]:
        if not ln.strip() or "打开每日报告" in ln:
            continue
        if ln.startswith("<b>") and ln.rstrip().endswith(("</b>", "）")) and not ln.startswith(("<b>🟢", "<b>🔴")):
            flush()
            head = ln
            more = next((v for k, v in MORE.items() if k in ln), "")
            body += (f'<h3 style="margin:18px 0 6px;font-size:16px;">{head}'
                     + (f' <span style="font-size:11px;color:#888;font-weight:400;">详情：{more}</span>' if more else "") + "</h3>")
        elif ln.startswith(("• ", "🟢", "🔴")):
            ul.append(ln[2:] if ln.startswith("• ") else ln)
        else:
            flush()
            body += f'<p style="margin:2px 0;line-height:1.7;">{ln}</p>'
    flush()
    body = body.replace("<a href=", '<a target="_blank" rel="noopener" style="color:#1565C0;text-decoration:none;" href=')
    body += ('<p style="color:#888;font-size:11px;margin-top:14px;">规则自动整理，不用 AI。「为什么」是把当晚大盘涨跌和同一晚多家媒体报道的新闻标题配对，'
             '是相关新闻，不是因果分析；找不到就照实写。新闻标题保留英文原文。仅供学习，不构成投资建议。</p>')
    return card(html.escape(title), body, accent="#F9A825", bg="#FFFDE7",
                sub='<div style="font-size:13px;color:#555;">昨晚美股发生什么、为什么、谁在带动、今晚要看什么</div>')


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    day = dt.date.fromisoformat(DATE) if DATE else daily_moves([("SPY", "")])["SPY"]["date"]
    text, data = build(day)
    os.makedirs(os.path.join(OUT_DIR, "早报"), exist_ok=True)
    base = os.path.join(OUT_DIR, "早报", str(day))
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(dict(date=str(day), telegram_html=text), f, ensure_ascii=False, indent=1)
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "</head><body style=\"margin:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222;\">"
                + web_html(text) + "</body></html>")
    spy, qqq = data["index"].get("SPY"), data["index"].get("QQQ")
    # TradingView 和 Yahoo 的当日涨跌要一致（相差 ≤0.15 个百分点），Yahoo 的日期也要是这一天
    diffs = {s: abs(data["index"][s]["chg"] - data["yahoo"][s]["chg"]) for s in data["index"]
             if data["index"].get(s) and data["yahoo"].get(s) and data["yahoo"][s]["date"] == day}
    bad = [s for s, d in diffs.items() if d > 0.15]
    # 逐项交叉核对：每个数字都用第二个来源再算一次
    import brief_check as bc
    rows = (bc.check_quotes(data["tv_all"], day) + bc.check_movers(data["movers"], day)
            + bc.check_bls(data["past"], data["stories"]) + bc.check_earnings(data["earnings"], day))
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(dict(date=str(day), telegram_html=text, crosscheck=rows), f, ensure_ascii=False, indent=1, default=str)
    checks = [bc.summary(rows), dict(name="早报行情（TradingView vs Yahoo）", ok=len(diffs) == 3 and not bad, critical=False,
                   detail=(f"SPY {spy['chg']:+.2f}%；" if spy else "") + (f"{len(diffs) - len(bad)}/{len(diffs)} 一致" if diffs else "Yahoo 取不到这一天")
                   + (f"，不一致：{'、'.join(bad)}" if bad else "")),
              dict(name="经济数据实际值（BLS 官方）", ok=True, critical=False,
                   detail=(f"{len(data['actuals'])} 项取到" if data["actuals"] else "这一天没有 BLS 的数据公布，或 BLS 还没更新")),
              dict(name="早报新闻", ok=bool(data["macro"]), critical=False,
                   detail=f"这一天的新闻 {data['n_stories']} 条，选出 {len(data['macro'])} 条大市新闻")]
    print(json.dumps({"html": base + ".html", "json": base + ".json", "date": str(day),
                      "spy": round(spy["chg"], 1) if spy else None, "qqq": round(qqq["chg"], 1) if qqq else None,
                      "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
