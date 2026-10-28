"""各板块前 10 大公司：最新季度业绩、前瞻（公司指引 + 分析师预期变化）、两年估值情景（不用 AI）。

  * 公司池：TradingView 市值最大的 600 只美股，按 Yahoo Finance 的 11 个板块分组，每组取市值前 10
  * 业绩：最新季度 EPS / 营收 实际 vs 预期、营收按年增长、业绩前后两天的股价反应
  * 前瞻：① 公司 8-K 业绩新闻稿（SEC EDGAR，附件 99.1）里提到展望 / 指引的原句（英文原文，不改写）
          ② 分析师对下季、今年、明年 EPS 预期在过去 30 / 90 天的修正，以及上调 / 下调人数
  * 两年估值情景：两年后的预估年度 EPS × 过去几年的市盈率（低 / 中位 / 高）= 悲观 / 基准 / 乐观价位
      - 两年后 EPS：分析师「明年度」EPS，若该财年在两年内结束，再按分析师明年增长率（限制在 −20%～+40%）外推到满两年
      - 市盈率：每个财年末的股价 ÷ 当年摊薄 EPS，加上现在的滚动市盈率；GAAP 与调整后 EPS 的差异按最近四季比例换算
      - 只在 EPS 为正、数据齐全时计算；这是情景估算，不是预测
  * 核对：EPS、营收、股价分别和 TradingView 对照，不一致的标出 ⚠

用法：python earnings_valuation.py [输出目录]
输出：<输出目录>/业绩估值/YYYY-MM-DD.html、.json；缓存 <输出目录>/业绩估值/cache/
仅供学习，不构成投资建议。
"""
import datetime as dt
import html
import json
import os
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (AMBER, BLUE, GREEN, GREY, RED, card, check_list_html, esc, h3, raw, sec_json, sec_text, tv_scan,
                    yahoo_chart, yahoo_summary, yahoo_timeseries)

# 这一页有 110 家公司，用 CSS class 代替重复的内联样式，网页小很多
TD, TDN = 'class="ev-td"', 'class="ev-td ev-n"'
EV_CSS = ("<style>.ev-td{padding:6px 8px;border-bottom:1px solid #eee;vertical-align:top}.ev-n{white-space:nowrap}"
          ".ev-th{padding:6px 8px;background:#f5f5f5;text-align:left;font-weight:600;border-bottom:1px solid #ddd;white-space:nowrap}"
          ".ev-t{width:100%;border-collapse:collapse;font-size:13px}.ev-s{font-size:11px;color:#888}.ev-up{color:#2E7D32}"
          ".ev-dn{color:#C62828}.ev-na{color:#aaa}.ev-d{margin:0 0 8px;border:1px solid #eee;border-radius:6px;padding:6px 10px}"
          ".ev-d summary{cursor:pointer}.ev-m{font-size:12px;color:#555;margin-top:6px}</style>")


def table(head, rows_html):
    hd = "".join(f'<th class="ev-th">{x}</th>' for x in head)
    return f'<div style="overflow-x:auto;"><table class="ev-t"><tr>{hd}</tr>{rows_html}</table></div>'


def pct(x, d=1, signed=True):
    if x is None:
        return '<span class="ev-na">—</span>'
    c = "ev-up" if x > 0 else "ev-dn" if x < 0 else "ev-na"
    return f'<span class="{c}">{x:+.{d}f}%</span>' if signed else f"{x:.{d}f}%"

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV_DIR = os.path.join(OUT_DIR, "业绩估值")
CACHE = os.path.join(EV_DIR, "cache")
SECTOR_MAP = os.path.join(CACHE, "sector_map.json")
EDGAR_CACHE = os.path.join(CACHE, "edgar_guidance.json")
TOP_N, POOL = 10, 600
SECTOR_ZH = {"Technology": "科技", "Financial Services": "金融", "Healthcare": "医疗保健", "Consumer Cyclical": "可选消费",
             "Communication Services": "通讯服务", "Industrials": "工业", "Consumer Defensive": "必需消费", "Energy": "能源",
             "Utilities": "公用事业", "Real Estate": "房地产", "Basic Materials": "原材料"}
GUIDE_RX = re.compile(r"\b(expects?|expected to|anticipates?|outlook|guidance|guides?|guided|forecasts?|projects?|projected|"
                      r"reaffirm\w*|raising|raises?|lowers?|narrows?|now sees|target(s|ing)?|will (be|grow|deliver|increase|decline))\b", re.I)
FUTURE_RX = re.compile(r"\b(expects?|expected to|anticipates?|outlook|guidance|guides?|now sees|forecasts?|projects?|will)\b", re.I)
NUM_RX = re.compile(r"\$\s?\d|\d+(\.\d+)?\s?(%|percent|billion|million)")
TODAY = dt.date.today()


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=0)


TV_COLS = ["name", "description", "close", "market_cap_basic", "earnings_per_share_fq", "earnings_per_share_forecast_fq",
           "revenue_fq", "revenue_forecast_fq", "earnings_release_date", "earnings_release_next_date", "price_target_average",
           "exchange"]


def universe():
    body = {"filter": [{"left": "type", "operation": "equal", "right": "stock"},
                       {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
                       {"left": "is_primary", "operation": "equal", "right": True}],
            "columns": TV_COLS, "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}, "range": [0, POOL]}
    rows = [dict(zip(TV_COLS, r["d"])) for r in tv_scan(body)]
    return [r for r in rows if r["market_cap_basic"]]


def sectors(rows):
    smap = load(SECTOR_MAP, {})
    stale = [r["name"] for r in rows
             if r["name"] not in smap or (TODAY - dt.date.fromisoformat(smap[r["name"]][2])).days > 45]

    def one(sym):
        try:
            p = yahoo_summary(sym.replace(".", "-"), ["assetProfile"]).get("assetProfile", {})
            return sym, [p.get("sector") or "", p.get("industry") or "", str(TODAY)]
        except Exception:
            return sym, None
    with ThreadPoolExecutor(8) as ex:
        for sym, v in ex.map(one, stale):
            if v:
                smap[sym] = v
    save(SECTOR_MAP, smap)
    return smap


def split_factor(splits, ts):
    """该日期之后发生的拆股累计倍数（EPS 要除以它，才能和已调整的股价对应）。"""
    f = 1.0
    for t, ratio in splits:
        if t > ts:
            f *= ratio
    return f


def eps_history_pe(price_bars, annual_eps, splits, ref_pe):
    """每个财年末的市盈率（GAAP 摊薄 EPS）。

    Yahoo 的历史 EPS 有时已按拆股调整、有时没有；K 线是已调整的。所以每个点同时算「调整」与「不调整」两种，
    取在 4～150 倍之间、且和现在市盈率（ref_pe）最接近的一个。"""
    import math
    out = []
    for date_s, eps in annual_eps:
        if not eps or eps <= 0:
            continue
        ts = dt.datetime.fromisoformat(date_s).replace(tzinfo=dt.timezone.utc).timestamp()
        prior = [b for b in price_bars if b["t"] <= ts + 86400 * 3]
        if not prior:
            continue
        f = split_factor(splits, ts + 86400 * 45)
        cands = [prior[-1]["c"] / e for e in {eps, eps / f}]
        cands = [pe for pe in cands if 4 <= pe <= 150]
        if cands:
            out.append((date_s, min(cands, key=lambda pe: abs(math.log(pe / ref_pe))) if ref_pe else cands[0]))
    return out


def reaction(daily, release_ts):
    """业绩后的股价反应。开盘前公布（美东 9:30 前）= 当天收盘 vs 前一天收盘；收盘后公布 = 下一天收盘 vs 当天收盘。"""
    if not release_ts or not daily:
        return None
    from news_digest import et_offset
    t = dt.datetime.fromtimestamp(release_ts, dt.timezone.utc)
    t = t.astimezone(et_offset(t))
    d = t.date()
    pre_market = (t.hour, t.minute) < (9, 30)
    days = [(dt.datetime.fromtimestamp(b["t"], dt.timezone.utc).date(), b["c"]) for b in daily]
    before = [c for dd, c in days if (dd < d if pre_market else dd <= d)]
    after = [c for dd, c in days if (dd >= d if pre_market else dd > d)]
    if not before or not after:
        return None
    return (after[0] / before[-1] - 1) * 100


def guidance(sym, release_ts, ciks, cache):
    """找出业绩日附近的 8-K（2.02 项）附件 99.1，抽出提到展望 / 指引的句子（原文）。"""
    cik = ciks.get(sym.replace(".", "-")) or ciks.get(sym)
    if not cik or not release_ts:
        return None
    rel = dt.datetime.fromtimestamp(release_ts, dt.timezone.utc).date()
    key = f"{sym}:{rel}"
    if key in cache:
        return cache[key]
    res = None
    try:
        sub = sec_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")["filings"]["recent"]
        for i, form in enumerate(sub["form"][:200]):
            if form != "8-K" or "2.02" not in (sub["items"][i] or ""):
                continue
            fd = dt.date.fromisoformat(sub["filingDate"][i])
            if abs((fd - rel).days) > 4:
                continue
            acc = sub["accessionNumber"][i].replace("-", "")
            idx = sec_json(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/index.json")["directory"]["item"]
            primary = sub["primaryDocument"][i]
            htms = [x["name"] for x in idx if x["name"].lower().endswith((".htm", ".html")) and x["name"] != primary
                    and not re.match(r"R\d+\.htm|.*index", x["name"], re.I)]
            ex = [n for n in htms if re.search(r"ex-?99|ex99|exhibit|ex-?9\.|ex-9|earnings|release|press", n, re.I)]
            if not ex:                       # 名字看不出来时，看 8-K 正文里链接到哪个附件
                body = sec_text(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{primary}")
                links = [h.split("/")[-1] for h in re.findall(r'href="([^"#]+\.htm)"', body, re.I)]
                ex = [n for n in links if n in htms] or htms[:1]
            if not ex:
                break
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{ex[0]}"
            text = re.sub(r"<[^>]+>", " ", sec_text(url))
            text = html.unescape(text).replace(" ", " ")
            text = re.sub(r"\s+", " ", text)
            sents = [x for part in re.split(r"\s*[•◦▪●■]\s*", text)
                     for x in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])", part)]
            scored = []
            for k, s in enumerate(sents):
                s = s.strip()
                digits = sum(ch.isdigit() for ch in s) / max(1, len(s))
                if 40 <= len(s) <= 380 and FUTURE_RX.search(s) and NUM_RX.search(s) and digits < 0.18 and not re.search(
                        r"forward-looking statements|safe harbor|undue reliance|risks and uncertainties|exhibit 99|ex-99|^assumes|^\d+ |current prior|unavailable information|reconcil|non-gaap measure", s, re.I):
                    scored.append((len(GUIDE_RX.findall(s)) + (3 if re.search(r"outlook|guidance|now sees|raising|reaffirm", s, re.I) else 0)
                                   + (1 if re.search(r"20\d\d|next quarter|fourth quarter|full[- ]year", s, re.I) else 0), k, s))
            top = sorted(sorted(scored, key=lambda x: -x[0])[:3], key=lambda x: x[1])
            res = dict(url=url, filed=str(fd), quotes=[s for _, _, s in top])
            break
    except Exception:
        res = None
    if res is not None:
        cache[key] = res
    return res


def analyse(tv, sector, industry, ciks, gcache):
    sym = tv["name"]
    ys = sym.replace(".", "-")
    try:
        s = yahoo_summary(ys, ["earningsHistory", "earningsTrend", "financialData", "calendarEvents", "price"])
        ts = yahoo_timeseries(ys, ["annualDilutedEPS", "quarterlyDilutedEPS", "quarterlyTotalRevenue"])
        weekly, wmeta = yahoo_chart(ys, "5y", "1wk")
        daily, _ = yahoo_chart(ys, "6mo", "1d")
    except Exception as e:
        return dict(sym=sym, error=str(e)[:120])
    fd = s.get("financialData", {})
    price = daily[-1]["c"] if daily else tv["close"]
    hist = (s.get("earningsHistory") or {}).get("history") or []
    hist = [h for h in hist if raw(h, "epsActual") is not None]
    last = hist[-1] if hist else None
    trend = {t["period"]: t for t in (s.get("earningsTrend") or {}).get("trend", [])}
    q_rev = ts.get("quarterlyTotalRevenue", [])
    q_end = (last or {}).get("quarter", {}).get("fmt")

    def rev_at(date_s, tol=12):
        if not date_s:
            return None
        d0 = dt.date.fromisoformat(date_s)
        for d, v in q_rev:
            if abs((dt.date.fromisoformat(d) - d0).days) <= tol:
                return v
        return None
    rev_last = rev_at(q_end)                                   # Yahoo 同一季度的营收（用来核对）
    year_ago = str(dt.date.fromisoformat(q_end) - dt.timedelta(days=365)) if q_end else None
    base_rev = rev_last or tv["revenue_fq"]
    prev_rev = rev_at(year_ago, 20)
    rev_yoy = (base_rev / prev_rev - 1) * 100 if base_rev and prev_rev else None

    # ---- 最新季度 ----
    eps_a, eps_e = raw(last, "epsActual"), raw(last, "epsEstimate")
    eps_beat = (eps_a - eps_e) / abs(eps_e) * 100 if eps_a is not None and eps_e else None
    rev_a, rev_e = tv["revenue_fq"], tv["revenue_forecast_fq"]
    rev_beat = (rev_a / rev_e - 1) * 100 if rev_a and rev_e else None
    react = reaction(daily, tv["earnings_release_date"])

    # ---- 前瞻：分析师修正 ----
    def revision(period):
        t = trend.get(period)
        if not t:
            return None
        cur, d30, d90 = raw(t, "epsTrend", "current"), raw(t, "epsTrend", "30daysAgo"), raw(t, "epsTrend", "90daysAgo")
        return dict(period=period, end=t.get("endDate"), eps=raw(t, "earningsEstimate", "avg"),
                    growth=(raw(t, "growth") or 0) * 100 if raw(t, "growth") is not None else None,
                    rev=raw(t, "revenueEstimate", "avg"), n=raw(t, "earningsEstimate", "numberOfAnalysts"),
                    chg30=(cur / d30 - 1) * 100 if cur and d30 else None, chg90=(cur / d90 - 1) * 100 if cur and d90 else None,
                    up30=raw(t, "epsRevisions", "upLast30days"), down30=raw(t, "epsRevisions", "downLast30days"))
    rev_q, rev_y0, rev_y1 = revision("0q"), revision("0y"), revision("+1y")

    # ---- 两年估值情景 ----
    val, why = None, ""
    annual = ts.get("annualDilutedEPS", [])
    splits = wmeta.get("splits", [])
    q_raw = ts.get("quarterlyDilutedEPS", [])[-4:]
    gaap_ttm = None
    if len(q_raw) == 4:
        plain = sum(v for _, v in q_raw)
        adj = sum(v / split_factor(splits, dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc).timestamp() + 86400 * 30)
                  for d, v in q_raw)
        fwd = price / raw(trend.get("+1y", {}), "earningsEstimate", "avg") if raw(trend.get("+1y", {}), "earningsEstimate", "avg") else None
        cands = [x for x in {plain, adj} if x > 0 and 4 <= price / x <= 400]
        gaap_ttm = (min(cands, key=lambda x: abs(price / x - fwd)) if fwd else cands[0]) if cands else (plain if plain else None)
    adj_ttm = sum(raw(h, "epsActual") for h in hist[-4:]) if len(hist) >= 4 else None
    if rev_y1 and rev_y1["eps"] and rev_y1["eps"] > 0 and rev_y0 and rev_y0["eps"] and rev_y0["eps"] > 0 and rev_y1["end"]:
        t1 = (dt.date.fromisoformat(rev_y1["end"]) - TODAY).days / 365.25
        g = rev_y1["growth"] / 100 if rev_y1["growth"] is not None else rev_y1["eps"] / rev_y0["eps"] - 1
        g = max(-0.2, min(0.4, g))
        ext = max(0.0, 2 - t1)
        eps2 = rev_y1["eps"] * (1 + g) ** ext
        ratio = gaap_ttm / adj_ttm if gaap_ttm and adj_ttm and gaap_ttm > 0 and adj_ttm > 0 else 1.0
        ratio = max(0.5, min(1.5, ratio))
        cur_pe = price / gaap_ttm * ratio if gaap_ttm and gaap_ttm > 0 else None
        fwd_pe = price / rev_y1["eps"]
        hist_pts = [(d, pe * ratio) for d, pe in eps_history_pe(weekly, annual, splits, (cur_pe or fwd_pe) / ratio)]
        pts = hist_pts + ([("现在(滚动)", cur_pe)] if cur_pe else []) + [("现在(明年度预期)", fwd_pe)]
        pts = [(d, pe) for d, pe in pts if 4 <= pe <= 150]
        if cur_pe and cur_pe > 150:
            why = f"当前滚动市盈率 {cur_pe:.0f} 倍，远高于历史区间，这个方法不适用"
        elif len(pts) >= 3:
            pes = sorted(pe for _, pe in pts)
            lo, mid, hi = pes[0], statistics.median(pes), pes[-1]
            if hi / lo > 3:                      # 极端值太多时改用 25% / 75% 分位
                q = statistics.quantiles(pes, n=4)
                lo, hi = q[0], q[2]
            if cur_pe:
                mid = min(mid, max(cur_pe, lo))  # 基准：市盈率不高于今天（不假设估值扩张）
            prices = [eps2 * m for m in (lo, mid, hi)]
            val = dict(eps2=eps2, g=g * 100, ext=ext, t1=t1, ratio=ratio, pts=pts, pe=(lo, mid, hi), prices=prices,
                       up=[(p / price - 1) * 100 for p in prices], cagr=((prices[1] / price) ** 0.5 - 1) * 100,
                       eps_mult=eps2 / adj_ttm if adj_ttm and adj_ttm > 0 else None)
        else:
            why = why or "历年市盈率数据不足"
    else:
        why = "亏损或没有分析师 EPS 预期" if not (rev_y1 and rev_y1["eps"]) or rev_y1["eps"] <= 0 else "预期数据不全"

    # ---- 核对 ----
    flags, notes = [], []
    tv_eps = tv["earnings_per_share_fq"]
    if eps_a is not None and tv_eps is not None and abs(eps_a - tv_eps) > max(0.03, abs(tv_eps) * 0.04):
        flags.append(f"EPS：Yahoo(调整后) {eps_a:.2f} / TradingView {tv_eps:.2f}，可能是 GAAP 与调整后口径不同")
    tol = 0.08 if sector in ("Financial Services", "Real Estate") else 0.03
    if rev_last and rev_a:
        if abs(rev_last / rev_a - 1) > tol:
            flags.append(f"营收：Yahoo {rev_last/1e9:.2f}B / TradingView {rev_a/1e9:.2f}B")
    elif rev_a:
        notes.append("Yahoo 还没有这一季的营收，营收只用 TradingView 一个来源")
    if tv["close"] and abs(price / tv["close"] - 1) > 0.015:
        flags.append(f"股价：Yahoo {price:.2f} / TradingView {tv['close']:.2f}")
    if val and (val["up"][1] > 150 or val["up"][1] < -60):
        notes.append(f"估值情景偏离现价很大：主要因为分析师预期两年后 EPS 是现在的 {val['eps_mult']:.1f} 倍" if val.get("eps_mult")
                     else "估值情景偏离现价很大，请看计算明细")
    nxt = raw(s, "calendarEvents", "earnings", "earningsDate")
    next_er = tv["earnings_release_next_date"]
    rel = tv["earnings_release_date"]
    days_since = (TODAY - dt.datetime.fromtimestamp(rel, dt.timezone.utc).date()).days if rel else None
    guide = guidance(sym, rel, ciks, gcache) if days_since is not None and days_since <= 120 else None
    return dict(sym=sym, name=(s.get("price", {}).get("longName") or tv["description"] or "")[:40], sector=sector,
                industry=industry, mcap=tv["market_cap_basic"], price=price, quarter=(last or {}).get("quarter", {}).get("fmt"),
                eps_a=eps_a, eps_e=eps_e, eps_beat=eps_beat, rev_a=rev_a, rev_e=rev_e, rev_beat=rev_beat, rev_yoy=rev_yoy,
                react=react, release=str(dt.datetime.fromtimestamp(rel, dt.timezone.utc).date()) if rel else None,
                days_since=days_since, next_er=str(dt.datetime.fromtimestamp(next_er, dt.timezone.utc).date()) if next_er else None,
                rev_q=rev_q, rev_y0=rev_y0, rev_y1=rev_y1, target=raw(fd, "targetMeanPrice"), target_lo=raw(fd, "targetLowPrice"),
                target_hi=raw(fd, "targetHighPrice"), n_analysts=raw(fd, "numberOfAnalystOpinions"),
                rec=fd.get("recommendationKey"), val=val, why=why, flags=flags, notes=notes, guide=guide)


def money(x):
    if x is None:
        return "—"
    a = abs(x)
    return f"{x/1e12:.2f}T" if a >= 1e12 else f"{x/1e9:.1f}B" if a >= 1e9 else f"{x/1e6:.0f}M"


def summary_zh(r):
    """按规则拼出一句中文业绩总结（数字全部来自数据源）。"""
    parts = []
    if r["eps_a"] is not None:
        s = f"每股盈利 {r['eps_a']:.2f} 美元"
        if r["eps_beat"] is not None:
            s += f"，{'好于' if r['eps_beat'] >= 0 else '差于'}预期 {r['eps_e']:.2f}（{r['eps_beat']:+.1f}%）"
        parts.append(s)
    if r["rev_a"]:
        s = f"营收 {money(r['rev_a'])}"
        if r["rev_beat"] is not None:
            s += f"，{'高于' if r['rev_beat'] >= 0 else '低于'}预期 {r['rev_beat']:+.1f}%"
        if r["rev_yoy"] is not None:
            s += f"，按年 {r['rev_yoy']:+.1f}%"
        parts.append(s)
    if r["react"] is not None:
        parts.append(f"业绩后股价 {r['react']:+.1f}%")
    q = r["rev_q"]
    if q and q["chg30"] is not None:
        d = "上调" if q["chg30"] > 0.5 else "下调" if q["chg30"] < -0.5 else "大致不变"
        parts.append(f"分析师对下季 EPS 预期近 30 天{d}（{q['chg30']:+.1f}%，上调 {q['up30'] or 0} 人 / 下调 {q['down30'] or 0} 人）")
    y1 = r["rev_y1"]
    if y1 and y1["eps"]:
        parts.append(f"明年度 EPS 预期 {y1['eps']:.2f}（增长 {y1['growth']:+.0f}%）" if y1["growth"] is not None else f"明年度 EPS 预期 {y1['eps']:.2f}")
    return "；".join(parts) + "。" if parts else "没有取到业绩数据。"


def tone(r):
    """业绩 + 前瞻的综合判断（规则）。"""
    pts = 0
    pts += 1 if (r["eps_beat"] or 0) > 2 else -1 if (r["eps_beat"] or 0) < -2 else 0
    pts += 1 if (r["rev_beat"] or 0) > 1 else -1 if (r["rev_beat"] or 0) < -1 else 0
    q = r["rev_q"] or {}
    y = r["rev_y1"] or {}
    pts += 1 if (q.get("chg30") or 0) > 1 or (y.get("chg30") or 0) > 1 else -1 if (q.get("chg30") or 0) < -1 or (y.get("chg30") or 0) < -1 else 0
    pts += 1 if (r["react"] or 0) > 3 else -1 if (r["react"] or 0) < -3 else 0
    if pts >= 2:
        return "偏强", GREEN
    if pts <= -2:
        return "偏弱", RED
    return "中性", AMBER


def company_rows(rs):
    body = ""
    for r in rs:
        if r.get("error"):
            body += f'<tr><td {TD}><b>{esc(r["sym"])}</b></td><td {TD} colspan="8" style="color:#aaa;">没有取到数据</td></tr>'
            continue
        t, tc = tone(r)
        v = r["val"]
        tgt = (f'{r["target"]:.0f} <span style="font-size:11px;">{pct((r["target"]/r["price"]-1)*100, 0)}</span>'
               if r["target"] and r["price"] else "—")
        valtxt = (f'{v["prices"][0]:.0f} / <b>{v["prices"][1]:.0f}</b> / {v["prices"][2]:.0f}<br>'
                  f'<span style="font-size:11px;">{pct(v["up"][0], 0)} / {pct(v["up"][1], 0)} / {pct(v["up"][2], 0)}</span>'
                  if v else f'<span style="color:#aaa;font-size:12px;">{esc(r["why"])}</span>')
        chk = (f'<span style="color:{GREEN};">✔</span>' if not r["flags"] else
               f'<span style="color:{AMBER};" title="{esc("；".join(r["flags"]))}">⚠ {len(r["flags"])}</span>')
        er = r["next_er"] or "—"
        soon = r["next_er"] and 0 <= (dt.date.fromisoformat(r["next_er"]) - TODAY).days <= 14
        body += (f'<tr><td {TD}><b>{esc(r["sym"])}</b><br><span class="ev-s">{esc(r["name"][:24])}</span></td>'
                 f'<td {TDN}>{money(r["mcap"])}<br><span class="ev-s">${r["price"]:.2f}</span></td>'
                 f'<td {TDN}>{esc(r["quarter"] or "—")}<br><span style="font-size:11px;">EPS {pct(r["eps_beat"])} · 营收 {pct(r["rev_beat"])}</span></td>'
                 f'<td {TDN}>{pct(r["rev_yoy"])}</td><td {TDN}>{pct(r["react"])}</td>'
                 f'<td {TDN}><b style="color:{tc};">{t}</b></td><td {TDN}>{tgt}</td><td {TDN}>{valtxt}</td>'
                 f'<td {TDN}>{chk}<br><span style="font-size:11px;{"color:" + RED + ";font-weight:600;" if soon else "color:#888;"}">{er}</span></td></tr>')
    return table(("公司", "市值 / 股价", "最新季度 vs 预期", "营收按年", "业绩后股价", "综合", "分析师目标价(12个月)",
                  "两年估值 悲观 / 基准 / 乐观", "核对 · 下次业绩"), body)


def detail(r):
    if r.get("error"):
        return ""
    v = r["val"]
    g = r["guide"]
    quotes = ""
    if g and g["quotes"]:
        quotes = ("<div style='margin-top:6px;'><b>公司展望原文</b>（8-K 业绩新闻稿，{}）：<ul style='margin:4px 0;padding-left:20px;'>".format(esc(g["filed"]))
                  + "".join(f'<li style="color:#333;font-size:12px;">“{esc(q)}”</li>' for q in g["quotes"])
                  + f'</ul><a href="{esc(g["url"])}" target="_blank" rel="noopener" style="font-size:12px;">打开新闻稿原文</a></div>')
    elif g:
        quotes = (f"<div style='margin-top:6px;font-size:12px;color:#888;'>新闻稿里没有找到带数字的展望句子。"
                  f"<a href='{esc(g['url'])}' target='_blank' rel='noopener'>打开新闻稿原文</a></div>")
    else:
        quotes = "<div style='margin-top:6px;font-size:12px;color:#888;'>没有找到对应的 8-K 业绩新闻稿（外国公司或业绩超过 120 天）。</div>"
    rev_lines = ""
    for lab, q in (("下季", r["rev_q"]), ("今年度", r["rev_y0"]), ("明年度", r["rev_y1"])):
        if q and q["eps"]:
            rev_lines += (f'<tr><td {TDN}>{lab}（至 {esc(q["end"] or "")}）</td><td {TDN}>{q["eps"]:.2f}</td>'
                          f'<td {TDN}>{pct(q["growth"], 0)}</td><td {TDN}>{money(q["rev"])}</td><td {TDN}>{pct(q["chg30"])}</td>'
                          f'<td {TDN}>{pct(q["chg90"])}</td><td {TDN}>{q["up30"] or 0} / {q["down30"] or 0}</td><td {TDN}>{q["n"] or "—"}</td></tr>')
    rev_tbl = table(("期间", "EPS 预期", "增长", "营收预期", "30 天修正", "90 天修正", "上调/下调(30天)", "分析师数"), rev_lines) if rev_lines else ""
    calc = ""
    if v:
        pts = "、".join(f"{esc(str(d)[:7] if str(d)[:2] == '20' else str(d))} {pe:.1f}x" for d, pe in v["pts"])
        calc = (f'<div class="ev-m"><b>估值计算</b>：两年后 EPS ≈ 明年度预期 {r["rev_y1"]["eps"]:.2f}'
                + (f' × (1{v["g"]:+.0f}%)^{v["ext"]:.1f}' if v["ext"] > 0.05 else "") + f' = <b>{v["eps2"]:.2f}</b>；'
                f'市盈率点（已按调整后/GAAP 比例 {v["ratio"]:.2f} 换算）：{pts} → 低 {v["pe"][0]:.1f}x / 中位 {v["pe"][1]:.1f}x / 高 {v["pe"][2]:.1f}x；'
                f'基准情景年化 {v["cagr"]:+.1f}%。</div>')
    flags = (f'<div style="font-size:12px;color:{AMBER};margin-top:6px;">⚠ 数据来源不一致：{esc("；".join(r["flags"]))}</div>' if r["flags"] else
             f'<div style="font-size:12px;color:{GREEN};margin-top:6px;">✔ EPS、营收、股价与 TradingView 一致</div>')
    flags += "".join(f'<div style="font-size:12px;color:#777;margin-top:2px;">ⓘ {esc(n)}</div>' for n in r.get("notes", []))
    tg = (f'分析师 {r["n_analysts"]} 人，评级 {esc(r["rec"] or "—")}，目标价 {r["target_lo"] or 0:.0f}–{r["target_hi"] or 0:.0f}（平均 {r["target"]:.0f}）'
          if r["target"] else "")
    return (f'<details class="ev-d">'
            f'<summary><b>{esc(r["sym"])}</b> {esc(r["name"][:30])} — {esc(summary_zh(r))}</summary>'
            f'<div class="ev-m">业绩日 {esc(r["release"] or "—")} · 行业 {esc(r["industry"])} · {tg}</div>'
            f'{quotes}<div style="margin-top:8px;">{rev_tbl}</div>{calc}{flags}</details>')


def build_html(groups, recent, upcoming, checks):
    n = sum(len(v) for v in groups.values())
    body = ""
    if recent:
        body += h3("最近 14 天公布业绩", GREEN) + company_rows(recent) + "".join(detail(r) for r in recent)
    if upcoming:
        rows = "".join(f'<li><b>{esc(r["sym"])}</b> {esc(r["name"][:28])} · {esc(SECTOR_ZH.get(r["sector"], r["sector"]))} · '
                       f'<span style="color:{RED};">{esc(r["next_er"])}</span></li>' for r in upcoming)
        body += h3("未来 14 天将公布业绩", AMBER) + f'<ul style="margin:0;padding-left:20px;">{rows}</ul>'
    for sec, rs in groups.items():
        body += (f'<details style="margin:14px 0;" {"open" if sec == "Technology" else ""}><summary style="cursor:pointer;font-size:16px;'
                 f'font-weight:700;color:{BLUE};">{esc(SECTOR_ZH.get(sec, sec))}（{esc(sec)}）· 前 {len(rs)} 大</summary>'
                 + company_rows(rs) + '<div style="margin-top:8px;">' + "".join(detail(r) for r in rs) + "</div></details>")
    body += h3("数据核对", GREY) + check_list_html(checks)
    body += ('<p style="color:#888;font-size:11px;margin-top:14px;">综合 = 按 EPS / 营收是否超预期、分析师预期修正、业绩后股价反应打分（规则）。'
             '两年估值 = 两年后预估年度 EPS × 过去几年的市盈率（低 / 中位 / 高），只是情景估算，不是预测；EPS 预期会随时修正。'
             '公司展望为 SEC 8-K 新闻稿原文摘录。数据来自 Yahoo Finance、TradingView、SEC EDGAR。仅供学习，不构成投资建议。</p>')
    sub = f'<div style="font-size:13px;color:#555;">11 个板块 · 共 {n} 家公司 · 数据日期 {TODAY}</div>'
    return EV_CSS + card("业绩与两年估值 · 各板块前 10 大", body, accent=BLUE, bg="#EEF4FA", sub=sub)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(CACHE, exist_ok=True)
    t0 = time.time()
    rows = universe()
    smap = sectors(rows)
    groups, seen = {}, set()
    for r in rows:
        firm = re.sub(r"\b(class [a-z]|inc\.?|corp(oration)?\.?|co\.?|plc|ltd\.?|holdings?)\b|[^a-z0-9 ]", "", (r["description"] or "").lower()).strip()
        if firm in seen:
            continue
        seen.add(firm)
        sec = (smap.get(r["name"]) or ["", ""])[0]
        if sec in SECTOR_ZH and len(groups.setdefault(sec, [])) < TOP_N:
            groups[sec].append(r)
    try:
        ciks = {v["ticker"]: v["cik_str"] for v in sec_json("https://www.sec.gov/files/company_tickers.json").values()}
    except Exception:
        ciks = {}
    gcache = load(EDGAR_CACHE, {})
    picks = [(r, sec) for sec, rs in groups.items() for r in rs]
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda x: analyse(x[0], x[1], (smap.get(x[0]["name"]) or ["", ""])[1], ciks, gcache), picks))
    save(EDGAR_CACHE, gcache)
    out = {}
    for (tv, sec), r in zip(picks, res):
        out.setdefault(sec, []).append(r)
    order = sorted(out, key=lambda s: -sum(x.get("mcap") or 0 for x in out[s]))
    out = {s: out[s] for s in order}
    ok = [r for r in res if not r.get("error")]
    recent = sorted([r for r in ok if r["days_since"] is not None and 0 <= r["days_since"] <= 14], key=lambda r: r["days_since"])
    upcoming = sorted([r for r in ok if r["next_er"] and 0 <= (dt.date.fromisoformat(r["next_er"]) - TODAY).days <= 14],
                      key=lambda r: r["next_er"])
    flagged = [r for r in ok if r["flags"]]
    valued = [r for r in ok if r["val"]]
    with_guide = [r for r in ok if r["guide"] and r["guide"]["quotes"]]
    checks = [
        dict(name="板块覆盖", ok=len(out) == 11, critical=len(out) < 8, detail=f"{len(out)}/11 个板块"),
        dict(name="公司数据", ok=len(ok) >= len(res) * 0.95, critical=len(ok) < len(res) * 0.7, detail=f"{len(ok)}/{len(res)} 家取到"),
        dict(name="两源核对（EPS / 营收 / 股价）", ok=len(flagged) <= len(ok) * 0.1, critical=False,
             detail=f"{len(ok) - len(flagged)} 家一致，{len(flagged)} 家有差异（已标 ⚠）"),
        dict(name="两年估值", ok=len(valued) >= len(ok) * 0.7, critical=False, detail=f"{len(valued)} 家可计算"),
        dict(name="公司展望原文", ok=True, critical=False, detail=f"{len(with_guide)} 家从 8-K 新闻稿抽到展望句子"),
    ]
    page = build_html(out, recent, upcoming, checks)
    base = os.path.join(EV_DIR, str(TODAY))
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "</head><body style=\"margin:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222;\">"
                + page + "</body></html>")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({s: [{k: v for k, v in r.items()} for r in rs] for s, rs in out.items()}, f, ensure_ascii=False, default=str)
    print(json.dumps({"html": base + ".html", "companies": len(res), "ok": len(ok), "valued": len(valued),
                      "flagged": [(r["sym"], r["flags"]) for r in flagged][:12], "recent": [r["sym"] for r in recent],
                      "upcoming": [(r["sym"], r["next_er"]) for r in upcoming], "secs": round(time.time() - t0),
                      "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
