"""J Law 大盘体温计 —— 每日判断「躺赚 / 警戒 / 血汗钱」并生成中文报告。

规则来自 TTT 课程与 J Law 公开视频（4 大见顶信号、8 大见底信号、检查清单 A 部分）。
数据：SPY / QQQ 日线（Yahoo Finance），市场宽度用 TradingView 选股器统计
美股市值 ≥ 100 亿美元的股票（约 1,000 只，作为标普 500 宽度的近似）。

用法：python market_regime.py [输出目录]
输出：<输出目录>/大盘报告/YYYY-MM-DD.md，并追加 <输出目录>/大盘报告/大盘历史.csv
仅供学习，不构成投资建议。
"""
import csv
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(OUT_DIR, "大盘报告")
HIST = os.path.join(REPORT_DIR, "大盘历史.csv")
SECTOR_HIST = os.path.join(REPORT_DIR, "行业历史.csv")
SCAN = "https://scanner.tradingview.com/america/scan"
# 11 个 SPDR 行业 ETF（标普 500 行业指数）：代码、中文名、进攻/防守
SECTORS = [("XLK", "科技", "进攻"), ("XLY", "可选消费", "进攻"), ("XLC", "通讯服务", "进攻"), ("XLF", "金融", "进攻"),
           ("XLI", "工业", "进攻"), ("XLB", "原材料", "进攻"), ("XLE", "能源", "其他"), ("XLV", "医疗保健", "防守"),
           ("XLP", "必需消费", "防守"), ("XLU", "公用事业", "防守"), ("XLRE", "房地产", "防守")]
EXCH = {"SPY": "AMEX", "QQQ": "NASDAQ", **{x[0]: "AMEX" for x in SECTORS}}
TV = "https://www.tradingview.com/chart/?symbol="


def tv_url(sym, ex=None):
    ex = ex or EXCH.get(sym)
    return TV + urllib.parse.quote(f"{ex}:{sym}" if ex else sym, safe="")


def tv_link(sym, ex=None, label=None):
    return (f'<a href="{tv_url(sym, ex)}" target="_blank" rel="noopener" title="在 TradingView 打开 {sym} 的图表" '
            f'style="color:#1565C0;text-decoration:none;font-weight:700;">{label or sym} <span style="font-size:11px;">📈</span></a>')


def tv_rs_link(sym):
    """相对强弱图：行业 ETF ÷ SPY（线向上 = 跑赢大盘）。"""
    url = TV + urllib.parse.quote(f"{EXCH[sym]}:{sym}/AMEX:SPY", safe="")
    return (f'<a href="{url}" target="_blank" rel="noopener" title="在 TradingView 打开 {sym}/SPY 相对强弱图" '
            f'style="color:#1565C0;text-decoration:none;font-size:12px;">RS 图</a>')


def http_json(url, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def daily(sym):
    d = http_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d")["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    rows = [dict(date=dt.date.fromtimestamp(t), o=o, h=h, l=l, c=c, v=v)
            for t, o, h, l, c, v in zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"])
            if None not in (o, h, l, c, v)]
    return rows


def sma(vals, n, back=0):
    end = len(vals) - back
    return sum(vals[end - n:end]) / n if end >= n else None


def quad_witching(d):
    return d.month in (3, 6, 9, 12) and d.weekday() == 4 and 15 <= d.day <= 21


def analyse(sym):
    rows = daily(sym)
    c = [r["c"] for r in rows]
    last = rows[-1]
    m = {k: sma(c, k) for k in (10, 20, 50, 200)}
    m50_5 = sma(c, 50, 5)
    m200_20 = sma(c, 200, 20)
    # 出货日：下跌 ≥0.2%，成交量高于前一日；排除四巫日（最近 20 个交易日）
    dist = []
    for i in range(len(rows) - 20, len(rows)):
        r, p = rows[i], rows[i - 1]
        if r["c"] < p["c"] * 0.998 and r["v"] > p["v"] and not quad_witching(r["date"]):
            dist.append(r["date"])
    # 突兀走势：最近 10 日单日跌 ≥3%，或跳空低开且收在当日低位 1/4
    abnormal = []
    for i in range(len(rows) - 10, len(rows)):
        r, p = rows[i], rows[i - 1]
        chg = r["c"] / p["c"] - 1
        gap = r["o"] < p["l"] and (r["c"] - r["l"]) <= 0.25 * (r["h"] - r["l"])
        if chg <= -0.03 or gap:
            abnormal.append((r["date"], round(chg * 100, 1)))
    # 急涨后最大跌幅：最近 5 日内出现 63 日最大单日跌幅
    chgs = [rows[i]["c"] / rows[i - 1]["c"] - 1 for i in range(len(rows) - 63, len(rows))]
    worst_recent = min(chgs[-5:]) == min(chgs) and min(chgs) < -0.015
    # 见底信号相关
    low63 = min(r["l"] for r in rows[-63:])
    rebound = c[-1] / low63 - 1
    return dict(sym=sym, date=last["date"], close=c[-1], rows=rows, chg1d=c[-1] / c[-2] - 1, perf1m=c[-1] / c[-22] - 1,
                sma=m, sma50_up=m[50] > m50_5, sma200_up=m[200] > m200_20,
                dist=dist, abnormal=abnormal, worst_recent=worst_recent, rebound=rebound,
                high20=c[-1] >= max(c[-20:]), cross=m[50] > m[200])


def breadth():
    body = {"filter": [{"left": "type", "operation": "equal", "right": "stock"},
                       {"left": "market_cap_basic", "operation": "egreater", "right": 1e10},
                       {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]}],
            "columns": ["close", "SMA50", "SMA200"], "range": [0, 3000]}
    d = [x["d"] for x in http_json(SCAN, body)["data"]]
    n = len(d)
    a50 = sum(1 for x in d if x[1] and x[0] > x[1]) / n * 100
    a200 = sum(1 for x in d if x[2] and x[0] > x[2]) / n * 100
    return n, a50, a200


def stage2_count():
    """JLaw Stage 2 筛选器（与 TradingView 中设置的一致，表现门槛用固定 5% / 14%）。"""
    body = {"filter": [{"left": "type", "operation": "equal", "right": "stock"},
                       {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
                       {"left": "market_cap_basic", "operation": "egreater", "right": 3e9},
                       {"left": "close", "operation": "egreater", "right": 10},
                       {"left": "volume", "operation": "egreater", "right": 5e5},
                       {"left": "average_volume_90d_calc", "operation": "egreater", "right": 5e5},
                       {"left": "Value.Traded", "operation": "egreater", "right": 5e7},
                       {"left": "SMA10", "operation": "egreater", "right": "SMA20"},
                       {"left": "close", "operation": "egreater", "right": "SMA200"},
                       {"left": "Perf.1M", "operation": "egreater", "right": 5},
                       {"left": "Perf.6M", "operation": "egreater", "right": 14}],
            "columns": ["name", "close", "price_52_week_high", "Perf.6M", "sector", "exchange"],
            "sort": {"sortBy": "Perf.6M", "sortOrder": "desc"}, "range": [0, 1000]}
    d = http_json(SCAN, body)["data"]
    near = [x["d"] for x in d if x["d"][2] and x["d"][1] >= 0.95 * x["d"][2]]
    return len(d), near[:15]


def ret(c, n):
    return c[-1] / c[-1 - n] - 1 if len(c) > n else None


def sparkline(vals, w=90, h=22):
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}" for i, v in enumerate(vals))
    col = "#2E7D32" if vals[-1] >= vals[0] else "#C62828"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="vertical-align:middle;">'
            f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.5"/></svg>')


def sectors(spy):
    """行业 ETF 追踪：涨跌幅、均线位置、相对 SPY 强弱（RS）、排名变化。"""
    spy_by_date = {r["date"]: r["c"] for r in spy["rows"]}
    sc = [r["c"] for r in spy["rows"]]
    year = spy["date"].year
    out = []
    for sym, zh, kind in SECTORS:
        rows = daily(sym)
        c = [r["c"] for r in rows]
        m = {k: sma(c, k) for k in (20, 50, 200)}
        ytd_base = next((rows[i - 1]["c"] for i in range(1, len(rows)) if rows[i]["date"].year == year), None)
        # RS 线 = ETF ÷ SPY（按日期对齐，最近 63 个交易日）
        ratio = [r["c"] / spy_by_date[r["date"]] for r in rows if r["date"] in spy_by_date][-63:]
        m1, s1 = ret(c, 21), ret(sc, 21)
        m3, s3 = ret(c, 63), ret(sc, 63)
        trend = ("强势" if c[-1] > m[50] > m[200] and m[50] > sma(c, 50, 5)
                 else "弱势" if c[-1] < m[200] else "转弱" if c[-1] < m[50] else "整理")
        out.append(dict(sym=sym, zh=zh, kind=kind, date=rows[-1]["date"], close=c[-1], d1=ret(c, 1), w1=ret(c, 5),
                        m1=m1, m3=m3, ytd=c[-1] / ytd_base - 1 if ytd_base else None,
                        rs1=(1 + m1) / (1 + s1) - 1, rs3=(1 + m3) / (1 + s3) - 1,
                        a20=c[-1] > m[20], a50=c[-1] > m[50], a200=c[-1] > m[200], trend=trend,
                        rs_high=ratio[-1] >= max(ratio), rs_low=ratio[-1] <= min(ratio), ratio=ratio))
    out.sort(key=lambda x: -x["m1"])
    for i, x in enumerate(out, 1):
        x["rank"] = i
    return out


def tv_check(sec):
    """收盘价交叉核对：Yahoo vs TradingView（相差 > 1.5% 视为不一致）。"""
    try:
        body = {"symbols": {"tickers": [f"AMEX:{x['sym']}" for x in sec]}, "columns": ["name", "close"]}
        tv = {d["d"][0]: d["d"][1] for d in http_json(SCAN, body)["data"]}
    except Exception as e:
        return f"无法连接 TradingView 核对（{type(e).__name__}）", False
    bad = [x["sym"] for x in sec if not tv.get(x["sym"]) or abs(tv[x["sym"]] / x["close"] - 1) > 0.015]
    ok = len(sec) - len(bad)
    return (f"{ok}/{len(sec)} 个行业 ETF 收盘价与 TradingView 一致" + (f"；不一致：{'、'.join(bad)}" if bad else "")), not bad


def load_sector_hist():
    if not os.path.exists(SECTOR_HIST):
        return []
    with open(SECTOR_HIST, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def save_sector_hist(sec, hist):
    today = str(sec[0]["date"])
    if any(h["date"] == today for h in hist):
        return
    new = not os.path.exists(SECTOR_HIST)
    with open(SECTOR_HIST, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "sym", "close", "m1", "rs1", "rank"])
        for x in sorted(sec, key=lambda x: x["sym"]):
            w.writerow([today, x["sym"], round(x["close"], 2), round(x["m1"] * 100, 2), round(x["rs1"] * 100, 2), x["rank"]])


def sector_prev_rank(sec, hist):
    """上一个交易日的排名（同一天重跑时跳过当天）。"""
    today = str(sec[0]["date"])
    dates = sorted({h["date"] for h in hist if h["date"] != today})
    if not dates:
        return {}, None
    last = dates[-1]
    return {h["sym"]: int(h["rank"]) for h in hist if h["date"] == last}, last


def sector_html(sec, prev_rank, prev_date, check, check_ok):
    td = 'style="padding:5px 6px;border-bottom:1px solid #eee;white-space:nowrap;"'
    th = 'style="padding:5px 6px;background:#f5f5f5;text-align:left;font-weight:600;border-bottom:1px solid #ddd;white-space:nowrap;"'
    ok = lambda b: '<span style="color:#2E7D32;">✔</span>' if b else '<span style="color:#C62828;">✘</span>'

    def pc(v):
        if v is None:
            return "—"
        c = "#2E7D32" if v > 0 else "#C62828" if v < 0 else "#555"
        return f'<span style="color:{c};">{v * 100:+.1f}%</span>'

    tcol = {"强势": "#2E7D32", "整理": "#555", "转弱": "#B26A00", "弱势": "#C62828"}
    kcol = {"进攻": "#1565C0", "防守": "#6A1B9A", "其他": "#555"}
    rows = ""
    for x in sec:
        pr = prev_rank.get(x["sym"])
        mv = ("" if pr is None else '<span style="color:#888;">—</span>' if pr == x["rank"] else
              f'<span style="color:{"#2E7D32" if pr > x["rank"] else "#C62828"};font-size:11px;">'
              f'{"▲" if pr > x["rank"] else "▼"}{abs(pr - x["rank"])}</span>')
        flag = (' <span title="RS 线创 3 个月新高" style="color:#2E7D32;font-size:11px;">RS新高</span>' if x["rs_high"] else
                ' <span title="RS 线创 3 个月新低" style="color:#C62828;font-size:11px;">RS新低</span>' if x["rs_low"] else "")
        rows += (f'<tr><td {td}>{x["rank"]} {mv}</td>'
                 f'<td {td}>{tv_link(x["sym"])}<br><span style="font-size:11px;color:#666;">{x["zh"]} · '
                 f'<span style="color:{kcol[x["kind"]]};">{x["kind"]}</span></span></td>'
                 f'<td {td}>{x["close"]:.2f}</td><td {td}>{pc(x["d1"])}</td><td {td}>{pc(x["w1"])}</td>'
                 f'<td {td}><b>{pc(x["m1"])}</b></td><td {td}>{pc(x["m3"])}</td><td {td}>{pc(x["ytd"])}</td>'
                 f'<td {td}>{pc(x["rs1"])}{flag}</td><td {td}>{sparkline(x["ratio"])} {tv_rs_link(x["sym"])}</td>'
                 f'<td {td}>{ok(x["a20"])}{ok(x["a50"])}{ok(x["a200"])}</td>'
                 f'<td {td}><span style="color:{tcol[x["trend"]]};font-weight:600;">{x["trend"]}</span></td></tr>')
    avg = lambda k: sum(x["m1"] for x in sec if x["kind"] == k) / max(1, sum(1 for x in sec if x["kind"] == k))
    off, dfn = avg("进攻"), avg("防守")
    lead = "、".join(f'{x["zh"]}（{x["m1"] * 100:+.1f}%）' for x in sec[:3])
    lag = "、".join(f'{x["zh"]}（{x["m1"] * 100:+.1f}%）' for x in sec[-3:])
    strong = sum(1 for x in sec if x["trend"] == "强势")
    above50 = sum(1 for x in sec if x["a50"])
    tilt = ("进攻型行业领先，资金偏向冒险（有利于成长股突破）" if off - dfn > 0.01 else
            "防守型行业领先，资金偏向避险（小心追高）" if dfn - off > 0.01 else "进攻与防守行业表现相近")
    return f"""<h3 style="margin:22px 0 6px;">行业指数追踪（11 个 SPDR 行业 ETF，按近 1 月涨幅排名）</h3>
<p style="margin:0 0 6px;font-size:13px;line-height:1.6;"><b>领涨：</b>{lead}<br><b>落后：</b>{lag}<br>
<b>进攻 vs 防守（近 1 月平均）：</b>{off * 100:+.1f}% vs {dfn * 100:+.1f}% → {tilt}<br>
<b>强势行业：</b>{strong}/11 · <b>站上 50 天线：</b>{above50}/11</p>
<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12.5px;">
<tr><th {th}>排名</th><th {th}>行业</th><th {th}>收盘</th><th {th}>当日</th><th {th}>1周</th><th {th}>1月</th><th {th}>3月</th>
<th {th}>今年</th><th {th}>RS 1月</th><th {th}>RS 线（3个月）</th><th {th}>20/50/200天</th><th {th}>趋势</th></tr>
{rows}</table></div>
<p style="margin:6px 0 0;font-size:11px;color:#777;line-height:1.5;">排名箭头 = 与 {prev_date or "上一个交易日"} 相比的排名变化。
RS 1月 = 行业近 1 月涨幅相对 SPY 的超额表现；RS 线 = ETF ÷ SPY，向上代表跑赢大盘（J Law：领导股多出自 RS 领先的行业）。
趋势：强势 = 收盘 &gt; 50 天线 &gt; 200 天线且 50 天线向上；整理 = 在 50 天线上但未全部满足；转弱 = 跌破 50 天线；弱势 = 跌破 200 天线。
<span style="color:{"#2E7D32" if check_ok else "#C62828"};">数据核对：{check}</span></p>"""


def load_hist():
    if not os.path.exists(HIST):
        return []
    with open(HIST, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def build_html(today, state, prev_state, advice, spy, qqq, n, b50, b200, s2, prev, red, yellow, bottom, near, sec_html=""):
    """邮件友好的 HTML（全部内联样式，浅色背景）。"""
    col = {"🔴": ("#C62828", "#FDECEA"), "🟡": ("#B26A00", "#FFF4E0"), "🟢": ("#2E7D32", "#E8F5E9")}[state[0]]
    td = 'style="padding:6px 8px;border-bottom:1px solid #eee;"'
    th = 'style="padding:6px 8px;background:#f5f5f5;text-align:left;font-weight:600;border-bottom:1px solid #ddd;"'
    ok = lambda b: '<span style="color:#2E7D32;">✔</span>' if b else '<span style="color:#C62828;">✘</span>'

    def delta(cur, key, fmt):
        if not prev:
            return ""
        d = cur - float(prev[key])
        c = "#2E7D32" if d > 0 else "#C62828" if d < 0 else "#777"
        return f' <span style="color:{c};font-size:12px;">({d:+{fmt}} vs {prev["date"]})</span>'

    rows = ""
    for x in (spy, qqq):
        s = x["sma"]
        rows += (f'<tr><td {td}>{tv_link(x["sym"])}</td><td {td}>{x["close"]:.2f}</td>'
                 f'<td {td}>{x["chg1d"]*100:+.1f}%</td><td {td}>{x["perf1m"]*100:+.1f}%</td>'
                 f'<td {td}>{ok(x["close"] > s[20])}</td><td {td}>{ok(x["close"] > s[50])}</td><td {td}>{ok(x["close"] > s[200])}</td>'
                 f'<td {td}>{"向上" if x["sma50_up"] else "向下"}</td>'
                 f'<td {td}><span style="color:{"#C62828" if len(x["dist"]) >= 4 else "#333"};">{len(x["dist"])}</span></td></tr>')
    sig = ""
    if red:
        sig += '<h3 style="color:#C62828;margin:18px 0 6px;">🔴 血汗钱信号</h3><ul style="margin:0;padding-left:20px;">' + "".join(f"<li>{t}</li>" for t in red) + "</ul>"
    if yellow:
        sig += '<h3 style="color:#B26A00;margin:18px 0 6px;">🟡 警戒信号</h3><ul style="margin:0;padding-left:20px;">' + "".join(f"<li>{t}</li>" for t in yellow) + "</ul>"
    bot = "".join(f"<li>{ok(b)} {t}</li>" for t, b in bottom)
    stocks = "".join(f'<tr><td {td}>{tv_link(r[0], r[5])}</td><td {td}>{r[1]:.2f}</td><td {td}>{r[3]:.0f}%</td><td {td}>{r[4]}</td></tr>' for r in near)
    change = (f'<div style="margin-top:8px;font-size:15px;font-weight:600;">⚠ 状态改变：{prev_state} → {state}</div>' if prev_state else "")
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>大盘体温计 {today}</title></head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222;">
<div style="max-width:960px;margin:0 auto;padding:16px;">
<div style="background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e3e3e3;">
<div style="background:{col[1]};border-left:6px solid {col[0]};padding:16px 18px;">
<div style="font-size:13px;color:#555;">J Law 大盘体温计 · 美股收盘 {today}</div>
<div style="font-size:26px;font-weight:700;color:{col[0]};margin-top:4px;">{state}</div>{change}
<div style="margin-top:8px;font-size:14px;line-height:1.6;"><b>建议：</b>{advice}</div></div>
<div style="padding:16px 18px;font-size:14px;line-height:1.6;">
<table style="width:100%;border-collapse:collapse;font-size:13px;">
<tr><th {th}>指数</th><th {th}>收盘</th><th {th}>当日</th><th {th}>近1月</th><th {th}>20天</th><th {th}>50天</th><th {th}>200天</th><th {th}>50线</th><th {th}>出货日</th></tr>
{rows}</table>
<p style="margin:14px 0 4px;"><b>市场宽度</b>（{n} 只市值 ≥100 亿美元的美股）：<b>{b50:.1f}%</b> 在 50 天线之上{delta(b50, "above50", ".1f")}，{b200:.1f}% 在 200 天线之上</p>
<p style="margin:4px 0;"><b>JLaw Stage 2 筛出</b>：<b>{s2}</b> 只{delta(s2, "stage2", ".0f")}</p>
{sig}
{sec_html}
<h3 style="margin:18px 0 6px;">见底 / 转强信号</h3><ul style="margin:0;padding-left:20px;list-style:none;">{bot}</ul>
{('<h3 style="margin:18px 0 6px;">离 52 周高点 5% 以内的 Stage 2 股票</h3><table style="width:100%;border-collapse:collapse;font-size:13px;"><tr><th ' + th + '>股票</th><th ' + th + '>收盘</th><th ' + th + '>6个月涨幅</th><th ' + th + '>板块</th></tr>' + stocks + '</table>') if near else ''}
<p style="margin:14px 0 0;font-size:12px;color:#555;">📈 点指数、行业 ETF 或股票代码会在新分页打开 TradingView 日线图；「RS 图」打开该行业 ÷ SPY 的相对强弱图。</p>
</div>
<div style="padding:12px 18px;background:#fafafa;border-top:1px solid #eee;font-size:11px;color:#888;line-height:1.5;">
规则：🔴 = 指数在 50 天线下且 50 天线向下 / 跌破 200 天线 / 50 天线 &lt; 200 天线 / 宽度 &lt; 40%；🟡 = 近 20 日 ≥4 个出货日、突兀大跌或跳空低开、3 个月最大跌幅、跌破 20 或 50 天线、宽度 &lt; 50%、宽度背驰。出货日 = 下跌 ≥0.2% 且成交量高于前一日（排除四巫日）。宽度为大型股近似值。<br>仅供学习，不构成投资建议。</div>
</div></div></body></html>"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(REPORT_DIR, exist_ok=True)
    spy, qqq = analyse("SPY"), analyse("QQQ")
    n, b50, b200 = breadth()
    s2, near = stage2_count()
    sec = sectors(spy)
    check, check_ok = tv_check(sec)
    shist = load_sector_hist()
    prev_rank, prev_rdate = sector_prev_rank(sec, shist)
    hist = load_hist()
    today_str = str(spy["date"])
    past = [h for h in hist if h["date"] != today_str]      # 同一天重跑时，和上一个交易日比较
    prev = past[-1] if past else None
    # 背驰：指数在 20 日高位，但 50 天线以上比例比 10 个记录前低 5 个百分点以上
    old = hist[-10] if len(hist) >= 10 else None
    diverge = bool(old and spy["high20"] and b50 < float(old["above50"]) - 5)

    red, yellow = [], []
    for x in (spy, qqq):
        s = x["sma"]
        if x["close"] < s[50] and not x["sma50_up"]:
            red.append(f'{x["sym"]} 在 50 天线下方且 50 天线向下')
        if x["close"] < s[200]:
            red.append(f'{x["sym"]} 跌破 200 天线')
        if not x["cross"]:
            red.append(f'{x["sym"]} 50 天线低于 200 天线（10 周线 < 40 周线）')
        if len(x["dist"]) >= 4:
            yellow.append(f'{x["sym"]} 近 20 日有 {len(x["dist"])} 个出货日')
        if x["abnormal"]:
            yellow.append(f'{x["sym"]} 近 10 日出现突兀大跌/跳空低开：' + "、".join(f"{d:%m-%d}({p}%)" for d, p in x["abnormal"]))
        if x["worst_recent"]:
            yellow.append(f'{x["sym"]} 近 5 日出现 3 个月来最大单日跌幅')
        if x["close"] < s[50] and x["sma50_up"]:
            yellow.append(f'{x["sym"]} 跌破 50 天线（50 天线仍向上）')
        elif x["close"] < s[20]:
            yellow.append(f'{x["sym"]} 跌破 20 天线')
    if b50 < 40:
        red.append(f"市场宽度弱：只有 {b50:.0f}% 的大型股在 50 天线之上")
    elif b50 < 50:
        yellow.append(f"市场宽度偏弱：{b50:.0f}% 的大型股在 50 天线之上")
    if diverge:
        yellow.append("背驰：指数在 20 日高位，但站上 50 天线的股票比例下降")

    state = "🔴 血汗钱" if red else ("🟡 警戒" if yellow else "🟢 躺赚")
    advice = {"🔴 血汗钱": "以现金为主、冬眠；只观察逆市走强的股票（下一轮领导股候选），不追反弹。",
              "🟡 警戒": "减仓、提高标准：只做形态最紧、优势最多的股票，单笔风险减半；有利润的持仓收紧止损。",
              "🟢 躺赚": "积极操作：按检查清单 D 在突破点买入领导股，顺手时逐步加大仓位。"}[state]

    # 见底 / 转强信号（血汗钱或警戒时参考）
    bottom = [("SPY 自 3 个月低点反弹 ≥ 10%（大力反弹）", spy["rebound"] >= 0.10),
              ("SPY 50 天线在 200 天线之上（10 周 > 40 周）", spy["cross"]),
              ("SPY 200 天线向上（40 周线走平或向上）", spy["sma200_up"]),
              ("≥ 70% 大型股在 50 天线之上（广泛参与）", b50 >= 70),
              ("JLaw Stage 2 筛出 ≥ 150 只（大量个股出现买点）", s2 >= 150)]

    today = spy["date"]
    changed = prev and prev["state"] != state
    lines = [f"# 大盘体温计 {today}", "",
             f"## 状态：{state}" + ("（⚠ 状态改变：上次是 " + prev["state"] + "）" if changed else ""), "",
             f"**建议**：{advice}", "",
             "| 指数 | 收盘 | 当日 | 近1月 | 20天线 | 50天线 | 200天线 | 50线方向 | 出货日(20日) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for x in (spy, qqq):
        s = x["sma"]
        pos = lambda m: ("上方 ✔" if x["close"] > m else "下方 ✘")
        lines.append(f'| {x["sym"]} | {x["close"]:.2f} | {x["chg1d"]*100:+.1f}% | {x["perf1m"]*100:+.1f}% | {pos(s[20])} | '
                     f'{pos(s[50])} | {pos(s[200])} | {"向上" if x["sma50_up"] else "向下"} | {len(x["dist"])} |')
    lines += ["", f"**市场宽度**（{n} 只市值 ≥ 100 亿美元的美股）：{b50:.1f}% 在 50 天线之上，{b200:.1f}% 在 200 天线之上",
              f"**JLaw Stage 2 筛出**：{s2} 只（数量越多市况越好；熊市时可能只有几十只）", ""]
    if red:
        lines += ["### 🔴 血汗钱信号"] + [f"- {t}" for t in red] + [""]
    if yellow:
        lines += ["### 🟡 警戒信号"] + [f"- {t}" for t in yellow] + [""]
    lines += ["### 见底 / 转强信号（8 大见底信号的可自动部分）"] + [f"- {'✔' if ok else '✘'} {t}" for t, ok in bottom] + [""]
    lines += ["### 行业指数追踪（按近 1 月涨幅排名）", "",
              "| 排名 | 行业 | 收盘 | 当日 | 1周 | 1月 | 3月 | 今年 | RS 1月 | 趋势 |", "|---|---|---|---|---|---|---|---|---|---|"]
    f1 = lambda v: "—" if v is None else f"{v * 100:+.1f}%"
    lines += [f'| {x["rank"]} | {x["sym"]} {x["zh"]} | {x["close"]:.2f} | {f1(x["d1"])} | {f1(x["w1"])} | {f1(x["m1"])} | '
              f'{f1(x["m3"])} | {f1(x["ytd"])} | {f1(x["rs1"])} | {x["trend"]} |' for x in sec]
    lines += ["", f"数据核对：{check}", ""]
    if near:
        lines += ["### 离 52 周高点 5% 以内的 Stage 2 股票（前 15，按 6 个月涨幅）", "",
                  "| 股票 | 收盘 | 6个月涨幅 | 板块 |", "|---|---|---|---|"]
        lines += [f"| {r[0]} | {r[1]:.2f} | {r[3]:.0f}% | {r[4]} |" for r in near]
        lines.append("")
    lines += ["---", "规则：🔴 = 指数在 50 天线下且 50 天线向下 / 跌破 200 天线 / 50 天线 < 200 天线 / 宽度 < 40%；"
              "🟡 = 近 20 日 ≥4 个出货日、突兀大跌或跳空低开、3 个月最大跌幅、跌破 20 或 50 天线、宽度 < 50%、宽度背驰。",
              "出货日 = 下跌 ≥0.2% 且成交量高于前一日（排除四巫日）。宽度为大型股近似值。仅供学习，不构成投资建议。"]
    path = os.path.join(REPORT_DIR, f"{today}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    html_path = os.path.join(REPORT_DIR, f"{today}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(today, state, changed and prev["state"], advice, spy, qqq, n, b50, b200, s2, prev,
                           red, yellow, bottom, near, sector_html(sec, prev_rank, prev_rdate, check, check_ok)))
    save_sector_hist(sec, shist)

    new = not os.path.exists(HIST)
    if not any(h["date"] == str(today) for h in hist):
        with open(HIST, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["date", "state", "spy", "qqq", "above50", "above200", "spy_dist", "qqq_dist", "stage2"])
            w.writerow([today, state, round(spy["close"], 2), round(qqq["close"], 2), round(b50, 1), round(b200, 1),
                        len(spy["dist"]), len(qqq["dist"]), s2])
    print(json.dumps({"date": str(today), "state": state, "changed": bool(changed), "report": path, "html": html_path,
                      "red": red, "yellow": yellow, "above50": round(b50, 1), "stage2": s2,
                      "sectors": [x["sym"] for x in sec], "sector_check": check}, ensure_ascii=False))


if __name__ == "__main__":
    main()
