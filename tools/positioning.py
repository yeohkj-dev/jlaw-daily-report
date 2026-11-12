"""大资金在哪里买卖：CFTC 期货持仓（真实数据）+ CTA 趋势跟踪模型（估算）。

1. CFTC「Traders in Financial Futures」周报（免费，publicreporting.cftc.gov）：每周二的持仓，周五公布。
   杠杆基金（对冲基金、CTA）和资产管理人（共同基金、退休金）在 标普 500 / 纳指 100 / 罗素 2000 迷你期货的
   多空口数、净持仓、比上周变化、按当时期货价格换算的美元金额，以及在过去 3 年里算偏多还是偏空（百分位）。
2. CTA 模型（估算，不是真实数据）：CTA 多用趋势跟踪，最常见是看 20 / 60 / 120 / 250 个交易日的涨跌。
   每个周期：现价高于 N 天前 = 做多，低于 = 做空；「翻转价」= 明天会滚进来的那个 N 天前的价格，标普跌破就从买变卖。
   仓位 = 4 个信号平均 × 波动调整（目标年化波动 15% ÷ 近 20 天实际波动，最多 1 倍）。
   金额：假设 CTA 在美股指期货的最大仓位约 1,500 亿美元（公开估计大约 1,000–2,000 亿，各家差很多），
   估计「标普跌破某个翻转价」时仓位变化 × 1,500 亿 = 大约会卖多少。只是数量级，请当参考。
用法：python positioning.py [输出目录] → 大盘报告/资金持仓_YYYY-MM-DD.html 和 .json
仅供学习，不构成投资建议。
"""
import datetime as dt
import json
import math
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import yahoo_chart

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFTC = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
# (CFTC 市场名称, 中文, Yahoo 期货代码, 每点美元)
# (CFTC 市场名称, 中文, Yahoo 期货代码, 每点美元, TradingView 代码)
MARKETS = [("E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE", "标普 500 迷你期货", "ES=F", 50, "CME_MINI:ES1!"),
           ("NASDAQ MINI - CHICAGO MERCANTILE EXCHANGE", "纳指 100 迷你期货", "NQ=F", 20, "CME_MINI:NQ1!"),
           ("RUSSELL E-MINI - CHICAGO MERCANTILE EXCHANGE", "罗素 2000 迷你期货", "RTY=F", 50, "CME_MINI:RTY1!")]
CFTC_TXT = "https://www.cftc.gov/dea/futures/financial_lf.htm"     # 同一份周报的官方文字版（第二来源）
CBOE_SPX = "https://cdn.cboe.com/api/global/delayed_quotes/charts/historical/_SPX.json"   # 标普 500 日线（第二来源）
CTA_MAX = 150e9                 # 假设：CTA 在美股指期货的最大仓位（美元）
LOOKBACKS = (20, 60, 120, 250)
TARGET_VOL = 0.15


def cftc(name, weeks=160):
    q = CFTC + "?" + urllib.parse.urlencode({"market_and_exchange_names": name, "$order": "report_date_as_yyyy_mm_dd DESC",
                                              "$limit": str(weeks)})
    rows = json.load(urllib.request.urlopen(urllib.request.Request(q, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))
    out = []
    for r in rows:
        f = lambda k: int(float(r.get(k) or 0))
        out.append(dict(date=r["report_date_as_yyyy_mm_dd"][:10], lev_l=f("lev_money_positions_long"), lev_s=f("lev_money_positions_short"),
                        am_l=f("asset_mgr_positions_long"), am_s=f("asset_mgr_positions_short"), oi=f("open_interest_all")))
    return out


def _get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()


def check_cftc_txt(rows):
    """CFTC 官网文字版周报逐项核对：两边持仓日期相同时，杠杆基金、资产管理人的净持仓和比上周要完全一样。
    文字版每个市场 Positions 下一行 14 个数：交易商 多/空/套利、资产管理人 多/空/套利、杠杆基金 多/空/套利、其他 多/空/套利、非报告 多/空。"""
    try:
        import re
        txt = _get(CFTC_TXT).decode("latin-1")
        m = re.search(r"Positions as of (\w+ \d+, \d{4})", txt)
        tdate = str(dt.datetime.strptime(m.group(1), "%B %d, %Y").date()) if m else None
        bad, n = [], 0
        for name, zh, *_ in MARKETS:
            r = next((x for x in rows if x["zh"] == zh), None)
            i = txt.find(name)
            if r is None or i < 0 or r["date"] != tdate:
                continue
            blk = txt[i:i + 2500]
            pos = [int(x.replace(",", "")) for x in re.search(r"Positions[ \t]*\r?\n(.*)\r?\n", blk).group(1).split()]
            chg = [int(x.replace(",", "")) for x in re.search(r"Changes from:.*\r?\n(.*)\r?\n", blk).group(1).split()]
            want = dict(am=pos[3] - pos[4], lev=pos[6] - pos[7], am_chg=chg[3] - chg[4], lev_chg=chg[6] - chg[7])
            n += 1
            bad += [f"{zh} {k} {r[k]:,} vs 官网 {v:,}" for k, v in want.items() if r[k] != v]
        if not n:
            return dict(name="CFTC vs 官网文字版", ok=False, critical=False, detail=f"官网文字版是 {tdate}，和数据库日期不同，这次没比")
        return dict(name="CFTC vs 官网文字版", ok=not bad, critical=False,
                    detail=f"{tdate} {n} 个市场 × 净持仓 / 比上周 " + ("全部一致" if not bad else "不一致：" + "；".join(bad)))
    except Exception as e:
        return dict(name="CFTC vs 官网文字版", ok=False, critical=False, detail=f"官网取不到（{type(e).__name__}）")


def check_futures_tv(last_px):
    """Yahoo 期货最新价 vs TradingView 连续合约（差 ≤0.3%）。美元换算用的是 Yahoo 的价格。"""
    try:
        from common import fetch_json      # 期货要用 global 选股器（america 没有期货）
        data = fetch_json("https://scanner.tradingview.com/global/scan",
                          body={"symbols": {"tickers": [m[4] for m in MARKETS]}, "columns": ["close"]})["data"]
        tv = {x["s"]: x["d"][0] for x in data if x["d"][0]}
        out, bad = [], []
        for name, zh, ysym, mult, tsym in MARKETS:
            y, t = last_px.get(ysym), tv.get(tsym)
            if y and t:
                out.append(f"{ysym} {y:,.2f} / TV {t:,.2f}")
                if abs(y / t - 1) > 0.003:
                    bad.append(ysym)
        return dict(name="期货价格 Yahoo vs TradingView", ok=bool(out) and not bad, critical=False,
                    detail="；".join(out) + (f"（{'、'.join(bad)} 差 >0.3%）" if bad else ""))
    except Exception as e:
        return dict(name="期货价格 Yahoo vs TradingView", ok=False, critical=False, detail=f"TradingView 取不到（{type(e).__name__}）")


def check_cta_cboe(cta):
    """CTA 模型用的标普收盘（Yahoo）vs CBOE 官方标普 500 日线：最近 260 天逐日比（≤0.05%），4 个翻转价用 CBOE 再算一次。"""
    try:
        cb = {x["date"]: float(x["close"]) for x in json.loads(_get(CBOE_SPX))["data"]}
        y = cta["_px"]
        ds = sorted(y)[-260:]
        cbs = sorted(cb)
        late = [str(d) for d in ds if str(d) > cbs[-1]]          # CBOE 还没更新到的最新几天：不算错，只比两边都有的日子
        both = [d for d in ds if str(d) <= cbs[-1]]
        miss = [str(d) for d in both if str(d) not in cb]
        off = [str(d) for d in both if str(d) in cb and abs(y[d] / cb[str(d)] - 1) > 0.0005]
        flips, yds = [], sorted(y)
        for n in LOOKBACKS:
            fd = str(yds[-n])                                    # 翻转价是哪一天的收盘
            if fd in cb and abs(cb[fd] / cta["sig"][n]["flip"] - 1) > 0.0005:
                flips.append(f"{n} 天 {cta['sig'][n]['flip']:,.0f} vs CBOE {cb[fd]:,.0f}")
        ok = not miss and not off and not flips and len(late) <= 1 and len(both) >= 250
        det = (f"{len(both)} 天收盘逐日一致、4 个翻转价相同" + (f"（CBOE 还没有 {late[-1]}，这一天没比）" if late else f"（CBOE 最新 {cbs[-1]}）") if ok else
               f"CBOE 最新 {cbs[-1]}；缺 {len(miss)} 天、差 >0.05% {len(off)} 天、CBOE 落后 {len(late)} 天" + (f"；翻转价不同：{'；'.join(flips)}" if flips else ""))
        return dict(name="CTA 标普收盘 vs CBOE", ok=ok, critical=False, detail=det)
    except Exception as e:
        return dict(name="CTA 标普收盘 vs CBOE", ok=False, critical=False, detail=f"CBOE 取不到（{type(e).__name__}）")


def closes(sym, rng="2y"):
    bars, _ = yahoo_chart(sym, rng, "1d")
    return {dt.datetime.fromtimestamp(b["t"], dt.timezone.utc).date(): b["c"] for b in bars}


def pct_rank(x, xs):
    return sum(1 for v in xs if v <= x) / len(xs) * 100 if xs else None


def cta_model():
    px = closes("^GSPC", "2y")
    ds = sorted(px)
    c = [px[d] for d in ds]
    last = c[-1]
    sig = {}
    for n in LOOKBACKS:
        ref_today = c[-1 - n]
        flip = c[-n]                                   # 明天的比较价（滚进来的那一天）
        sig[n] = dict(now=1 if last > ref_today else -1, flip=flip, dist=(flip / last - 1) * 100)
    rets = [math.log(c[i] / c[i - 1]) for i in range(len(c) - 20, len(c))]
    vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 * math.sqrt(252)
    scale = min(1.0, TARGET_VOL / vol) if vol else 1.0
    pos = sum(s["now"] for s in sig.values()) / len(sig) * scale

    def pos_at(price):
        return sum((1 if price > (c[-n]) else -1) for n in LOOKBACKS) / len(LOOKBACKS) * scale
    # 情景：标普跌到每个「在现价下面」的翻转价下方 0.1% 时，仓位变成多少、大约卖多少
    scen = []
    for n in sorted(LOOKBACKS, key=lambda n: -sig[n]["flip"]):
        f = sig[n]["flip"]
        if f < last and sig[n]["now"] == 1:
            p1 = pos_at(f * 0.999)
            scen.append(dict(n=n, level=f, dist=(f / last - 1) * 100, pos=p1, flow=(p1 - pos) * CTA_MAX))
    up = []
    for n in sorted(LOOKBACKS, key=lambda n: sig[n]["flip"]):
        f = sig[n]["flip"]
        if f > last and sig[n]["now"] == -1:
            p1 = pos_at(f * 1.001)
            up.append(dict(n=n, level=f, dist=(f / last - 1) * 100, pos=p1, flow=(p1 - pos) * CTA_MAX))
    return dict(_px=px, date=str(ds[-1]), last=last, sig=sig, vol=vol * 100, scale=scale, pos=pos, usd=pos * CTA_MAX, down=scen, up=up)


def build(today):
    rows, checks = [], []
    last_px = {}
    for name, zh, ysym, mult, tsym in MARKETS:
        try:
            hist = cftc(name)
        except Exception as e:
            checks.append(dict(name=f"CFTC {zh}", ok=False, critical=False, detail=f"取不到（{type(e).__name__}）"))
            continue
        if len(hist) < 2:
            continue
        try:
            fpx = closes(ysym, "5y")
        except Exception:
            fpx = {}

        def price_on(d):
            d = dt.date.fromisoformat(d)
            ks = [k for k in fpx if k <= d]
            return fpx[max(ks)] if ks else None
        cur, prev = hist[0], hist[1]
        p = price_on(cur["date"])
        if fpx:
            last_px[ysym] = fpx[max(fpx)]
        lev = [h["lev_l"] - h["lev_s"] for h in hist]
        am = [h["am_l"] - h["am_s"] for h in hist]
        rows.append(dict(zh=zh, date=cur["date"], price=p, mult=mult,
                         lev=lev[0], lev_chg=lev[0] - lev[1], lev_usd=lev[0] * mult * p if p else None, lev_pct=pct_rank(lev[0], lev),
                         am=am[0], am_chg=am[0] - am[1], am_usd=am[0] * mult * p if p else None, am_pct=pct_rank(am[0], am), oi=cur["oi"]))
        age = (today - dt.date.fromisoformat(cur["date"])).days
        checks.append(dict(name=f"CFTC {zh}", ok=age <= 11, critical=False, detail=f"{cur['date']} 的持仓（{age} 天前）" + ("" if p else "；没有期货价格，不能换算美元")))
    try:
        cta = cta_model()
        checks.append(dict(name="CTA 模型（标普 500）", ok=True, critical=False, detail=f"{cta['date']} 收盘 {cta['last']:.0f}"))
        checks.append(check_cta_cboe(cta))
    except Exception as e:
        cta = None
        checks.append(dict(name="CTA 模型（标普 500）", ok=False, critical=False, detail=f"取不到（{type(e).__name__}）"))
    checks.append(check_cftc_txt(rows))
    checks.append(check_futures_tv(last_px))
    if cta:
        cta.pop("_px", None)
    return rows, cta, checks


def html(rows, cta):
    td = 'style="padding:5px 7px;border-bottom:1px solid #eee;white-space:nowrap;"'
    th = 'style="padding:5px 7px;background:#f5f5f5;text-align:left;font-weight:600;border-bottom:1px solid #ddd;white-space:nowrap;"'
    num = lambda x: f"{x:+,}" if x is not None else "—"
    usd = lambda x: "—" if x is None else (f"{x / 1e9:+,.0f} 亿美元".replace("+-", "-") if abs(x) >= 1e9 else f"{x / 1e6:+,.0f} 百万美元")
    usd = lambda x: "—" if x is None else f"{'+' if x >= 0 else '−'}${abs(x) / 1e9:,.0f}B（约 {abs(x) / 1e8:,.0f} 亿美元）"
    col = lambda x: "#2E7D32" if (x or 0) > 0 else "#C62828" if (x or 0) < 0 else "#555"
    pct_txt = lambda p: "—" if p is None else (f"{p:.0f}%（3 年来很偏空）" if p <= 10 else f"{p:.0f}%（3 年来很偏多）" if p >= 90 else f"{p:.0f}%")
    body = ""
    for r in rows:
        body += (f'<tr><td {td}><b>{r["zh"]}</b><br><span style="color:#888;font-size:11px;">{r["date"]}</span></td>'
                 f'<td {td}><b style="color:{col(r["lev"])};">{num(r["lev"])} 口</b><br><span style="font-size:11px;">{usd(r["lev_usd"])}</span></td>'
                 f'<td {td}><span style="color:{col(r["lev_chg"])};">{num(r["lev_chg"])}</span></td><td {td}>{pct_txt(r["lev_pct"])}</td>'
                 f'<td {td}><b style="color:{col(r["am"])};">{num(r["am"])} 口</b><br><span style="font-size:11px;">{usd(r["am_usd"])}</span></td>'
                 f'<td {td}><span style="color:{col(r["am_chg"])};">{num(r["am_chg"])}</span></td><td {td}>{pct_txt(r["am_pct"])}</td></tr>')
    cftc_tbl = (f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12.5px;"><tr>'
                f'<th {th}>期货</th><th {th}>杠杆基金净持仓<br>（对冲基金、CTA）</th><th {th}>比上周</th><th {th}>3 年百分位</th>'
                f'<th {th}>资产管理人净持仓<br>（共同基金、退休金）</th><th {th}>比上周</th><th {th}>3 年百分位</th></tr>{body}</table></div>')
    cta_html = ""
    if cta:
        s = cta["sig"]
        srow = "".join(f'<tr><td {td}>{n} 天</td><td {td}><b style="color:{col(s[n]["now"])};">{"做多" if s[n]["now"] > 0 else "做空"}</b></td>'
                       f'<td {td}>{s[n]["flip"]:,.0f}</td><td {td}>{s[n]["dist"]:+.1f}%</td></tr>' for n in LOOKBACKS)
        lines = []
        for x in cta["down"]:
            lines.append(f'标普 <b>跌破 {x["level"]:,.0f}</b>（离现价 {x["dist"]:+.1f}%）：{x["n"]} 天信号转空，模型估计 CTA 卖出约 '
                         f'<b style="color:#C62828;">${abs(x["flow"]) / 1e9:,.0f}B</b>（仓位 {cta["pos"] * 100:+.0f}% → {x["pos"] * 100:+.0f}%）')
        for x in cta["up"]:
            lines.append(f'标普 <b>站上 {x["level"]:,.0f}</b>（离现价 {x["dist"]:+.1f}%）：{x["n"]} 天信号转多，模型估计 CTA 买入约 '
                         f'<b style="color:#2E7D32;">${abs(x["flow"]) / 1e9:,.0f}B</b>（仓位 {cta["pos"] * 100:+.0f}% → {x["pos"] * 100:+.0f}%）')
        if not lines:
            lines.append("附近没有翻转价。")
        lines.append('<span style="color:#777;">金额是从现在的仓位算起的累计数：例如跌破第二个价位时，包括跌破第一个价位那部分。</span>')
        cta_html = (f'<p style="margin:10px 0 4px;"><b>CTA 趋势模型（估算）</b>：标普 500 收盘 {cta["last"]:,.0f}（{cta["date"]}），'
                    f'模型仓位 <b style="color:{col(cta["pos"])};">{cta["pos"] * 100:+.0f}%</b>（约 {usd(cta["usd"])}）；近 20 天波动 {cta["vol"]:.0f}%（波动越大仓位越小）。</p>'
                    f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12.5px;"><tr><th {th}>趋势周期</th><th {th}>现在</th>'
                    f'<th {th}>翻转价（明天）</th><th {th}>离现价</th></tr>{srow}</table></div>'
                    '<ul style="margin:6px 0 0;padding-left:20px;font-size:13px;line-height:1.7;">' + "".join(f"<li>{l}</li>" for l in lines) + "</ul>")
    return f"""<h3 style="margin:22px 0 6px;">大资金在哪里买卖</h3>
<p style="margin:0 0 6px;font-size:13px;line-height:1.6;"><b>CFTC 期货持仓（真实数据，每周）</b>：美国商品期货交易委员会每周公布各类机构在股指期货的多空口数。
「杠杆基金」主要是对冲基金和 CTA（趋势跟踪基金），「资产管理人」是共同基金、退休金等长线资金。净持仓 = 多单 − 空单；美元金额按当周期货价格换算（标普每点 $50、纳指 $20、罗素 $50）。</p>
{cftc_tbl}{cta_html}
<p style="margin:6px 0 0;font-size:11px;color:#777;line-height:1.5;">数据核对：CFTC 数字对过 CFTC 官网文字版周报，期货价格对过 TradingView，标普收盘对过 CBOE（结果在页头「数据核对」）。CFTC 是每周二的持仓、周五公布，所以会晚几天。杠杆基金的空单有很大一部分是对冲（例如买股票、卖期货），不一定代表看空。
CTA 部分是<b>模型估算</b>：用 20 / 60 / 120 / 250 天趋势判断买卖，假设 CTA 在美股指期货最大仓位约 1,500 亿美元（公开估计 1,000–2,000 亿，各家差很多），金额只是数量级参考，不是真实成交。仅供学习，不构成投资建议。</p>"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    today = dt.date.today()
    rows, cta, checks = build(today)
    d = os.path.join(OUT_DIR, "大盘报告")
    os.makedirs(d, exist_ok=True)
    base = os.path.join(d, f"资金持仓_{today}")
    frag = html(rows, cta)
    open(base + ".html", "w", encoding="utf-8").write(
        "<!doctype html><html><head><meta charset='utf-8'></head><body style=\"margin:0;font-family:Arial,'Microsoft YaHei',sans-serif;\">"
        "<div style='max-width:960px;margin:0 auto;padding:16px;background:#fff;'>" + frag + "</div></body></html>")
    json.dump(dict(rows=rows, cta={k: v for k, v in (cta or {}).items()}, checks=checks), open(base + ".json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    print(json.dumps({"html": base + ".html", "fragment": frag, "checks": checks}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
