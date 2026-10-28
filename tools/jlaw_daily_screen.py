"""J Law 每日选股 —— 两种形态：「VCP 突破」与「动能后 META 回调」。

依据 TTT 课程、检查清单 D，以及 J Law 2026 年 Chart Fanatics 访问（多重优势交易系统）：
  * 先有动能（催化剂带动的大涨 + 大成交量），再等低量回调到「突破位 + 10/20 天线 + 趋势线」重叠的 META 区间
  * 止损 3–5%，目标 5R；单笔风险约账户 0.35%
  * 成交额：日均成交额 ≥ 1 亿美元；≥ 10 亿代表机构大量参与
  * 相对强度：大盘下跌日更抗跌，RS 线接近新高
  * 产业组 / 主题：同一细分行业多只股票一起走强才可靠
  * 大周期支撑：周线 20 周线（以日线 100 日均线近似）

流程：
  1. TradingView 选股器：市值 ≥30 亿、股价 ≥10、成交量 ≥50 万、股价 ≥ SMA200、SMA50 ≥ SMA200（第二阶段）
  2. 逐只下载一年日线（Yahoo Finance）并计算：20 日平均成交额（≥1 亿美元）、RS、动能事件、META 回调、VCP
  3. VCP 突破：沿用 8 项评分，并要求 1 个月 / 6 个月涨幅约为标普两倍
  4. META 回调：近 30 个交易日内有动能事件，回调 2%–15%，按 8 项优势计数
  5. 标出未来 14 天内有业绩的股票（课程：业绩前不建大仓）

用法：python jlaw_daily_screen.py [输出目录]
输出：<输出目录>/每日选股/YYYY-MM-DD.html（主要）、.md、.csv、_图表.png
仅供学习，不构成投资建议。
"""
import csv
import datetime as dt
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREEN_DIR = os.path.join(OUT_DIR, "每日选股")
HIST = os.path.join(OUT_DIR, "大盘报告", "大盘历史.csv")
SCAN = "https://scanner.tradingview.com/america/scan"
COLS = ["name", "description", "close", "market_cap_basic", "Value.Traded", "Perf.1M", "Perf.6M", "sector", "industry",
        "earnings_release_next_date", "earnings_release_date", "average_volume_30d_calc", "exchange"]
EXCH = {}                  # 代码 → 交易所（做 TradingView 图表链接用）


def tv_url(sym):
    """TradingView 日线图链接（例如 NASDAQ:AAPL）。"""
    ex = EXCH.get(sym)
    return "https://www.tradingview.com/chart/?symbol=" + (f"{ex}:{sym}" if ex else sym)

MIN_DOLLAR_VOL = 1e8        # 20 日平均成交额（美元）
BIG_DOLLAR_VOL = 1e9        # 机构大量参与
RISK_PER_TRADE = 0.0035     # J Law：单笔风险约账户 0.35%
META_MAX_RISK = 5.0         # META 回调止损上限 %
VCP_MAX_RISK = 8.0          # VCP 止损上限 %
HOT_GROUP_MIN = 3           # 同一细分行业 ≥3 只 = 热门组


def http_json(url, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def scan():
    spy1m, spy6m = http_json(SCAN, {"symbols": {"tickers": ["AMEX:SPY"]}, "columns": ["Perf.1M", "Perf.6M"]})["data"][0]["d"]
    body = {"filter": [
        {"left": "type", "operation": "equal", "right": "stock"},
        {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
        {"left": "market_cap_basic", "operation": "egreater", "right": 3e9},
        {"left": "close", "operation": "egreater", "right": 10},
        {"left": "volume", "operation": "egreater", "right": 5e5},
        {"left": "average_volume_30d_calc", "operation": "egreater", "right": 5e5},
        {"left": "close", "operation": "egreater", "right": "SMA200"},
        {"left": "SMA50", "operation": "egreater", "right": "SMA200"}],
        "columns": COLS, "range": [0, 3000]}
    rows = [dict(zip(COLS, r["d"])) for r in http_json(SCAN, body)["data"]]
    # 先用 30 日均量 × 股价粗筛成交额，再在日线里精算 20 日平均成交额
    rows = [r for r in rows if (r["close"] or 0) * (r["average_volume_30d_calc"] or 0) >= MIN_DOLLAR_VOL * 0.7]
    return dict(spy1m=spy1m, spy6m=spy6m, min1m=max(2 * spy1m, 5.0), min6m=max(2 * spy6m, 10.0), rows=rows)


def prices(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym.replace('.', '-')}?range=1y&interval=1d"
    for _ in range(3):
        try:
            d = http_json(url)["chart"]["result"][0]
            q = d["indicators"]["quote"][0]
            return [dict(d=dt.date.fromtimestamp(t), o=o, h=h, l=l, c=c, v=v) for t, o, h, l, c, v in
                    zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"]) if None not in (o, h, l, c, v)]
        except Exception:
            pass
    return None


def sma(vals, n, back=0):
    end = len(vals) - back
    return sum(vals[end - n:end]) / n if end >= n else None


def ema(vals, n):
    k, e = 2 / (n + 1), vals[0]
    for x in vals[1:]:
        e = x * k + e * (1 - k)
    return e


def analyse(meta, px, spy):
    if not px or len(px) < 210:
        return None
    c = [x["c"] for x in px]; o = [x["o"] for x in px]; h = [x["h"] for x in px]
    l = [x["l"] for x in px]; v = [x["v"] for x in px]
    close, n = c[-1], len(px)
    s10, s20, s50, s100, s200, e20 = sma(c, 10), sma(c, 20), sma(c, 50), sma(c, 100), sma(c, 200), ema(c[-120:], 20)
    dollar20 = sum(c[i] * v[i] for i in range(n - 20, n)) / 20
    if dollar20 < MIN_DOLLAR_VOL:
        return None
    mcap = meta["market_cap_basic"] or 0

    # ---- 相对强度 ----
    spy_c = {x["d"]: x["c"] for x in spy}
    rs = [c[i] / spy_c[px[i]["d"]] for i in range(n) if px[i]["d"] in spy_c]
    rs_near_high = len(rs) > 126 and rs[-1] >= 0.95 * max(rs[-126:])
    down = []                       # 近 20 个交易日中标普下跌的日子：个股 − 标普
    for i in range(n - 20, n):
        d0, d1 = px[i - 1]["d"], px[i]["d"]
        if d0 in spy_c and d1 in spy_c:
            sr = spy_c[d1] / spy_c[d0] - 1
            if sr < 0:
                down.append((c[i] / c[i - 1] - 1) - sr)
    rs_down = sum(down) / len(down) if down else 0
    rs_ok = rs_near_high or (len(down) >= 3 and rs_down > 0)

    # ---- 动能事件（近 30 个交易日，排除今天）----
    thr = 0.05 if mcap >= 2e11 else 0.08
    mom = None
    for i in range(n - 30, n - 1):
        avg50 = sum(v[i - 50:i]) / 50
        ret, gap = c[i] / c[i - 1] - 1, o[i] / c[i - 1] - 1
        vr = v[i] / avg50
        run3 = c[i] / c[i - 3] - 1
        multi = run3 >= 0.12 and all(v[j] > avg50 for j in range(i - 2, i + 1))
        if ((ret >= thr or (gap >= 0.05 and ret >= 0.03)) and vr >= 1.5) or multi:   # 跳空后收跌不算动能
            if not mom or max(ret, run3) >= mom["size"]:
                mom = dict(i=i, date=px[i]["d"], size=max(ret, run3 if multi else ret), gap=gap, vr=vr, vol=v[i])
    er_last = meta.get("earnings_release_date")
    catalyst = bool(mom and er_last and abs((dt.datetime.fromtimestamp(er_last, dt.timezone.utc).date() - mom["date"]).days) <= 3)

    er = meta.get("earnings_release_next_date")
    days_to_er = (dt.datetime.fromtimestamp(er, dt.timezone.utc).date() - dt.date.today()).days if er else None
    EXCH[meta["name"]] = meta.get("exchange") or ""
    base = dict(sym=meta["name"], name=(meta["description"] or "")[:30], sector=meta["sector"] or "", industry=meta["industry"] or "",
                close=round(close, 2), dollar20=dollar20, rs_near_high=rs_near_high, rs_down=round(rs_down * 100, 2), rs_ok=rs_ok,
                p1m=round(meta["Perf.1M"] or 0, 1), p6m=round(meta["Perf.6M"] or 0, 1), er_days=days_to_er,
                mom=mom, catalyst=catalyst, px=px)

    # ---- META 回调 ----
    meta_res = None
    if mom:
        peak_i = max(range(mom["i"], n), key=lambda k: h[k])
        peak = h[peak_i]
        pb = (close / peak - 1) * 100
        days_pb = n - 1 - peak_i
        breakout = max(h[mom["i"] - 40:mom["i"]])               # 动能前的前浪顶 = 突破位
        pb_vol = sum(v[peak_i + 1:]) / days_pb if days_pb else v[-1]
        avg50_now = sum(v[-50:]) / 50
        mas = [s10, s20, e20]
        ma_dist = min(abs(close / m - 1) for m in mas) * 100
        zone_lo = min(min(mas), breakout) if close <= breakout * 1.06 else min(mas)   # 只有贴近突破位时才把它算进区间
        stop = min(min(l[-3:]), zone_lo) * 0.99
        risk = (close / stop - 1) * 100
        reward = (peak / close - 1) * 100
        edges = {
            "动能事件": True,
            "低量回调": days_pb >= 2 and pb_vol < 0.6 * mom["vol"] and pb_vol < 1.1 * avg50_now,
            "10/20 天线支撑": ma_dist <= 3 and close >= min(mas) * 0.97,
            "突破位支撑": breakout * 0.98 <= close <= breakout * 1.06,
            "RS 抗跌/新高": rs_ok,
            "周线 20 周线支撑": s100 and 0 <= (close / s100 - 1) * 100 <= 6,
            "业绩/催化剂": catalyst,
            "热门产业组": False,               # 稍后按行业统计后补上
        }
        meta_res = dict(peak=round(peak, 2), pb=round(pb, 1), days_pb=days_pb, breakout=round(breakout, 2),
                        ma_dist=round(ma_dist, 1), stop=round(stop, 2), risk=round(risk, 1), reward=round(reward, 1),
                        rr=round(reward / risk, 1) if risk > 0 else 0, edges=edges, in_pullback=-15 <= pb <= -2 and days_pb >= 2 and close > s50)   # META 回调要守在 50 天线之上

    # ---- VCP 突破（原 8 项）----
    hi52 = max(h[-252:])
    vbase = max(h[-40:-2])
    pivot = vbase if close <= vbase else max(h[-40:])
    ext = (close / pivot - 1) * 100
    depths = []
    for a, b in ((-60, -40), (-40, -20), (-20, None)):
        hh, ll = max(h[a:b]), min(l[a:b])
        depths.append((hh - ll) / hh * 100)
    tight10 = (max(h[-10:]) - min(l[-10:])) / max(h[-10:]) * 100
    dry = (sum(v[-10:]) / 10) / (sum(v[-50:]) / 50)
    vstop = min(l[-10:]) * 0.995
    vrisk = (pivot / vstop - 1) * 100
    checks = {"趋势": close > s50 > s200 and s200 > sma(c, 200, 21), "近52周高": close >= 0.75 * hi52,
              "波幅收缩": depths[0] > depths[1] > depths[2], "最后收缩<10%": depths[2] < 10, "紧密≤8%": tight10 <= 8,
              "量缩": dry < 0.9, "止损≤8%": vrisk <= VCP_MAX_RISK, "接近突破点": -6 <= ext <= 5}
    status = ("刚突破" if ext > 0 else "等突破") if -6 <= ext <= 5 else ("已远离" if ext > 5 else "离突破点远")
    vcp = dict(pivot=round(pivot, 2), ext=round(ext, 1), stop=round(vstop, 2), risk=round(vrisk, 1), d=[round(x, 1) for x in depths],
               tight10=round(tight10, 1), dry=round(dry, 2), score=sum(checks.values()), status=status,
               fails="、".join(k for k, ok in checks.items() if not ok))
    base.update(meta=meta_res, vcp=vcp)
    return base


def market_state():
    if not os.path.exists(HIST):
        return None
    with open(HIST, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else None


def shares_per_100k(entry, stop):
    return int(100000 * RISK_PER_TRADE / (entry - stop)) if entry > stop else 0


def charts(items, path):
    """items: [(股票结果, 'META' 或 'VCP')]"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans SC", "Arial Unicode MS", "DejaVu Sans"]
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    if not items:
        return False
    cols = 3
    rws = (len(items) + cols - 1) // cols
    fig, axes = plt.subplots(rws, cols, figsize=(18, 4.6 * rws), squeeze=False)
    for ax in axes.flat:
        ax.axis("off")
    for ax, (it, kind) in zip(axes.flat, items):
        ax.axis("on")
        px = it["px"]
        c = [x["c"] for x in px]
        ma = {k: [sum(c[i - k + 1:i + 1]) / k if i >= k - 1 else None for i in range(len(c))] for k in (10, 20, 50, 200)}
        d = px[-130:]
        off = len(px) - len(d)
        for i, x in enumerate(d):
            col = "#26a69a" if x["c"] >= x["o"] else "#ef5350"
            ax.vlines(i, x["l"], x["h"], color=col, lw=0.7)
            ax.vlines(i, min(x["o"], x["c"]), max(x["o"], x["c"]), color=col, lw=3)
        for k, colr in ((10, "#9e9e9e"), (20, "#43a047"), (50, "#1e88e5"), (200, "#e53935")):
            ax.plot(range(len(d)), ma[k][off:], color=colr, lw=1)
        er = f" | 业绩 {it['er_days']} 天后" if it["er_days"] is not None and 0 <= it["er_days"] <= 14 else ""
        if kind == "META":
            m = it["meta"]
            ax.axhline(m["breakout"], color="#ff9800", ls="--", lw=1.2)
            ax.axhline(m["stop"], color="#8e24aa", ls=":", lw=1.2)
            mi = it["mom"]["i"] - off
            if 0 <= mi < len(d):
                ax.annotate("动能", (mi, d[mi]["l"]), xytext=(mi, d[mi]["l"] * 0.95), color="#2E7D32", fontsize=9,
                            ha="center", arrowprops=dict(arrowstyle="->", color="#2E7D32"))
            n_e = sum(m["edges"].values())
            title = f"[META 回调] {it['sym']} {it['name'][:18]}\n优势 {n_e}/8 | 回调 {m['pb']}% | 止损 {m['risk']}% | 到前高 {m['rr']}R{er}"
        else:
            v = it["vcp"]
            ax.axhline(v["pivot"], color="#ff9800", ls="--", lw=1.2)
            ax.axhline(v["stop"], color="#8e24aa", ls=":", lw=1.2)
            title = f"[VCP 突破] {it['sym']} {it['name'][:18]}\n得分 {v['score']}/8 | 距突破点 {v['ext']}% | 止损 {v['risk']}%{er}"
        ax.set_title(title, fontsize=10, loc="left")
        ax.tick_params(labelsize=8, labelbottom=False)
        ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=75)
    return True


def fmt_money(x):
    return f"{x / 1e9:.1f}B" if x >= 1e9 else f"{x / 1e6:.0f}M"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(SCREEN_DIR, exist_ok=True)
    today = dt.date.today()
    s = scan()
    spy = prices("SPY")
    with ThreadPoolExecutor(8) as ex:
        pxs = list(ex.map(lambda r: prices(r["name"]), s["rows"]))
    res = [x for x in (analyse(m, p, spy) for m, p in zip(s["rows"], pxs)) if x]

    # ---- 产业组：有动能事件或通过 VCP 相对强度层的股票，按细分行业计数 ----
    rs_layer = {r["sym"] for r in res if r["p1m"] >= s["min1m"] and r["p6m"] >= s["min6m"]}
    groups = {}
    for r in res:
        if r["mom"] or r["sym"] in rs_layer:
            groups.setdefault(r["industry"], []).append(r["sym"])
    hot = {k: v for k, v in groups.items() if k and len(v) >= HOT_GROUP_MIN}
    for r in res:
        if r["meta"]:
            r["meta"]["edges"]["热门产业组"] = r["industry"] in hot
            r["meta"]["n_edges"] = sum(r["meta"]["edges"].values())

    soon = lambda r: r["er_days"] is not None and 0 <= r["er_days"] <= 14
    meta_all = [r for r in res if r["meta"] and r["meta"]["in_pullback"]]
    meta_ready = [r for r in meta_all if r["meta"]["edges"]["低量回调"]
                  and (r["meta"]["edges"]["10/20 天线支撑"] or r["meta"]["edges"]["突破位支撑"])
                  and r["meta"]["risk"] <= META_MAX_RISK and r["meta"]["n_edges"] >= 4]
    meta_watch = [r for r in meta_all if r not in meta_ready and r["meta"]["n_edges"] >= 3 and r["meta"]["risk"] <= VCP_MAX_RISK]
    meta_ready.sort(key=lambda r: (-r["meta"]["n_edges"], r["meta"]["risk"]))
    meta_watch.sort(key=lambda r: (-r["meta"]["n_edges"], r["meta"]["risk"]))
    vcp_pool = [r for r in res if r["sym"] in rs_layer]
    vcp_ready = [r for r in vcp_pool if r["vcp"]["score"] >= 6 and r["vcp"]["status"] in ("等突破", "刚突破") and r["vcp"]["risk"] <= VCP_MAX_RISK]
    vcp_watch = [r for r in vcp_pool if r not in vcp_ready and r["vcp"]["score"] >= 5 and r["vcp"]["status"] in ("等突破", "刚突破")]
    vcp_ready.sort(key=lambda r: (-r["vcp"]["score"], r["vcp"]["risk"]))
    vcp_watch.sort(key=lambda r: (-r["vcp"]["score"], r["vcp"]["risk"]))
    fresh_mom = sorted([r for r in res if r["mom"] and (len(r["px"]) - 1 - r["mom"]["i"]) <= 5],
                       key=lambda r: -r["mom"]["size"])

    # ---- 与上一份比较 ----
    prev_files = sorted(f for f in os.listdir(SCREEN_DIR) if f.endswith(".csv") and f[:10] != str(today))
    prev_set = set()
    if prev_files:
        with open(os.path.join(SCREEN_DIR, prev_files[-1]), encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("就绪") in ("META", "VCP") or int(row.get("得分(8)") or 0) >= 6:
                    prev_set.add(row["代码"])
    ready_syms = [r["sym"] for r in meta_ready + vcp_ready]
    new_names = [x for x in dict.fromkeys(ready_syms) if x not in prev_set] if prev_files else []

    ms = market_state()
    state = ms["state"] if ms else "（未知：还没有大盘报告）"

    # ---- Markdown ----
    def er_txt(r):
        return f"⚠ {r['er_days']} 天后" if soon(r) else ("—" if r["er_days"] is None else f"{r['er_days']} 天后")

    def meta_md(rows):
        out = ["| 股票 | 行业 | 收盘 | 动能日 | 回调 | 突破位 | 建议止损 | 止损 | 到前高 | 优势 | 每10万股数 | 业绩 | 优势明细 |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            m, mo = r["meta"], r["mom"]
            ok = "、".join(k for k, b in m["edges"].items() if b)
            out.append(f"| {r['sym']} | {r['industry'][:18]} | {r['close']} | {mo['date']:%m-%d} +{mo['size']*100:.0f}%（量 {mo['vr']:.1f}x） | "
                       f"{m['pb']}% | {m['breakout']} | {m['stop']} | {m['risk']}% | {m['rr']}R | {m['n_edges']}/8 | "
                       f"{shares_per_100k(r['close'], m['stop'])} | {er_txt(r)} | {ok} |")
        return out

    def vcp_md(rows):
        out = ["| 股票 | 行业 | 收盘 | 突破点 | 距突破点 | 建议止损 | 止损 | 得分 | 状态 | 每10万股数 | 业绩 | 未通过项 |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            v = r["vcp"]
            out.append(f"| {r['sym']} | {r['industry'][:18]} | {r['close']} | {v['pivot']} | {v['ext']}% | {v['stop']} | {v['risk']}% | "
                       f"{v['score']}/8 | {v['status']} | {shares_per_100k(v['pivot'], v['stop'])} | {er_txt(r)} | {v['fails'] or '—'} |")
        return out

    lines = [f"# J Law 每日选股 {today}", "",
             f"**大盘状态**：{state}" + (f"（大盘报告日期 {ms['date']}）" if ms else ""),
             f"**股票池**：第二阶段 + 日均成交额 ≥ 1 亿美元 **{len(res)} 只**；动能事件 {sum(1 for r in res if r['mom'])} 只；"
             f"VCP 相对强度层 {len(vcp_pool)} 只（1M ≥{s['min1m']:.1f}%、6M ≥{s['min6m']:.1f}%）", ""]
    if "血汗钱" in state:
        lines += ["> 🔴 血汗钱：以现金为主、冬眠。名单只作观察，留意谁在逆市走强。", ""]
    elif "警戒" in state:
        lines += ["> 🟡 警戒：只做优势最多、止损最窄的形态，单笔风险减半。", ""]
    lines += [f"## A1. META 回调就绪（动能后低量回调到均线/突破位，止损 ≤5%，优势 ≥4）：{len(meta_ready)} 只", ""]
    lines += meta_md(meta_ready[:15]) if meta_ready else ["今天没有符合条件的股票。"]
    lines += ["", f"## A2. VCP 突破就绪（得分 ≥6、接近突破点、止损 ≤8%）：{len(vcp_ready)} 只", ""]
    lines += vcp_md(vcp_ready[:15]) if vcp_ready else ["今天没有符合条件的股票。"]
    lines += ["", f"## B. 观察名单：META {len(meta_watch)} 只、VCP {len(vcp_watch)} 只", ""]
    lines += meta_md(meta_watch[:10]) if meta_watch else []
    lines += [""] + (vcp_md(vcp_watch[:10]) if vcp_watch else [])
    lines += ["", f"## 热门产业组（同一行业 ≥{HOT_GROUP_MIN} 只出现动能或强势）", ""]
    lines += [f"- **{k}**（{len(v)}）：{'、'.join(v[:12])}" for k, v in sorted(hot.items(), key=lambda x: -len(x[1]))[:10]] or ["无。"]
    lines += ["", "## 近 5 日新的动能事件（等它低量回调到 META 区间）", ""]
    lines += [f"- {r['sym']}（{r['industry'][:20]}）{r['mom']['date']:%m-%d} +{r['mom']['size']*100:.0f}%，量 {r['mom']['vr']:.1f}x"
              + ("，业绩催化" if r["catalyst"] else "") for r in fresh_mom[:15]] or ["无。"]
    if new_names:
        lines += ["", "**新进入就绪名单**（对比上一份）：" + "、".join(new_names[:20])]
    lines += ["", "## 下单前仍须人工确认",
              "- META 回调：确认动能有催化剂（业绩、指引、新产品、主题），回调成交量明显萎缩，股价守在 10/20 天线或突破位区间",
              "- VCP 突破：最后收缩 < 10%，带量突破才买，高于突破点 5% 不追",
              f"- 止损 3–5%（META）/ ≤8%（VCP），目标 ≥ 3–5R；单笔风险约账户 {RISK_PER_TRADE*100:.2f}%（表中「每10万股数」按此计算）",
              "- 同组其他股票也强才可靠；⚠ 14 天内有业绩不建大仓；大盘不利时降低仓位",
              "", "优势定义：动能事件 = 近 30 日内单日 ≥8%（市值 ≥2,000 亿为 5%）或跳空 ≥5% 且量 ≥1.5 倍，或 3 日 ≥12% 且连续放量；"
              "低量回调 = 回调期均量 < 动能日量 60% 且 ≤ 50 日均量 1.1 倍；均线支撑 = 距 10/20 SMA 或 20 EMA ≤3%；"
              "突破位 = 动能前 40 日最高点；周线 20 周线以 100 日均线近似。程序化近似，仅供学习，不构成投资建议。"]
    md = os.path.join(SCREEN_DIR, f"{today}.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ---- CSV ----
    with open(os.path.join(SCREEN_DIR, f"{today}.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["代码", "名称", "板块", "行业", "收盘价", "日均成交额(百万)", "RS近新高", "跌日超额%", "1个月%", "6个月%",
                    "动能日", "动能幅度%", "动能量比", "业绩催化", "META回调%", "突破位", "META止损", "META止损%", "META到前高R", "META优势",
                    "VCP突破点", "VCP距突破点%", "VCP止损", "VCP止损%", "得分(8)", "VCP状态", "业绩天数", "就绪"])
        for r in sorted(res, key=lambda r: r["sym"]):
            m, mo, v = r["meta"] or {}, r["mom"] or {}, r["vcp"]
            ready = "META" if r in meta_ready else ("VCP" if r in vcp_ready else "")
            w.writerow([r["sym"], r["name"], r["sector"], r["industry"], r["close"], round(r["dollar20"] / 1e6), r["rs_near_high"],
                        r["rs_down"], r["p1m"], r["p6m"], mo.get("date", ""), round(mo["size"] * 100, 1) if mo else "",
                        round(mo["vr"], 1) if mo else "", r["catalyst"], m.get("pb", ""), m.get("breakout", ""), m.get("stop", ""),
                        m.get("risk", ""), m.get("rr", ""), m.get("n_edges", ""), v["pivot"], v["ext"], v["stop"], v["risk"],
                        v["score"], v["status"], r["er_days"], ready])

    chart_items = [(r, "META") for r in meta_ready[:6]] + [(r, "VCP") for r in vcp_ready[:3]]
    chart_items += [(r, "META") for r in meta_watch] + [(r, "VCP") for r in vcp_watch]
    png = os.path.join(SCREEN_DIR, f"{today}_图表.png")
    has_png = charts(chart_items[:9], png)
    html_path = os.path.join(SCREEN_DIR, f"{today}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(today, state, ms, s, len(res), sum(1 for r in res if r["mom"]), len(vcp_pool), meta_ready, vcp_ready,
                           meta_watch, vcp_watch, hot, fresh_mom, new_names, png if has_png else None))

    print(json.dumps({"html": html_path, "date": str(today), "market_state": state, "universe": len(res),
                      "meta_ready": [(r["sym"], r["meta"]["n_edges"], r["meta"]["risk"], r["er_days"]) for r in meta_ready[:10]],
                      "vcp_ready": [(r["sym"], r["vcp"]["score"], r["vcp"]["risk"], r["er_days"]) for r in vcp_ready[:10]],
                      "watch": [r["sym"] for r in (meta_watch + vcp_watch)[:12]],
                      "hot_groups": {k: len(v) for k, v in sorted(hot.items(), key=lambda x: -len(x[1]))[:6]},
                      "fresh_momentum": [r["sym"] for r in fresh_mom[:10]], "new_ready": new_names[:10],
                      "report": md, "chart": png if has_png else None}, ensure_ascii=False))


def build_html(today, state, ms, s, n_univ, n_mom, n_vcp, meta_ready, vcp_ready, meta_watch, vcp_watch, hot, fresh_mom, new_names, png_path):
    """单文件 HTML（内联样式，图表以 base64 内嵌）。"""
    import base64
    import html as h
    key = state[0] if state and state[0] in "🔴🟡🟢" else None
    col = {"🔴": ("#C62828", "#FDECEA"), "🟡": ("#B26A00", "#FFF4E0"), "🟢": ("#2E7D32", "#E8F5E9")}.get(key, ("#555", "#f0f0f0"))
    advice = {"🔴": "以现金为主、冬眠：名单只作观察，留意谁在逆市走强，不建议新开大仓。",
              "🟡": "警戒：只做优势最多、止损最窄的形态，单笔风险减半。",
              "🟢": "躺赚：动能后低量回调到 META 区间、或 VCP 带量突破时买入领导股。"}.get(key, "先确认大盘状态再操作。")
    td = 'style="padding:6px 8px;border-bottom:1px solid #eee;white-space:nowrap;"'
    tdw = 'style="padding:6px 8px;border-bottom:1px solid #eee;color:#666;font-size:12px;"'
    th = 'style="padding:6px 8px;background:#f5f5f5;text-align:left;font-weight:600;border-bottom:1px solid #ddd;white-space:nowrap;"'

    def er(r):
        if r["er_days"] is not None and 0 <= r["er_days"] <= 14:
            return f'<span style="color:#C62828;font-weight:600;">⚠ {r["er_days"]} 天后</span>'
        return "—" if r["er_days"] is None else f'{r["er_days"]} 天后'

    def link(sym):
        return (f'<a href="{h.escape(tv_url(sym))}" target="_blank" rel="noopener" title="在 TradingView 打开 {h.escape(sym)} 的图表" '
                f'style="color:#1565C0;text-decoration:none;font-weight:700;">{h.escape(sym)} <span style="font-size:11px;">📈</span></a>')

    def name(r):
        return f'{link(r["sym"])}<br><span style="color:#888;font-size:11px;">{h.escape(r["name"][:22])}</span>'

    def wrap(head, body):
        hd = "".join(f"<th {th}>{x}</th>" for x in head)
        return f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:13px;"><tr>{hd}</tr>{body}</table></div>'

    def meta_tbl(rows):
        if not rows:
            return '<p style="color:#777;">今天没有符合条件的股票。</p>'
        body = ""
        for r in rows:
            m, mo = r["meta"], r["mom"]
            ok = "、".join(k for k, b in m["edges"].items() if b)
            rc = "#2E7D32" if m["risk"] <= META_MAX_RISK else "#C62828"
            body += (f'<tr><td {td}>{name(r)}</td><td {td}>{h.escape(r["industry"][:20])}</td><td {td}>{r["close"]}</td>'
                     f'<td {td}>{mo["date"]:%m-%d} <b style="color:#2E7D32;">+{mo["size"]*100:.0f}%</b><br><span style="color:#888;font-size:11px;">量 {mo["vr"]:.1f}x{"，业绩" if r["catalyst"] else ""}</span></td>'
                     f'<td {td}>{m["pb"]}%</td><td {td}><b>{m["breakout"]}</b></td><td {td}>{m["stop"]}</td>'
                     f'<td {td}><span style="color:{rc};">{m["risk"]}%</span></td><td {td}>{m["rr"]}R</td>'
                     f'<td {td}><b>{m["n_edges"]}/8</b></td><td {td}>{shares_per_100k(r["close"], m["stop"])}</td><td {td}>{er(r)}</td>'
                     f'<td {tdw}>{h.escape(ok)}</td></tr>')
        return wrap(("股票", "行业", "收盘", "动能日", "回调", "突破位", "建议止损", "止损", "到前高", "优势", "每10万股数", "业绩", "优势明细"), body)

    def vcp_tbl(rows):
        if not rows:
            return '<p style="color:#777;">今天没有符合条件的股票。</p>'
        body = ""
        for r in rows:
            v = r["vcp"]
            rc = "#2E7D32" if v["risk"] <= VCP_MAX_RISK else "#C62828"
            body += (f'<tr><td {td}>{name(r)}</td><td {td}>{h.escape(r["industry"][:20])}</td><td {td}>{r["close"]}</td>'
                     f'<td {td}><b>{v["pivot"]}</b></td><td {td}>{v["ext"]}%</td><td {td}>{v["stop"]}</td>'
                     f'<td {td}><span style="color:{rc};">{v["risk"]}%</span></td><td {td}><b>{v["score"]}/8</b></td><td {td}>{v["status"]}</td>'
                     f'<td {td}>{shares_per_100k(v["pivot"], v["stop"])}</td><td {td}>{er(r)}</td><td {tdw}>{h.escape(v["fails"] or "—")}</td></tr>')
        return wrap(("股票", "行业", "收盘", "突破点", "距突破点", "建议止损", "止损", "得分", "状态", "每10万股数", "业绩", "未通过项"), body)

    img = ""
    if png_path and os.path.exists(png_path):
        with open(png_path, "rb") as f:
            img = ('<h3 style="margin:22px 0 8px;">图表（META：橙色虚线 = 突破位；VCP：橙色虚线 = 突破点；紫色点线 = 建议止损）</h3>'
                   f'<img alt="候选股图表" style="width:100%;border:1px solid #eee;" src="data:image/png;base64,{base64.b64encode(f.read()).decode()}">')
    hot_html = "".join(f'<li><b>{h.escape(k)}</b>（{len(v)}）：{"、".join(link(x) for x in v[:12])}</li>'
                       for k, v in sorted(hot.items(), key=lambda x: -len(x[1]))[:10]) or "<li>无</li>"
    fresh_html = "".join(f'<li>{link(r["sym"])}（{h.escape(r["industry"][:20])}）{r["mom"]["date"]:%m-%d} '
                         f'<span style="color:#2E7D32;">+{r["mom"]["size"]*100:.0f}%</span>，量 {r["mom"]["vr"]:.1f}x{"，业绩催化" if r["catalyst"] else ""}</li>'
                         for r in fresh_mom[:15]) or "<li>无</li>"
    new_line = (f'<p style="margin:10px 0 0;"><b>新进入就绪名单：</b>{h.escape("、".join(new_names[:20]))}</p>' if new_names else "")
    ms_date = f'（大盘报告日期 {ms["date"]}）' if ms else ""
    sec = lambda t, c: f'<h3 style="margin:22px 0 8px;color:{c};">{t}</h3>'
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>J Law 每日选股 {today}</title></head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222;">
<div style="max-width:1080px;margin:0 auto;padding:16px;">
<div style="background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e3e3e3;">
<div style="background:{col[1]};border-left:6px solid {col[0]};padding:16px 18px;">
<div style="font-size:13px;color:#555;">J Law 每日选股 · {today}</div>
<div style="font-size:24px;font-weight:700;margin-top:4px;">META 回调 <span style="color:#2E7D32;">{len(meta_ready)}</span> · VCP 突破 <span style="color:#2E7D32;">{len(vcp_ready)}</span> · 观察 <span style="color:#B26A00;">{len(meta_watch) + len(vcp_watch)}</span></div>
<div style="margin-top:6px;font-size:15px;"><b>大盘：</b><span style="color:{col[0]};font-weight:700;">{h.escape(state)}</span> <span style="color:#777;font-size:12px;">{ms_date}</span></div>
<div style="margin-top:6px;font-size:14px;line-height:1.6;"><b>建议：</b>{advice}</div></div>
<div style="padding:16px 18px;font-size:14px;line-height:1.6;">
<p style="margin:0;"><b>股票池：</b>第二阶段 + 日均成交额 ≥ 1 亿美元 <b>{n_univ}</b> 只 · 有动能事件 <b>{n_mom}</b> 只 · VCP 相对强度层 <b>{n_vcp}</b> 只
<span style="color:#777;font-size:12px;">（1M ≥{s['min1m']:.1f}%、6M ≥{s['min6m']:.1f}%；标普 1M {s['spy1m']:+.1f}%、6M {s['spy6m']:+.1f}%）</span></p>{new_line}
{sec("A1. META 回调就绪（动能后低量回调到均线 / 突破位，止损 ≤5%，优势 ≥4）", "#2E7D32")}{meta_tbl(meta_ready[:15])}
{sec("A2. VCP 突破就绪（得分 ≥6、接近突破点、止损 ≤8%）", "#2E7D32")}{vcp_tbl(vcp_ready[:15])}
{sec("B. 观察名单 · META（优势 ≥3）", "#B26A00")}{meta_tbl(meta_watch[:10])}
{sec("B. 观察名单 · VCP（得分 ≥5）", "#B26A00")}{vcp_tbl(vcp_watch[:10])}
<div style="display:flex;flex-wrap:wrap;gap:16px;">
<div style="flex:1 1 360px;">{sec(f"热门产业组（同一行业 ≥{HOT_GROUP_MIN} 只）", "#1F4E78")}<ul style="margin:0;padding-left:20px;">{hot_html}</ul></div>
<div style="flex:1 1 360px;">{sec("近 5 日新的动能事件（等低量回调）", "#1F4E78")}<ul style="margin:0;padding-left:20px;">{fresh_html}</ul></div></div>
{img}
<p style="margin:14px 0 0;font-size:12px;color:#555;">📈 点股票代码会在新分页打开 TradingView 日线图，方便研究形态。</p>
<h3 style="margin:22px 0 6px;">下单前仍须人工确认</h3>
<ul style="margin:0;padding-left:20px;">
<li>META 回调：动能要有催化剂（业绩、指引、新产品、主题），回调成交量明显萎缩，股价守在 10/20 天线或突破位区间（均线是区间，不是一条线）</li>
<li>VCP 突破：最后收缩 &lt; 10%，带量突破才买，高于突破点 5% 不追</li>
<li>止损 3–5%（META）/ ≤ 8%（VCP），目标 ≥ 3–5R；单笔风险约账户 {RISK_PER_TRADE*100:.2f}%（「每10万股数」按此计算）</li>
<li>同组其他股票也强才可靠；<span style="color:#C62828;">⚠</span> 14 天内有业绩不建大仓；大盘不利时降低仓位</li></ul></div>
<div style="padding:12px 18px;background:#fafafa;border-top:1px solid #eee;font-size:11px;color:#888;line-height:1.5;">
动能事件 = 近 30 日内单日 ≥8%（市值 ≥2,000 亿为 5%）或跳空 ≥5% 且量 ≥1.5 倍，或 3 日 ≥12% 且连续放量。低量回调 = 回调期均量 &lt; 动能日量 60% 且 ≤ 50 日均量 1.1 倍。
均线支撑 = 距 10/20 SMA 或 20 EMA ≤3%。突破位 = 动能前 40 日最高点。RS = 近 126 日 RS 线 5% 内新高，或近 20 日标普下跌日平均跑赢标普。周线 20 周线以 100 日均线近似。
热门产业组 = 同一细分行业 ≥3 只有动能事件或通过相对强度层。依据 TTT 课程与 J Law 2026 年 Chart Fanatics 访问整理的程序化近似。<br>仅供学习，不构成投资建议。</div>
</div></div></body></html>"""


if __name__ == "__main__":
    main()
