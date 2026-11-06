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

argv = sys.argv[1:]
DATE = argv[argv.index("--date") + 1] if "--date" in argv else None
args = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i and argv[i - 1] == "--date")]
OUT_DIR = args[0] if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_DIR = os.path.join(OUT_DIR, "新闻")
SITE = "https://yeohkj-dev.github.io/jlaw-daily-report/"
WEEKDAY = "一二三四五六日"
MARKETS = [("SPY", "标普 500"), ("QQQ", "纳指 100"), ("IWM", "小型股"), ("^TNX", "10 年美债"), ("DX-Y.NYB", "美元"),
           ("CL=F", "原油"), ("GC=F", "黄金"), ("^VIX", "VIX")]
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


def news_of(day):
    """当天（美东）的每日新闻；也读前一天，涵盖盘前的消息。"""
    stories = []
    for d in (day, day - dt.timedelta(days=1)):
        f = os.path.join(NEWS_DIR, f"{d}_daily.json")
        if os.path.exists(f):
            stories += json.load(open(f, encoding="utf-8")).get("stories", [])
    seen, out = set(), []
    for s in stories:
        if s["title"] not in seen:
            seen.add(s["title"])
            out.append(s)
    return out


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


EARN_RX = re.compile(r"\b(dividend|earnings|estimates|beats?|misses|revenue|guidance|quarter|profit)\b", re.I)   # 个股消息


def macro_news(stories):
    """当晚最受关注的大市新闻：讲大盘涨跌的标题优先，其次媒体数；个股财报只在标题讲到大盘时才算。"""
    macro = ("美联储 / 利率", "通胀", "就业", "经济数据", "政策 / 关税", "地缘政治", "市场动态")
    m = [s for s in stories if MARKET_RX.search(s["title"]) or (s.get("topic") in macro and not EARN_RX.search(s["title"]))]
    return sorted(m, key=lambda s: (-(4 * bool(MARKET_RX.search(s["title"])) + s.get("n_sources", 1)), -s.get("score", 0)))[:4]


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
    return [r["sym"] for rs in data.values() for r in rs if r.get("next_er") == str(next_day)]


def state():
    p = os.path.join(OUT_DIR, "大盘报告", "大盘历史.csv")
    rows = open(p, encoding="utf-8-sig").read().strip().splitlines()
    last = rows[-1].split(",")
    return last[0], last[1]


def build(day):
    mk = daily_moves(MARKETS)
    sec = daily_moves(SECTORS)
    stories = news_of(day)
    mv = movers(stories)
    past, ahead = econ(day)
    nxt = day + dt.timedelta(days=1 if day.weekday() < 4 else 3)
    ers = earnings(nxt)
    sdate, st = state()
    e = html.escape

    def p(x):
        return f"{x:+.1f}%"
    spy, qqq, iwm = mk.get("SPY"), mk.get("QQQ"), mk.get("IWM")
    big = max(abs(spy["chg"]), abs(qqq["chg"])) if spy and qqq else 0
    mood = ("大跌" if big >= 2 and qqq["chg"] < 0 else "大涨" if big >= 2 else "下跌" if spy and spy["chg"] < -0.3 else
            "上涨" if spy and spy["chg"] > 0.3 else "持平")
    lines = [f"<b>☀️ 早报 · 美股 {day:%m-%d}（周{WEEKDAY[day.weekday()]}）收盘</b>", ""]
    lines.append(f"<b>📉 昨晚：美股{mood}</b>" if "跌" in mood else f"<b>📈 昨晚：美股{mood}</b>")
    lines.append(f"标普 {p(spy['chg'])} · 纳指 {p(qqq['chg'])} · 小型股 {p(iwm['chg'])}")
    t = mk.get("^TNX"); v = mk.get("^VIX"); o = mk.get("CL=F"); u = mk.get("DX-Y.NYB"); g = mk.get("GC=F")
    lines.append(" · ".join(x for x in [
        f"10 年美债 {t['close']:.2f}%（{t['diff'] * 100:+.0f} 基点）" if t else "",
        f"VIX {v['close']:.1f}（{v['diff']:+.1f}）" if v else "",
        f"油 {p(o['chg'])}" if o else "", f"美元 {p(u['chg'])}" if u else "", f"金 {p(g['chg'])}" if g else ""] if x))
    lines += ["", "<b>❓ 为什么（相关新闻，不是因果分析）</b>"]
    mn = macro_news(stories)
    for s in mn:
        lines.append(f"• <a href=\"{e(s['link'])}\">{e(s['title'])}</a>" + (f"（{s['n_sources']} 家媒体）" if s.get("n_sources", 1) >= 2 else ""))
    for ev in past:
        zh = nd.CAL_ZH.get(ev["title"], ev["title"])
        lines.append(f"• 数据：{e(zh)} 预期 {e(ev.get('forecast') or '—')}，前值 {e(ev.get('previous') or '—')}")
    if not mn and not past:
        lines.append("• 没有找到明显的相关新闻或数据")
    lines += ["", "<b>🏭 行业</b>"]
    ss = sorted(sec.values(), key=lambda x: -x["chg"])
    if ss:
        top_lab = "领涨" if ss[0]["chg"] > 0 else "最抗跌"
        bot_lab = "领跌" if ss[-1]["chg"] < 0 else "涨最少"
        lines.append(f"{top_lab}：" + "、".join(f"{x['name']} {p(x['chg'])}" for x in ss[:2])
                     + f"　{bot_lab}：" + "、".join(f"{x['name']} {p(x['chg'])}" for x in ss[-2:][::-1]))
    lines += ["", "<b>🔥 大公司异动（市值 ≥500 亿）</b>"]
    for k, lab in (("up", "涨"), ("down", "跌")):
        for r in mv[k][:3]:
            why = f" — <a href=\"{e(r['news']['link'])}\">{e(r['news']['title'][:70])}</a>" if r["news"] else " — 没有找到相关新闻"
            lines.append(f"{'🟢' if k == 'up' else '🔴'} <b>{e(r['name'])}</b> {p(r['change'])}{why}")
    lines += ["", "<b>👀 今晚要看</b>"]
    for ev in ahead:
        if ev["impact"] == "High":
            zh = nd.CAL_ZH.get(ev["title"], ev["title"])
            lines.append(f"• {nd.to_et(dt.datetime.fromisoformat(ev['when'])):%H:%M} 美东　{e(zh)}（预期 {e(ev.get('forecast') or '—')}，前值 {e(ev.get('previous') or '—')}）")
    if ers:
        lines.append("• 业绩：" + "、".join(ers[:10]))
    if not ahead and not ers:
        lines.append("• 没有高影响力数据或大公司业绩")
    lines += ["", f"<b>🚦 大盘状态：{e(st)}</b>（{sdate}）", f"<a href=\"{SITE}\">打开每日报告 →</a>"]
    return "\n".join(lines), dict(markets=mk, sectors=sec, movers=mv, macro=mn, past=past, ahead=ahead, earnings=ers)


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
    spy, qqq = data["markets"].get("SPY"), data["markets"].get("QQQ")
    checks = [dict(name="早报行情", ok=bool(spy and qqq) and spy["date"] == day, critical=False,
                   detail=f"SPY {spy['chg']:+.1f}%（{spy['date']}）" if spy else "取不到"),
              dict(name="早报新闻", ok=bool(data["macro"]), critical=False, detail=f"{len(data['macro'])} 条大市新闻")]
    print(json.dumps({"html": base + ".html", "json": base + ".json", "date": str(day),
                      "spy": round(spy["chg"], 1) if spy else None, "qqq": round(qqq["chg"], 1) if qqq else None,
                      "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
