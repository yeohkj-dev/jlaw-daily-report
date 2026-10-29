"""本周重大事件（不用 AI，按规则整理）。平日每天更新；周末版变成「本周回顾」。

  * 本周至今走势：SPY / QQQ / IWM / DIA、VIX、10 年期利率，对比上周五收盘，并列出每天涨跌
  * 本周重要经济数据（Forex Factory 高影响力）：已公布 / 待公布；已公布的配上本周新闻里相关的标题
    （Forex Factory 的免费数据没有「实际值」，所以用新闻标题说明结果，点开看原文）
  * 本周大公司财报：各板块前 10 大里本周已公布的（EPS / 营收对比预期、股价反应）和本周还没公布的
  * 本周最重大的新闻：把本周每天的新闻 JSON 合并，按重要性、媒体数、连续被报道的天数排序

用法：python weekly_events.py [输出目录] [--mode daily|weekend]
输入：新闻/YYYY-MM-DD_<daily|weekend>.json（每天的新闻）、业绩估值/YYYY-MM-DD.json
输出：<输出目录>/新闻/本周事件_YYYY-MM-DD.html 和 .json；本周经济日历存到 新闻/week_<周一>.json（周末回顾用）
仅供学习，不构成投资建议。
"""
import datetime as dt
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import AMBER, BLUE, GREEN, GREY, RED, TD, TDN, card, check_list_html, esc, h3, pct, table, tv_scan, yahoo_chart
import news_digest as nd

argv = sys.argv[1:]
MODE = argv[argv.index("--mode") + 1] if "--mode" in argv else None
args = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i and argv[i - 1] == "--mode")]
OUT_DIR = args[0] if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_DIR = os.path.join(OUT_DIR, "新闻")
KEEP_DAYS = 30
WEEKDAY = "一二三四五六日"
INDEXES = [("SPY", "标普 500"), ("QQQ", "纳斯达克 100"), ("IWM", "罗素 2000"), ("DIA", "道琼斯"),
           ("^VIX", "VIX 恐慌指数"), ("^TNX", "10 年期美债利率")]
TV = {"SPY": "AMEX:SPY", "QQQ": "NASDAQ:QQQ", "IWM": "AMEX:IWM", "DIA": "AMEX:DIA", "^VIX": "TVC:VIX", "^TNX": "TVC:TNX"}
# 经济数据 → 新闻标题关键词（用来找「结果」新闻）
EVENT_NEWS = [(r"Core CPI|^CPI", r"\bCPI\b|consumer price|inflation"), (r"PPI", r"\bPPI\b|producer price"),
              (r"PCE", r"\bPCE\b|inflation"), (r"Non-Farm|Unemployment Rate|Average Hourly", r"payroll|jobs report|unemployment rate|hiring"),
              (r"ADP", r"\bADP\b|private payroll"), (r"Unemployment Claims", r"jobless claims|unemployment claims"),
              (r"Federal Funds|FOMC|Fed Chair|Powell", r"\bFed\b|FOMC|Powell|rate cut|rate hike|interest rate"),
              (r"GDP", r"\bGDP\b|economy (grew|shr)|economic growth"), (r"Retail Sales", r"retail sales"),
              (r"ISM|PMI", r"\bISM\b|\bPMI\b|manufacturing|services sector"), (r"JOLTS", r"job openings|JOLTS"),
              (r"Consumer Confidence|Consumer Sentiment|UoM", r"consumer (confidence|sentiment)"),
              (r"Employment Cost", r"employment cost|wage"), (r"Home Sales|Housing|Building Permits", r"home sales|housing|homebuild")]


def et_now():
    now = dt.datetime.now(dt.timezone.utc)
    return now, nd.to_et(now)


def week_bounds(today, weekend):
    """本周一的日期；周末版就是刚结束的那一周。"""
    monday = today - dt.timedelta(days=today.weekday())
    return monday, monday + dt.timedelta(days=4)


def load_week_news(monday, today):
    """本周每天的新闻 JSON（含周一之前的那个周末版）。"""
    out = []
    for f in sorted(glob.glob(os.path.join(NEWS_DIR, "20??-??-??_*.json"))):
        name = os.path.basename(f)
        d = dt.date.fromisoformat(name[:10])
        mode = name[11:-5]
        ok = (mode == "daily" and monday <= d <= today and d.weekday() < 5) or \
             (mode == "weekend" and monday - dt.timedelta(days=2) <= d < monday and d.weekday() >= 5)
        if not ok:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        for s in data.get("stories", []):
            s["day"] = d
            out.append(s)
    return out


def merge_week(stories):
    """跨天合并同一事件：标题词重叠 ≥3 且 ≥ 较短标题的一半。"""
    groups = []
    for s in sorted(stories, key=lambda x: -x.get("score", 0)):
        tk = nd.tokens(s["title"])
        if len(tk) < 3:
            continue
        for g in groups:
            inter = len(tk & g["tokens"])
            if inter >= 3 and inter / min(len(tk), len(g["base"])) >= 0.5:
                g["items"].append(s)
                g["tokens"] |= tk
                break
        else:
            groups.append(dict(tokens=set(tk), base=set(tk), items=[s]))
    out = []
    for g in groups:
        its = g["items"]
        lead = max(its, key=lambda x: (x.get("n_sources", 1), x.get("score", 0)))
        days = sorted({x["day"] for x in its})
        srcs = sorted({src for x in its for src in x.get("sources", [])})
        score = max(x.get("score", 0) for x in its) + 3 * (len(days) - 1) + 2 * (len(srcs) - 1)
        latest = max(dt.datetime.fromisoformat(x["latest"]) for x in its if x.get("latest"))
        out.append(dict(title=lead["title"], link=lead["link"], topic=lead.get("topic", ""), days=days, sources=srcs,
                        score=score, desc=lead.get("desc", ""), latest=latest))
    return sorted(out, key=lambda x: -x["score"])


def index_week(monday, last_day):
    """各指数本周至今：上周五收盘 → 最新，以及每天的涨跌。"""
    rows = []
    for sym, name in INDEXES:
        try:
            bars, _ = yahoo_chart(sym, "1mo", "1d")
        except Exception:
            rows.append(dict(sym=sym, name=name, ok=False))
            continue
        bars = [dict(b, d=nd.to_et(dt.datetime.fromtimestamp(b["t"], dt.timezone.utc)).date()) for b in bars if b.get("c")]
        base = [b for b in bars if b["d"] < monday]
        week = [b for b in bars if monday <= b["d"] <= last_day]
        if not base or not week:
            rows.append(dict(sym=sym, name=name, ok=False))
            continue
        prev, daily = base[-1]["c"], []
        for b in week:
            daily.append((b["d"], b["c"] - prev if sym == "^TNX" else b["c"] / prev - 1))
            prev = b["c"]
        chg = week[-1]["c"] / base[-1]["c"] - 1
        rows.append(dict(sym=sym, name=name, ok=True, base=base[-1]["c"], last=week[-1]["c"], last_d=week[-1]["d"],
                         chg=chg, diff=week[-1]["c"] - base[-1]["c"], daily=daily))
    return rows


def week_calendar(monday, weekend, et):
    """本周高影响力美国数据。平日从 Forex Factory「本周」取，并存档；周末读存档（周日 FF 已换成下周）。"""
    path = os.path.join(NEWS_DIR, f"week_{monday}.json")
    cal = None
    if not weekend or et.weekday() == 5:
        cal = nd.calendar(False)
        if cal and not any(monday <= nd.to_et(e["when"]).date() <= monday + dt.timedelta(days=6) for e in cal):
            cal = None                                    # 缓存不是这一周的
    if cal:
        keep = [dict(e, when=e["when"].isoformat()) for e in cal if e["impact"] == "High"]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False, indent=1)
    try:
        with open(path, encoding="utf-8") as f:
            return [dict(e, when=dt.datetime.fromisoformat(e["when"])) for e in json.load(f)], True
    except (OSError, ValueError):
        return [], False


PREVIEW = re.compile(r"\bahead of\b|\bbefore\b|\bpreview\b|\bexpect|\bwill\b|\bawait|\bset to\b|what to watch", re.I)


RESULT = re.compile(r"\b(holds?|held|keeps?|leaves?|cuts?|raises?|hikes?|pauses?|unchanged|steady|rose|rises|fell|falls|"
                    r"grew|grows|jump(s|ed)?|slow(s|ed)|surg(es|ed)|beat|miss(es|ed)?|came in|decision)\b", re.I)


# 评论 / 假设类标题（某人说、如果、问句）排后面
OPINION = re.compile(r"\?|\bif\b|\bsays?\b|\bcould\b|\bmight\b|\bmay\b|\bshould\b|\bmistake\b|\bopinion\b", re.I)


def match_news(e, stories):
    """只取数据公布之后、且不是「前瞻 / 等待」类的标题。"""
    for ev_rx, news_rx in EVENT_NEWS:
        if re.search(ev_rx, e["title"], re.I):
            hits = [s for s in stories if s["latest"] >= e["when"] and re.search(news_rx, s["title"], re.I)
                    and not PREVIEW.search(s["title"])]
            # 关键词后面紧跟「结果」动词的最优先（Fed holds / GDP grew …），其次有结果动词，再其次媒体数、离公布时间近的
            direct = re.compile(rf"(?:{news_rx})\W+(?:\w+\W+){{0,2}}?{RESULT.pattern}", re.I)
            hits.sort(key=lambda x: (-6 * bool(direct.search(x["title"])) - 3 * bool(RESULT.search(x["title"]))
                                     + 5 * bool(OPINION.search(x["title"])) - len(x["sources"]), x["latest"]))
            return hits[:2]
    return []


def week_earnings(monday, friday, today):
    files = sorted(glob.glob(os.path.join(OUT_DIR, "业绩估值", "20??-??-??.json")))
    if not files:
        return [], [], None
    with open(files[-1], encoding="utf-8") as f:
        data = json.load(f)
    done, todo = [], []
    for sec, rs in data.items():
        for r in rs:
            rel = r.get("release")
            if rel and monday <= dt.date.fromisoformat(rel) <= friday:
                done.append(dict(r, sec=sec))
            elif r.get("next_er") and today <= dt.date.fromisoformat(r["next_er"]) <= friday:
                todo.append(dict(r, sec=sec))
    done.sort(key=lambda r: -float(r.get("mcap") or 0))
    todo.sort(key=lambda r: (r["next_er"], -float(r.get("mcap") or 0)))
    return done, todo, os.path.basename(files[-1])[:10]


def prune():
    cut = dt.date.today() - dt.timedelta(days=KEEP_DAYS)
    for f in glob.glob(os.path.join(NEWS_DIR, "20??-??-??_*.json")) + glob.glob(os.path.join(NEWS_DIR, "week_20??-??-??.json")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f))
        if m and dt.date.fromisoformat(m.group(1)) < cut:
            os.remove(f)


def tv_a(sym, text=None):
    url = "https://www.tradingview.com/chart/?symbol=" + TV.get(sym, sym)
    return (f'<a href="{esc(url)}" target="_blank" rel="noopener" style="color:#1565C0;text-decoration:none;font-weight:700;">'
            f'{esc(text or sym)} <span style="font-size:11px;">📈</span></a>')


def build_html(weekend, monday, friday, et, idx, cal, stories, raw, done, todo, ev_date, n_days, checks):
    title = (f"本周回顾 · {monday:%m-%d} 至 {friday:%m-%d}" if weekend else
             f"本周重大事件 · {monday:%m-%d} 至 {friday:%m-%d}（截至周{WEEKDAY[et.weekday()]}）")
    now_utc = dt.datetime.now(dt.timezone.utc)
    past = [e for e in cal if e["when"] <= now_utc]
    ahead = [e for e in cal if e["when"] > now_utc]

    # ---- 一句话总结 ----
    spy = next((r for r in idx if r["sym"] == "SPY" and r["ok"]), None)
    qqq = next((r for r in idx if r["sym"] == "QQQ" and r["ok"]), None)
    iwm = next((r for r in idx if r["sym"] == "IWM" and r["ok"]), None)
    bullets = []
    if spy:
        bullets.append(f'本周{"" if weekend else "至今"}标普 500（SPY）{pct(spy["chg"] * 100)}'
                       + (f'，纳指 100（QQQ）{pct(qqq["chg"] * 100)}' if qqq else "")
                       + (f'，小型股（IWM）{pct(iwm["chg"] * 100)}' if iwm else "") + "。")
    if cal:
        nxt = ahead[0] if ahead else None
        bullets.append(f"重要经济数据：已公布 {len(past)} 项，还有 {len(ahead)} 项"
                       + (f"，下一项是 {to_et_str(nxt['when'])} 的 <b>{esc(nd.CAL_ZH.get(nxt['title'], nxt['title']))}</b>" if nxt else "") + "。")
    if done or todo:
        reacts = [float(r["react"]) for r in done if r.get("react") not in (None, "")]
        beats = sum(1 for r in done if r.get("eps_beat") not in (None, "") and float(r["eps_beat"]) > 0)
        bullets.append(f"大公司财报：本周已公布 {len(done)} 家（{beats} 家 EPS 超预期"
                       + (f"，股价平均反应 {pct(sum(reacts) / len(reacts))}" if reacts else "") + "）"
                       + (f"，还有 {len(todo)} 家待公布" if todo and not weekend else "") + "。")
    if stories:
        top = next((x for x in stories if not PREVIEW.search(x["title"])), stories[0])
        bullets.append(f'本周最受关注：<a href="{esc(top["link"])}" target="_blank" rel="noopener" style="color:#111;font-weight:700;">'
                       f'{esc(top["title"])}</a>')
    summary = '<ul style="margin:0;padding-left:20px;">' + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>"

    # ---- 走势 ----
    days = sorted({d for r in idx if r["ok"] for d, _ in r["daily"]})
    head = ["品种", "上周五", "最新", "本周"] + [f"周{WEEKDAY[d.weekday()]} {d:%m-%d}" for d in days]
    def bp(v):
        n = round(v * 100)
        return f'<span style="color:{GREEN if n > 0 else RED if n < 0 else GREY};">{n:+d} 基点</span>' if n else             f'<span style="color:{GREY};">0 基点</span>'
    irows = ""
    for r in idx:
        if not r["ok"]:
            irows += f'<tr><td {TD}>{esc(r["name"])}</td><td {TDN} colspan="{len(head) - 1}" style="color:#aaa;">没有取到数据</td></tr>'
            continue
        is_rate = r["sym"] == "^TNX"
        chg = bp(r["diff"]) if is_rate else pct(r["chg"] * 100)
        dmap = dict(r["daily"])
        cells = "".join(f"<td {TDN}>{(bp(dmap[d]) if is_rate else pct(dmap[d] * 100)) if d in dmap else '—'}</td>" for d in days)
        unit = "%" if is_rate else ""
        irows += (f'<tr><td {TD}>{tv_a(r["sym"], r["name"])}</td><td {TDN}>{r["base"]:,.2f}{unit}</td>'
                  f'<td {TDN}>{r["last"]:,.2f}{unit}</td><td {TDN}><b>{chg}</b></td>{cells}</tr>')
    idx_html = table(head, irows)

    # ---- 经济数据 ----
    if cal:
        crow = ""
        for e in cal:
            zh = nd.CAL_ZH.get(e["title"], "")
            is_past = e["when"] <= now_utc
            st = (f'<span style="color:{GREEN};">已公布</span>' if is_past else f'<span style="color:{AMBER};">待公布</span>')
            hits = match_news(e, raw) if is_past else []
            res = ("<br>".join(f'<a href="{esc(h["link"])}" target="_blank" rel="noopener" style="color:#111;">{esc(h["title"])}</a>'
                               for h in hits)
                   if hits else ('<span style="color:#aaa;">公布后的新闻里还没有找到相关标题</span>' if is_past else ""))
            crow += (f'<tr><td {TDN}>{to_et_str(e["when"])}</td><td {TDN}>{st}</td>'
                     f'<td {TD}><b>{esc(zh or e["title"])}</b>' + (f'<br><span style="color:#999;font-size:11px;">{esc(e["title"])}</span>' if zh else "")
                     + f'</td><td {TDN}>{esc(e.get("forecast") or "—")}</td><td {TDN}>{esc(e.get("previous") or "—")}</td>'
                     f'<td {TD} style="font-size:12px;">{res}</td></tr>')
        cal_html = table(("时间（美东）", "状态", "数据", "预期", "前值", "结果相关新闻"), crow)
    else:
        cal_html = '<p style="color:#888;">没有取到本周经济日历。</p>'

    # ---- 财报 ----
    def er_row(r, is_done):
        nm = f'{tv_a_ex(r)}<br><span style="color:#888;font-size:11px;">{esc((r.get("name") or "")[:26])}</span>'
        if is_done:
            f = lambda k: pct(float(r[k])) if r.get(k) not in (None, "") else pct(None)
            return (f'<tr><td {TD}>{nm}</td><td {TDN}>{esc(r["sec"])}</td><td {TDN}>{r["release"][5:]}</td>'
                    f'<td {TDN}>{f("eps_beat")}</td><td {TDN}>{f("rev_beat")}</td><td {TDN}>{f("rev_yoy")}</td><td {TDN}>{f("react")}</td></tr>')
        return f'<tr><td {TD}>{nm}</td><td {TDN}>{esc(r["sec"])}</td><td {TDN}>{r["next_er"][5:]}</td></tr>'
    er_html = (table(("公司", "板块", "公布日", "EPS 对比预期", "营收对比预期", "营收同比", "股价反应"), "".join(er_row(r, True) for r in done))
               if done else '<p style="color:#888;">本周还没有各板块前 10 大公司公布业绩。</p>')
    if todo and not weekend:
        er_html += ('<p style="margin:10px 0 4px;"><b>本周还没公布：</b></p>'
                    + table(("公司", "板块", "预计公布日"), "".join(er_row(r, False) for r in todo)))
    er_html += f'<p style="color:#888;font-size:11px;">范围：各板块市值前 10 大（共 110 家），数据来自 {ev_date or "—"} 的业绩与估值分页，详细分析在那一页。</p>'

    # ---- 新闻 ----
    def li(s):
        dtxt = "、".join(f"周{WEEKDAY[d.weekday()]}" for d in s["days"])
        badge = (f'<span style="background:#E8F5E9;color:{GREEN};font-size:11px;padding:1px 6px;border-radius:8px;">'
                 f'{len(s["sources"])} 家媒体</span>')
        more = (f' <span style="background:#FFF4E0;color:{AMBER};font-size:11px;padding:1px 6px;border-radius:8px;">连续 {len(s["days"])} 天</span>'
                if len(s["days"]) >= 2 else "")
        return (f'<li style="margin:0 0 9px;"><span style="color:{BLUE};font-size:12px;font-weight:600;">[{esc(s["topic"])}]</span> '
                f'<a href="{esc(s["link"])}" target="_blank" rel="noopener" style="color:#111;font-weight:600;text-decoration:none;">'
                f'{esc(s["title"])}</a> {badge}{more}<div style="color:#888;font-size:11px;">{dtxt} · {esc("、".join(s["sources"][:5]))}</div></li>')
    news_html = ('<ol style="margin:0;padding-left:22px;">' + "".join(li(s) for s in stories[:10]) + "</ol>") if stories else \
        '<p style="color:#888;">本周还没有新闻记录。</p>'
    news_note = f'（合并本周 {n_days} 份每日新闻）' if n_days else ""

    sub = (f'<div style="font-size:13px;color:#555;">{"周末更新：这一周的完整回顾" if weekend else "每个交易日收盘后更新，一周内的数据、财报和新闻会逐日累加"}</div>')
    body = (h3("一眼看懂", GREEN) + summary
            + h3("本周走势（对比上周五收盘）") + idx_html
            + h3("重要经济数据（高影响力）") + cal_html
            + h3("大公司财报") + er_html
            + h3("本周最重大的新闻" + news_note) + news_html
            + h3("数据核对", GREY) + check_list_html(checks)
            + '<p style="color:#888;font-size:11px;margin-top:14px;">规则自动整理，不用 AI。走势来自 Yahoo Finance；经济日历来自 Forex Factory'
              '（免费数据没有实际值，「结果相关新闻」是本周新闻里关键词相符的标题，请点开确认）；新闻按重要性、可信媒体数量和连续报道天数排序。'
              '仅供学习，不构成投资建议。</p>')
    return card(esc(title), body, accent=AMBER, bg="#FFF8EC", sub=sub)


def to_et_str(t):
    e = nd.to_et(t)
    return f"周{WEEKDAY[e.weekday()]} {e:%m-%d %H:%M}"


def tv_a_ex(r):
    ex = r.get("exchange") or ""
    url = "https://www.tradingview.com/chart/?symbol=" + (f"{ex}:{r['sym']}" if ex else r["sym"])
    return (f'<a href="{esc(url)}" target="_blank" rel="noopener" style="color:#1565C0;text-decoration:none;font-weight:700;">'
            f'{esc(r["sym"])} <span style="font-size:11px;">📈</span></a>')


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(NEWS_DIR, exist_ok=True)
    now, et = et_now()
    weekend = MODE == "weekend" if MODE else et.weekday() >= 5
    today = et.date()
    monday, friday = week_bounds(today, weekend)
    last_day = min(today, friday)

    raw = load_week_news(monday, today)
    n_days = len({s["day"] for s in raw})
    stories = merge_week(raw)
    idx = index_week(monday, last_day)
    cal, cal_ok = week_calendar(monday, weekend, et)
    done, todo, ev_date = week_earnings(monday, friday, today)
    prune()

    got = [r for r in idx if r["ok"]]
    try:
        tv = {x["d"][0]: x["d"][1] for x in tv_scan({"symbols": {"tickers": ["AMEX:SPY", "NASDAQ:QQQ", "AMEX:IWM", "AMEX:DIA"]},
                                                    "columns": ["name", "close"]})}
        cmp = [r for r in got if r["sym"] in tv]
        bad = [r["sym"] for r in cmp if abs(tv[r["sym"]] / r["last"] - 1) > 0.015]
        tv_chk = dict(name="收盘价核对（Yahoo vs TradingView）", ok=bool(cmp) and not bad, critical=False,
                      detail=f"{len(cmp) - len(bad)}/{len(cmp)} 一致" + (f"；不一致：{'、'.join(bad)}" if bad else ""))
    except Exception as ex:
        tv_chk = dict(name="收盘价核对（Yahoo vs TradingView）", ok=False, critical=False, detail=f"无法连接（{type(ex).__name__}）")
    stale = [r["sym"] for r in got if (last_day - r["last_d"]).days > 3]
    checks = [tv_chk,
        dict(name="本周走势", ok=len(got) == len(idx) and not stale, critical=False,
             detail=f"{len(got)}/{len(idx)} 个品种取到数据" + (f"；数据偏旧：{'、'.join(stale)}" if stale else "")),
        dict(name="本周经济日历", ok=cal_ok, critical=False, detail=f"{len(cal)} 项高影响力数据" if cal_ok else "没有取到"),
        dict(name="本周新闻累计", ok=n_days >= 1, critical=False,
             detail=f"{n_days} 份每日新闻，合并后 {len(stories)} 个事件"),
        dict(name="财报数据", ok=ev_date is not None, critical=False, detail=f"业绩估值 {ev_date}" if ev_date else "没有业绩估值数据"),
    ]
    seen, uniq = set(), []
    for x in raw:
        if x["title"] not in seen and x.get("latest"):
            seen.add(x["title"])
            uniq.append(dict(x, latest=dt.datetime.fromisoformat(x["latest"]), sources=x.get("sources", [])))
    frag = build_html(weekend, monday, friday, et, idx, cal, stories, uniq, done, todo, ev_date, n_days, checks)
    base = os.path.join(NEWS_DIR, f"本周事件_{today}")
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "</head><body style=\"margin:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222;\">"
                + frag + "</body></html>")
    spy = next((r for r in got if r["sym"] == "SPY"), None)
    print(json.dumps({"html": base + ".html", "weekend": weekend, "monday": str(monday), "news_days": n_days,
                      "events": len(cal), "earnings_done": len(done), "earnings_todo": len(todo),
                      "spy_week": round(spy["chg"] * 100, 2) if spy else None, "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
