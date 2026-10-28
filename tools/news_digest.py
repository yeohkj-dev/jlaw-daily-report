"""每日 / 周末 市场新闻整理（不用 AI，按规则挑选和归类）。

  * 来源：CNBC、MarketWatch、Yahoo Finance 的 RSS，以及 Google News（汇总 Reuters、Bloomberg、WSJ 等的标题）
  * 时间窗口：每日版 = 最近 24 小时；周末版 = 周五美股收盘（美东 16:00）至今
  * 按关键词归入「美联储/利率、通胀、就业、经济数据、政策/关税、财报、能源/大宗、地缘、科技/AI、市场动态」，
    去掉个人理财等噪音；同一事件多家媒体报道会合并，并标出「多来源确认」
  * 附市场快照（指数、期货、利率、美元、油价、黄金、VIX）和本周 / 下周美国经济日历
  * 只显示媒体原标题、来源、时间、RSS 自带的简短摘要和原文链接；不改写内容

用法：python news_digest.py [输出目录] [--mode daily|weekend]（默认按今天星期几自动判断）
输出：<输出目录>/新闻/YYYY-MM-DD_<daily|weekend>.html 和 .json
仅供学习，不构成投资建议。
"""
import datetime as dt
import email.utils
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (AMBER, BLUE, GREEN, GREY, RED, TD, TDN, card, check_list_html, esc, fetch, fetch_json, h3, pct,
                    table, yahoo_chart)

argv = sys.argv[1:]
MODE = argv[argv.index("--mode") + 1] if "--mode" in argv else None
args = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i and argv[i - 1] == "--mode")]
OUT_DIR = args[0] if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_DIR = os.path.join(OUT_DIR, "新闻")
ET_TZ = dt.timezone(dt.timedelta(hours=-4))       # 美东夏令时；冬令时在下面按日期修正

FEEDS = {
    "CNBC": ["https://www.cnbc.com/id/100003114/device/rss/rss.html",   # Top News
             "https://www.cnbc.com/id/20910258/device/rss/rss.html",    # Economy
             "https://www.cnbc.com/id/10000664/device/rss/rss.html",    # Finance
             "https://www.cnbc.com/id/15839135/device/rss/rss.html"],   # Earnings
    "MarketWatch": ["https://feeds.content.dowjones.io/public/rss/mw_topstories",
                    "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"],
    "Yahoo Finance": ["https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC,^IXIC,^DJI&region=US&lang=en-US"],
}
GNEWS_QUERIES = ["stock market", "Federal Reserve", "inflation CPI OR PCE", "jobs report OR jobless claims",
                 "Treasury yields", "tariffs", "oil prices", "earnings results guidance", "Wall Street stocks futures"]
TRUSTED = ("Reuters", "Bloomberg", "The Wall Street Journal", "WSJ", "CNBC", "MarketWatch", "Financial Times",
           "Barron's", "Associated Press", "AP News", "Yahoo Finance", "The New York Times", "Fox Business",
           "Investopedia", "Axios", "Business Insider", "Forbes", "Morningstar", "Nasdaq", "Investor's Business Daily",
           "Seeking Alpha", "Kiplinger", "The Economist", "Politico", "CNN", "BBC")

TOPICS = [  # (标签, 权重, 关键词正则)
    ("美联储 / 利率", 10, r"\bfed\b|federal reserve|fomc|powell|rate cut|rate hike|interest rate|treasury yield|bond yield|10-year|yields?\b"),
    ("通胀", 9, r"inflation|\bcpi\b|\bpce\b|\bppi\b|consumer prices|price index"),
    ("就业", 9, r"payroll|jobs report|unemployment|jobless|labor market|nonfarm|hiring|layoffs"),
    ("经济数据", 7, r"\bgdp\b|recession|retail sales|\bism\b|\bpmi\b|consumer confidence|consumer sentiment|manufacturing|housing starts|durable goods|economy"),
    ("政策 / 关税", 8, r"tariff|trade war|trade deal|sanction|white house|trump|congress|shutdown|debt ceiling|regulat|treasury secretary|\bsec\b|antitrust"),
    ("财报 / 公司", 6, r"earnings|revenue|guidance|outlook|quarterly|results|beats|misses|profit|forecast|downgrade|upgrade|merger|acquisition|buyback"),
    ("能源 / 大宗", 6, r"\boil\b|crude|opec|brent|natural gas|gold|silver|copper|commodit"),
    ("地缘政治", 7, r"china|russia|ukraine|israel|iran|middle east|\bwar\b|taiwan|geopolit|missile|strike"),
    ("科技 / AI", 5, r"\bai\b|artificial intelligence|nvidia|chip|semiconductor|data center"),
    ("市场动态", 5, r"stocks?\b|s&p|dow\b|nasdaq|rally|sell-?off|futures|\bvix\b|wall street|record high|correction|bear market|bull market"),
]
NOISE = re.compile(r"\bbest\b|should you|retire|\bvs\.? .*\?|could have the edge|stocks? to (buy|watch)|is it time|"
                   r"(asx|ftse|nikkei|sensex|nifty|hang seng|kospi|tsx|dax|stoxx|australian|uk|indian?|canadian|european|south african) "
                   r"(stock|share|market|futures|central bank|rand|rupee)|\b(rba|rbnz|boj|ecb|boe|snb)\b|kiwi|\bsues\b|lawsuit|"
                   r"midterm|election|campaign|video$|bull case|"
                   r"mortgage rate|credit card|savings account|\bi'm\b|\bmy\b|personal finance|"
                   r"how to|\bquiz\b|horoscope|lottery|coupon|deal of the day|black friday|podcast|newsletter|watch live|"
                   r"what to know about|celebrity|recipe", re.I)
MEGA = re.compile(r"\b(apple|microsoft|nvidia|alphabet|google|amazon|meta|tesla|broadcom|berkshire|jpmorgan|visa|eli lilly|"
                  r"walmart|oracle|mastercard|exxon|netflix|costco|unitedhealth|home depot|procter|johnson & johnson|bank of america|"
                  r"amd|palantir|coca-cola|chevron|salesforce|goldman|morgan stanley|ibm|intel|boeing|caterpillar|s&p 500|dow|nasdaq)\b", re.I)
STOP = set("a an the of to in on for and or with at by from as is are be was were it its this that after over amid "
           "says said will may could new up down vs us u.s. stocks stock market".split())

SNAPSHOT = [("^GSPC", "标普 500"), ("^IXIC", "纳斯达克"), ("^DJI", "道琼斯"), ("^RUT", "罗素 2000"),
            ("ES=F", "标普期货"), ("NQ=F", "纳指期货"), ("^VIX", "VIX 恐慌指数"), ("^TNX", "10 年期美债收益率"),
            ("DX-Y.NYB", "美元指数"), ("CL=F", "WTI 原油"), ("GC=F", "黄金"), ("BTC-USD", "比特币")]


def et_offset(d):
    """美东时区：3 月第 2 个周日到 11 月第 1 个周日是夏令时（UTC-4），其余 UTC-5。"""
    y = d.year
    mar = dt.date(y, 3, 8) + dt.timedelta(days=(6 - dt.date(y, 3, 8).weekday()) % 7)
    nov = dt.date(y, 11, 1) + dt.timedelta(days=(6 - dt.date(y, 11, 1).weekday()) % 7)
    return dt.timezone(dt.timedelta(hours=-4 if mar <= d.date() < nov else -5))


def to_et(t):
    return t.astimezone(et_offset(t))


def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"&nbsp;|&#160;", " ", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&quot;|&#34;", '"', s)
    s = re.sub(r"&#39;|&apos;", "'", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_rss(xml_text, default_source):
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for it in root.iter("item"):
        title = strip_tags(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        src_el = it.find("source")
        source = (src_el.text.strip() if src_el is not None and src_el.text else default_source)
        desc = strip_tags(it.findtext("description"))
        try:
            when = email.utils.parsedate_to_datetime(pub) if pub else None
            if when and when.tzinfo is None:
                when = when.replace(tzinfo=dt.timezone.utc)
        except (TypeError, ValueError):
            when = None
        if source != default_source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        if desc.startswith(title[:40]) or default_source == "Google News":
            desc = ""                       # Google News 的描述只是标题和链接
        if title and link and when:
            out.append(dict(title=title, link=link, when=when, source=source, desc=desc[:260]))
    return out


def gather():
    jobs = [(src, u) for src, urls in FEEDS.items() for u in urls]
    jobs += [("Google News", "https://news.google.com/rss/search?q=" + q.replace(" ", "+") + "+when:2d&hl=en-US&gl=US&ceid=US:en")
             for q in GNEWS_QUERIES]
    ok, items = 0, []

    def one(job):
        try:
            return parse_rss(fetch(job[1], timeout=25, tries=2), job[0])
        except Exception:
            return None
    with ThreadPoolExecutor(8) as ex:
        for res in ex.map(one, jobs):
            if res is not None:
                ok += 1
                items += res
    return items, ok, len(jobs)


def stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 5 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokens(title):
    return {stem(w) for w in re.findall(r"[a-z0-9&'.-]+", title.lower()) if w not in STOP and len(w) > 2}


def classify(text):
    best, hits = None, []
    for label, w, rx in TOPICS:
        if re.search(rx, text, re.I):
            hits.append((w, label))
    if hits:
        best = max(hits)[1]
    return best, sum(w for w, _ in hits[:3])


def cluster(items):
    stories = []
    for it in sorted(items, key=lambda x: x["when"], reverse=True):
        tk = tokens(it["title"])
        if len(tk) < 3:
            continue
        for s in stories:
            inter = len(tk & s["tokens"])
            if inter >= 3 and inter / min(len(tk), len(s["base"])) >= 0.5:
                s["items"].append(it)
                s["tokens"] |= tk
                break
        else:
            stories.append(dict(tokens=set(tk), base=set(tk), items=[it]))
    out = []
    for s in stories:
        its = s["items"]
        lead = next((x for x in its if x["source"] in ("Reuters", "Bloomberg", "The Wall Street Journal", "CNBC", "MarketWatch")), its[0])
        sources = sorted({x["source"] for x in its})
        text = " ".join(x["title"] + " " + x["desc"] for x in its)
        topic, tscore = classify(text)
        if not topic or NOISE.search(lead["title"]):
            continue
        trusted = [x for x in sources if any(t.lower() in x.lower() for t in TRUSTED)]
        if not trusted:
            continue
        desc = next((x["desc"] for x in its if x["desc"]), "")
        score = tscore + 4 * (len(trusted) - 1) + (2 if len(sources) >= 3 else 0)
        if topic == "财报 / 公司" and not MEGA.search(text):
            score -= 4
        out.append(dict(topic=topic, title=lead["title"], link=lead["link"], source=lead["source"], sources=trusted,
                        when=min(x["when"] for x in its), latest=max(x["when"] for x in its), desc=desc,
                        n_sources=len(trusted), score=score))
    return sorted(out, key=lambda s: (-s["score"], -s["latest"].timestamp()))


def snapshot(weekend):
    rows = []

    def one(x):
        sym, name = x
        try:
            bars, meta = yahoo_chart(sym, "5d", "1d")
            price = meta.get("regularMarketPrice") or bars[-1]["c"]
            prev = meta.get("chartPreviousClose") if len(bars) < 2 else bars[-2]["c"]
            if weekend and sym.endswith("=F"):
                prev = bars[-2]["c"] if len(bars) >= 2 else prev     # 期货：对比周五收盘
            t = dt.datetime.fromtimestamp(meta.get("regularMarketTime") or bars[-1]["t"], dt.timezone.utc)
            return dict(sym=sym, name=name, price=price, chg=(price / prev - 1) * 100 if prev else None, time=t)
        except Exception:
            return dict(sym=sym, name=name, price=None, chg=None, time=None)
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(one, SNAPSHOT))
    return rows


def calendar(next_week):
    """Forex Factory 日历（有调用次数限制，所以缓存 3 小时）。"""
    which = "nextweek" if next_week else "thisweek"
    cache = os.path.join(NEWS_DIR, f"_calendar_{which}.json")
    data = None
    try:
        if time.time() - os.path.getmtime(cache) < 3 * 3600:
            with open(cache, encoding="utf-8") as f:
                data = json.load(f)
    except (OSError, ValueError):
        pass
    if data is None:
        try:
            data = fetch_json(f"https://nfs.faireconomy.media/ff_calendar_{which}.json", tries=2)
            os.makedirs(NEWS_DIR, exist_ok=True)
            with open(cache, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            return None
    out = []
    for e in data:
        if e.get("country") != "USD" or e.get("impact") not in ("High", "Medium"):
            continue
        try:
            t = dt.datetime.fromisoformat(e["date"])
        except (KeyError, ValueError):
            continue
        out.append(dict(title=e.get("title", ""), when=t, impact=e["impact"], forecast=e.get("forecast", ""),
                        previous=e.get("previous", ""), actual=e.get("actual", "")))
    return sorted(out, key=lambda x: x["when"])


CAL_ZH = {"CPI": "消费者物价指数", "Core CPI": "核心 CPI", "PPI": "生产者物价指数", "Core PPI": "核心 PPI",
          "Non-Farm Employment Change": "非农就业人数", "Unemployment Rate": "失业率", "Unemployment Claims": "首次申领失业金",
          "Federal Funds Rate": "联邦基金利率（议息）", "FOMC Statement": "FOMC 声明", "FOMC Press Conference": "FOMC 记者会",
          "FOMC Meeting Minutes": "FOMC 会议纪要", "Advance GDP q/q": "GDP 初值", "Prelim GDP q/q": "GDP 修正值",
          "Final GDP q/q": "GDP 终值", "Core PCE Price Index m/m": "核心 PCE 物价", "Retail Sales m/m": "零售销售",
          "Core Retail Sales m/m": "核心零售销售", "ISM Manufacturing PMI": "ISM 制造业 PMI", "ISM Services PMI": "ISM 服务业 PMI",
          "JOLTS Job Openings": "JOLTS 职位空缺", "ADP Non-Farm Employment Change": "ADP 就业人数", "CB Consumer Confidence": "谘商会消费者信心",
          "Prelim UoM Consumer Sentiment": "密歇根消费者信心初值", "Revised UoM Consumer Sentiment": "密歇根消费者信心终值",
          "Average Hourly Earnings m/m": "平均时薪", "Employment Cost Index q/q": "就业成本指数", "Pending Home Sales m/m": "成屋签约销售",
          "Existing Home Sales": "成屋销售", "New Home Sales": "新屋销售", "Durable Goods Orders m/m": "耐用品订单",
          "Core Durable Goods Orders m/m": "核心耐用品订单", "Powell Speaks": "鲍威尔讲话", "Fed Chair Powell Speaks": "鲍威尔讲话"}


def build_html(mode, now, window_start, stories, snap, cal, cal_label, checks):
    weekend = mode == "weekend"
    title = "周末新闻 · 影响周一开盘" if weekend else "今日市场新闻"
    win = f"{to_et(window_start):%m-%d %H:%M} 至 {to_et(now):%m-%d %H:%M}（美东时间）"
    multi = [s for s in stories if s["n_sources"] >= 2]
    # 市场快照
    srows = ""
    for r in snap:
        if r["price"] is None:
            srows += f'<tr><td {TD}>{esc(r["name"])}</td><td {TDN} colspan="3" style="color:#aaa;">没有取到数据</td></tr>'
            continue
        p = r["price"]
        ptxt = f"{p:,.2f}" + ("%" if r["sym"] == "^TNX" else "")
        srows += (f'<tr><td {TD}><b>{esc(r["name"])}</b> <span style="color:#999;font-size:11px;">{esc(r["sym"])}</span></td>'
                  f'<td {TDN}>{ptxt}</td><td {TDN}>{pct(r["chg"], 2)}</td>'
                  f'<td {TDN} style="color:#888;font-size:12px;">{to_et(r["time"]):%m-%d %H:%M} ET</td></tr>')
    snap_html = table(("品种", "最新", "变动" + ("（对比周五）" if weekend else ""), "数据时间"), srows)
    # 重点：多来源
    def story_li(s, show_topic=True):
        badge = (f'<span style="background:#E8F5E9;color:{GREEN};font-size:11px;padding:1px 6px;border-radius:8px;">'
                 f'{s["n_sources"]} 家媒体报道</span>' if s["n_sources"] >= 2 else
                 '<span style="background:#f2f2f2;color:#888;font-size:11px;padding:1px 6px;border-radius:8px;">单一来源</span>')
        topic = (f'<span style="color:{BLUE};font-size:12px;font-weight:600;">[{esc(s["topic"])}]</span> ' if show_topic else "")
        desc = f'<div style="color:#555;font-size:12px;margin-top:2px;">{esc(s["desc"])}</div>' if s["desc"] else ""
        srcs = "、".join(s["sources"][:5])
        return (f'<li style="margin:0 0 10px;">{topic}<a href="{esc(s["link"])}" target="_blank" rel="noopener" '
                f'style="color:#111;font-weight:600;text-decoration:none;">{esc(s["title"])}</a> {badge}'
                f'<div style="color:#888;font-size:11px;">{esc(srcs)} · {to_et(s["latest"]):%m-%d %H:%M} ET</div>{desc}</li>')
    top = multi[:8] if len(multi) >= 3 else stories[:8]
    top_html = '<ol style="margin:0;padding-left:22px;">' + "".join(story_li(s) for s in top) + "</ol>"
    # 按主题
    by_topic = ""
    shown = {id(s) for s in top}
    for label, _, _ in TOPICS:
        group = [s for s in stories if s["topic"] == label and id(s) not in shown][:6]
        if group:
            by_topic += (f'<div style="margin:14px 0 4px;font-weight:700;">{esc(label)}</div>'
                         f'<ul style="margin:0;padding-left:20px;">' + "".join(story_li(s, False) for s in group) + "</ul>")
    # 日历
    if cal is None:
        cal_html = '<p style="color:#888;">没有取到经济日历。</p>'
    elif not cal:
        cal_html = '<p style="color:#888;">没有中、高影响力的美国经济数据。</p>'
    else:
        crow = ""
        for e in cal:
            imp = (f'<span style="color:{RED};font-weight:700;">高</span>' if e["impact"] == "High" else
                   f'<span style="color:{AMBER};">中</span>')
            zh = CAL_ZH.get(e["title"], "")
            crow += (f'<tr><td {TDN}>{to_et(e["when"]):%m-%d %a %H:%M}</td><td {TDN}>{imp}</td>'
                     f'<td {TD}><b>{esc(zh or e["title"])}</b>' + (f'<br><span style="color:#999;font-size:11px;">{esc(e["title"])}</span>' if zh else "")
                     + f'</td><td {TDN}>{esc(e["actual"] or "—")}</td><td {TDN}>{esc(e["forecast"] or "—")}</td><td {TDN}>{esc(e["previous"] or "—")}</td></tr>')
        cal_html = table(("时间（美东）", "影响", "数据", "实际", "预期", "前值"), crow)
    sub = f'<div style="font-size:13px;color:#555;">新闻窗口：{win} · 共 {len(stories)} 条事件，其中 {len(multi)} 条有多家媒体报道</div>'
    body = (h3("市场快照") + snap_html
            + h3("重点新闻（多家媒体报道的优先）", GREEN) + top_html
            + h3("按主题") + (by_topic or '<p style="color:#888;">没有其他新闻。</p>')
            + h3(cal_label) + cal_html
            + h3("数据核对", GREY) + check_list_html(checks)
            + '<p style="color:#888;font-size:11px;margin-top:14px;">新闻按关键词自动挑选和归类，只显示媒体原标题、来源和 RSS 自带的摘要，'
              '点标题看原文。「N 家媒体报道」表示多家可信媒体在窗口内报道了相近标题。数据来自 Yahoo Finance 与 Forex Factory 日历。'
              '仅供学习，不构成投资建议。</p>')
    return card(esc(title), body, accent=BLUE, bg="#EEF4FA", sub=sub)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(NEWS_DIR, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    mode = MODE or ("weekend" if now.weekday() in (5, 6) else "daily")
    if mode == "weekend":
        et_now = to_et(now)
        fri = et_now.date() - dt.timedelta(days=(et_now.weekday() - 4) % 7)
        window_start = dt.datetime(fri.year, fri.month, fri.day, 16, 0, tzinfo=et_offset(now))
    else:
        window_start = now - dt.timedelta(hours=24)
    items, ok_feeds, n_feeds = gather()
    items = [x for x in items if window_start <= x["when"] <= now + dt.timedelta(minutes=10)]
    stories = cluster(items)
    snap = snapshot(mode == "weekend")
    et_now = to_et(now)
    next_week = mode == "weekend" and et_now.weekday() == 5        # 周六取下周；周日起 Forex Factory 的「本周」已是新一周
    cal = calendar(next_week)
    cal_label = "下周美国经济日历（中、高影响力）" if mode == "weekend" else "本周美国经济日历（中、高影响力）"

    got = [r for r in snap if r["price"] is not None]
    fresh = [r for r in got if r["time"] and (now - r["time"]).days <= 4]
    checks = [
        dict(name="新闻来源", ok=ok_feeds >= n_feeds * 0.6, critical=ok_feeds == 0, detail=f"{ok_feeds}/{n_feeds} 个 RSS 成功"),
        dict(name="新闻数量", ok=len(stories) >= 8, critical=len(stories) == 0, detail=f"窗口内 {len(items)} 条标题，合并后 {len(stories)} 个事件"),
        dict(name="多来源确认", ok=sum(1 for s in stories if s["n_sources"] >= 2) >= 3, critical=False,
             detail=f"{sum(1 for s in stories if s['n_sources'] >= 2)} 个事件有 ≥2 家媒体报道"),
        dict(name="市场快照", ok=len(got) == len(snap), critical=len(got) < len(snap) / 2, detail=f"{len(got)}/{len(snap)} 个品种取到数据"),
        dict(name="快照数据新鲜度", ok=len(fresh) == len(got), critical=False, detail=f"{len(fresh)}/{len(got)} 个在 4 天内更新"),
        dict(name="经济日历", ok=cal is not None, critical=False, detail="Forex Factory" if cal is not None else "没有取到"),
    ]
    html_frag = build_html(mode, now, window_start, stories, snap, cal, cal_label, checks)
    day = et_now.date()
    base = os.path.join(NEWS_DIR, f"{day}_{mode}")
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "</head><body style=\"margin:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222;\">"
                + html_frag + "</body></html>")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(dict(mode=mode, generated=now.isoformat(), window_start=window_start.isoformat(),
                       stories=[{k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in s.items()} for s in stories[:60]],
                       checks=checks), f, ensure_ascii=False, indent=1)
    print(json.dumps({"html": base + ".html", "mode": mode, "stories": len(stories),
                      "multi_source": sum(1 for s in stories if s["n_sources"] >= 2), "checks": checks,
                      "top": [s["title"] for s in stories[:5]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
