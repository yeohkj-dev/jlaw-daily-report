"""周末版早报：周末有什么会影响周一开市。规则整理，不用 AI。

周日晚上（美东，期货刚开盘后）跑：周末新闻（周五收盘后至今）、周日晚期货、上周回顾、下周经济日历和大公司业绩、大盘状态。
马来西亚时间周一早上发到 Telegram，网站「早报」分页周末也换成这一份。
用法：python weekend_brief.py [输出目录] [--force]（不是美东周六 / 周日就跳过，--force 测试用）
输出：<输出目录>/早报/周末_YYYY-MM-DD.json（telegram_html、crosscheck）和 .html
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
import morning_brief as mb

argv = sys.argv[1:]
FORCE = "--force" in argv
ASOF = argv[argv.index("--asof") + 1] if "--asof" in argv else None          # 测试用：模拟某个周日晚上 19:00（美东）
args = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i and argv[i - 1] == "--asof")]
OUT_DIR = args[0] if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_DIR = os.path.join(OUT_DIR, "新闻")
WEEKDAY = "一二三四五六日"
FUTURES = [("CME_MINI:ES1!", "ES=F", "标普期货"), ("CME_MINI:NQ1!", "NQ=F", "纳指期货"), ("CME_MINI:RTY1!", "RTY=F", "罗素期货"),
           ("NYMEX:CL1!", "CL=F", "原油"), ("COMEX:GC1!", "GC=F", "黄金")]
INDEX = [("SPY", "AMEX", "标普"), ("QQQ", "NASDAQ", "纳指"), ("IWM", "AMEX", "小型股")]
e = lambda x: html.escape(str(x), quote=False)


def latest_weekend_news():
    f = sorted(glob.glob(os.path.join(NEWS_DIR, "20??-??-??_weekend.json")))
    if not f:
        return [], None
    d = json.load(open(f[-1], encoding="utf-8"))
    return d.get("stories", []), d.get("window_start")


def pick_news(stories):
    """大市新闻：讲市场 / 利率 / 政策 / 地缘 / AI 的，多家媒体优先；另挑最多 3 条大公司消息。"""
    macro_topics = ("美联储 / 利率", "通胀", "就业", "经济数据", "市场动态", "政策 / 关税", "地缘政治", "能源 / 大宗", "科技 / AI")
    def ok(s):
        t = s["title"]
        if mb.MARKET_RX.search(t):
            return True
        if mb.POLITICS_RX.search(t) and not mb.POLICY_RX.search(t):
            return False
        if s.get("topic") in ("政策 / 关税", "地缘政治"):
            return bool(mb.POLICY_RX.search(t))
        return s.get("topic") in macro_topics and not mb.EARN_RX.search(t)
    rank = lambda s: (-(s.get("n_sources", 1) * 3 + 4 * bool(mb.MARKET_RX.search(s["title"])) + s.get("score", 0) / 10))
    macro = sorted([s for s in stories if ok(s)], key=rank)[:6]
    taken = {id(s) for s in macro}
    comp = sorted([s for s in stories if id(s) not in taken and s.get("topic") in ("财报 / 公司", "科技 / AI")
                   and (s.get("n_sources", 1) >= 2 or nd.MEGA.search(s["title"]))], key=rank)[:3]
    return macro, comp


def futures():
    """TradingView 期货（对比周五结算）；Yahoo 的最新成交时间用来判断周日晚是否已开盘。"""
    tv = mb.tv_quotes([t for t, _, _ in FUTURES], "global")
    out = []
    for t, ysym, name in FUTURES:
        q = tv.get(t)
        opened = None
        try:
            _, meta = yahoo_chart(ysym, "1d", "5m")
            last = dt.datetime.fromtimestamp(meta["regularMarketTime"], dt.timezone.utc)
            opened = nd.to_et(last).weekday() == 6 or nd.to_et(last).weekday() == 0          # 周日晚以后有成交
            ypx, yprev = meta.get("regularMarketPrice"), meta.get("chartPreviousClose")
        except Exception:
            ypx = yprev = None
        out.append(dict(t=t, ysym=ysym, name=name, q=q, opened=opened, ypx=ypx, yprev=yprev))
    return out


def last_week(friday):
    """上周涨跌 = 这个周五收盘 ÷ 上个周五收盘（Yahoo 日线）；再用 Yahoo 周线核对，收盘价也和 TradingView 比。
    （TradingView 的 Perf.W 是「最近 7 天」，不一定是周五对周五，所以不用它。）"""
    tvc = {r["d"][0]: r["d"][1] for r in tv_scan({"symbols": {"tickers": [f"{ex}:{s}" for s, ex, _ in INDEX]}, "columns": ["name", "close"]})}
    out = []
    for s, ex, n in INDEX:
        day = wk = fri_close = None
        try:
            bars, _ = yahoo_chart(s, "1mo", "1d")
            d = {dt.datetime.fromtimestamp(b["t"], dt.timezone.utc).date(): b["c"] for b in bars}
            prev = max((x for x in d if x <= friday - dt.timedelta(days=7)), default=None)
            if friday in d and prev:
                fri_close, day = d[friday], (d[friday] / d[prev] - 1) * 100
            wbars, _ = yahoo_chart(s, "3mo", "1wk")
            # 周线按「这一周的周一」取；Yahoo 最后会多一根重复的，所以按日期找，不用最后两根
            w = {}
            for b_ in wbars:
                dd = dt.datetime.fromtimestamp(b_["t"], dt.timezone.utc).date()
                w[dd - dt.timedelta(days=dd.weekday())] = b_["c"]
            mon = friday - dt.timedelta(days=4)
            if mon in w and mon - dt.timedelta(days=7) in w:
                wk = (w[mon] / w[mon - dt.timedelta(days=7)] - 1) * 100
        except Exception:
            pass
        out.append(dict(sym=s, ex=ex, name=n, chg=day, wk=wk, close=fri_close, tv_close=tvc.get(s)))
    return out


def next_week_events(et):
    nxt = et.date() + dt.timedelta(days=(7 - et.weekday()) % 7 or 7)            # 下一个周一
    cal = nd.calendar(et.weekday() == 5) or []                                      # 周六取「下周」，周日「本周」已是新一周
    evs = [x for x in cal if nxt <= nd.to_et(x["when"]).date() <= nxt + dt.timedelta(days=4) and x["impact"] == "High"]
    f = sorted(glob.glob(os.path.join(OUT_DIR, "业绩估值", "20??-??-??.json")))
    ers = []
    if f:
        data = json.load(open(f[-1], encoding="utf-8"))
        ers = sorted(((r["next_er"], r["sym"], r.get("exchange") or "") for rs in data.values() for r in rs
                      if r.get("next_er") and nxt <= dt.date.fromisoformat(r["next_er"]) <= nxt + dt.timedelta(days=4)))
    return nxt, evs, ers


def build(et):
    stories, win = latest_weekend_news()
    macro, comp = pick_news(stories)
    fut = futures()
    friday = et.date() - dt.timedelta(days=(et.weekday() - 4) % 7)
    wk = last_week(friday)
    nxt, evs, ers = next_week_events(et)
    sdate, st = mb.state()
    L = [f"<b>🗓 周末版 · 影响周一（{nxt:%m-%d}）开市</b>", ""]

    es = next((x for x in fut if x["t"] == "CME_MINI:ES1!"), None)
    nq = next((x for x in fut if x["t"] == "CME_MINI:NQ1!"), None)
    if es and es["opened"] and es["q"]:
        lead = es["q"]["chg"] if not (nq and nq["q"]) or abs(es["q"]["chg"]) >= abs(nq["q"]["chg"]) else nq["q"]["chg"]
        tone = "📈 期货开盘偏强" if lead >= 0.5 else "📉 期货开盘偏弱" if lead <= -0.5 else "➖ 期货开盘平稳"
        L.append(f"<b>{tone}（周日晚，对比周五结算）</b>")
    else:
        L.append("<b>⏳ 期货还没开盘（美东周日 18:00 开盘），下面是周五的涨跌</b>")
    L.append(" · ".join(f"{x['name']} {x['q']['chg']:+.2f}%" for x in fut if x["q"]))

    L += ["", "<b>📰 周末重要新闻（周五收盘后）</b>"]
    for s in macro:
        L.append(f"• <a href=\"{html.escape(s['link'])}\">{e(s['title'])}</a>" + (f"（{s['n_sources']} 家媒体）" if s.get("n_sources", 1) >= 2 else ""))
    if not macro:
        L.append("• 周末没有重要的大市新闻")
    if comp:
        L += ["", "<b>🏢 公司消息</b>"]
        for s in comp:
            L.append(f"• <a href=\"{html.escape(s['link'])}\">{e(s['title'])}</a>" + (f"（{s['n_sources']} 家媒体）" if s.get("n_sources", 1) >= 2 else ""))

    L += ["", "<b>📊 上周</b>"]
    L.append(" · ".join(f"{mb.tv_link(x['sym'], x['ex'], x['name'])} {x['chg']:+.1f}%" for x in wk if x["chg"] is not None))

    L += ["", f"<b>👀 下周（{nxt:%m-%d} 起）要看</b>"]
    by_day = {}
    for x in evs:
        t = x["when"]
        by_day.setdefault(nd.to_et(t).date(), []).append(
            f"{nd.to_et(t):%H:%M} 美东（马来西亚 {t.astimezone(mb.MY_TZ):%H:%M}）{e(nd.CAL_ZH.get(x['title'], x['title']))}"
            f"（预期 {e(x.get('forecast') or '—')}，前值 {e(x.get('previous') or '—')}）")
    for d_, sym, ex in ers:
        by_day.setdefault(dt.date.fromisoformat(d_), [])
    for d_ in sorted(by_day):
        items = by_day[d_]
        day_ers = [mb.tv_link(sym, ex) for dd, sym, ex in ers if dt.date.fromisoformat(dd) == d_]
        L.append(f"<b>周{WEEKDAY[d_.weekday()]} {d_:%m-%d}</b>")
        L += [f"• {x}" for x in items]
        if day_ers:
            L.append("• 业绩：" + "、".join(day_ers))
    if not by_day:
        L.append("• 下周没有高影响力数据或大公司业绩（或日历还没取到）")

    li = {"🟢": "绿灯 0.5%", "🟡": "黄灯 0.35%", "🔴": "红灯 0.25%"}.get(st[:1], "")
    L += ["", f"<b>🚦 大盘状态：{e(st)}</b>（{sdate}）" + (f" → {li}" if li else ""),
          f"<a href=\"{mb.SITE}\">打开每日报告 →</a>", "<i>仅供学习，不构成投资建议</i>"]

    # 交叉核对：期货 TradingView vs Yahoo（同一合约前一天结算是否一致）、上周涨跌 TradingView vs Yahoo
    chk = []
    for x in fut:
        if x["q"] and x["yprev"]:
            tv_prev = x["q"]["close"] / (1 + x["q"]["chg"] / 100)
            chk.append(dict(item=x["name"], brief=round(x["q"]["chg"], 2), check=f"前一天结算 {tv_prev:.2f} vs Yahoo {x['yprev']:.2f}",
                            source="Yahoo " + x["ysym"], ok=abs(tv_prev / x["yprev"] - 1) <= 0.003))
    for x in wk:
        if x["chg"] is not None:
            chk.append(dict(item=f"{x['name']} 上周", brief=round(x["chg"], 2), check=None if x["wk"] is None else round(x["wk"], 2),
                            source="Yahoo 周线", ok=None if x["wk"] is None else abs(x["chg"] - x["wk"]) <= 0.2))
        if x["close"] and x["tv_close"]:
            chk.append(dict(item=f"{x['name']} 周五收盘", brief=round(x["close"], 2), check=round(x["tv_close"], 2), source="TradingView",
                            ok=abs(x["close"] / x["tv_close"] - 1) <= 0.002))
    return "\n".join(L), nxt, chk, dict(news=len(stories), window=win, events=len(evs), earnings=len(ers))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    now = dt.datetime.now(dt.timezone.utc)
    et = nd.to_et(now)
    if ASOF:
        a = dt.date.fromisoformat(ASOF)
        et = nd.to_et(dt.datetime(a.year, a.month, a.day, 0, 0, tzinfo=dt.timezone.utc) + dt.timedelta(days=1))   # 美东前一天 19:00 左右
    if et.weekday() < 5 and not FORCE:
        print(json.dumps({"skip": f"美东现在周{WEEKDAY[et.weekday()]}，不是周末"}, ensure_ascii=False))
        return
    text, nxt, chk, info = build(et)
    os.makedirs(os.path.join(OUT_DIR, "早报"), exist_ok=True)
    day = et.date()
    base = os.path.join(OUT_DIR, "早报", f"周末_{day}")
    json.dump(dict(date=str(day), next_monday=str(nxt), telegram_html=text, crosscheck=chk), open(base + ".json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    page = mb.web_html(text).replace("昨晚美股发生什么、为什么、谁在带动、今晚要看什么", "周末新闻、周日晚期货、上周回顾、下周要看什么")
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "</head><body style=\"margin:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222;\">"
                + page + "</body></html>")
    bad = [c for c in chk if c["ok"] is False]
    checks = [dict(name="周末版逐项核对", ok=not bad, critical=False,
                   detail=f"{sum(1 for c in chk if c['ok'])}/{len(chk)} 项一致" + (f"；不一致：{'、'.join(c['item'] for c in bad)}" if bad else "")),
              dict(name="周末新闻", ok=info["news"] > 0, critical=False, detail=f"{info['news']} 条（{info['window'] or '—'} 起）"),
              dict(name="下周日历", ok=info["events"] > 0, critical=False, detail=f"{info['events']} 项高影响力数据，{info['earnings']} 家公布业绩")]
    print(json.dumps({"html": base + ".html", "json": base + ".json", "next_monday": str(nxt), "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
