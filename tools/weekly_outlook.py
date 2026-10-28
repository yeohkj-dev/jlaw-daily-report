"""每周市场展望（不用 AI，按规则打分）。

看 9 个因素，每个 +1 / 0 / −1，合计 ≥ +3 = 偏多，≤ −3 = 偏空，其余 = 中性 / 震荡：
  1. SPY 是否在 10 周线之上          2. 10 周线是否在 40 周线之上（J Law 见底信号 5）
  3. 市场宽度一周变化（50 天线以上比例） 4. 市场宽度水平（>60% / <40%）
  5. VIX 水平与一周变化              6. 进攻板块 vs 防守板块（近 1 个月）
  7. 信用风险偏好（HYG / IEF 近 1 个月） 8. 大盘体温计状态（躺赚 / 警戒 / 血汗钱）
  9. 出货日数量（近 20 日 ≥5 个扣分）
另附：主要指数和 11 个板块 ETF 的一周 / 一月 / 三月表现、利率美元油价、下周经济日历和下周公布业绩的大公司。

用法：python weekly_outlook.py [输出目录]
输出：<输出目录>/每周展望/YYYY-MM-DD.html、.json
仅供学习，不构成投资建议。
"""
import csv
import datetime as dt
import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import AMBER, BLUE, GREEN, GREY, RED, TD, TDN, card, check_list_html, esc, fetch_json, h3, pct, table, yahoo_chart
from news_digest import CAL_ZH, calendar, et_offset, to_et

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WK_DIR = os.path.join(OUT_DIR, "每周展望")
HIST = os.path.join(OUT_DIR, "大盘报告", "大盘历史.csv")
INDEXES = [("SPY", "标普 500"), ("QQQ", "纳斯达克 100"), ("IWM", "罗素 2000（小盘）"), ("DIA", "道琼斯")]
SECTORS = [("XLK", "科技", "进攻"), ("XLY", "可选消费", "进攻"), ("XLC", "通讯服务", "进攻"), ("XLF", "金融", "进攻"),
           ("XLI", "工业", "进攻"), ("XLB", "原材料", "进攻"), ("XLE", "能源", "其他"), ("XLV", "医疗保健", "防守"),
           ("XLP", "必需消费", "防守"), ("XLU", "公用事业", "防守"), ("XLRE", "房地产", "防守")]
MACRO = [("^TNX", "10 年期美债收益率"), ("DX-Y.NYB", "美元指数"), ("CL=F", "WTI 原油"), ("GC=F", "黄金"), ("^VIX", "VIX"),
         ("HYG", "高收益债 ETF"), ("IEF", "7–10 年国债 ETF")]


def perf(sym):
    try:
        d, _ = yahoo_chart(sym, "1y", "1d")
        w, _ = yahoo_chart(sym, "2y", "1wk")
    except Exception:
        return sym, None
    c = [x["c"] for x in d]
    wc = [x["c"] for x in w]

    def back(n):
        return (c[-1] / c[-1 - n] - 1) * 100 if len(c) > n else None
    ma10 = sum(wc[-10:]) / 10 if len(wc) >= 10 else None
    ma40 = sum(wc[-40:]) / 40 if len(wc) >= 40 else None
    ma40_prev = sum(wc[-44:-4]) / 40 if len(wc) >= 44 else None
    return sym, dict(close=c[-1], w1=back(5), m1=back(21), m3=back(63), ma10=ma10, ma40=ma40,
                     ma40_up=ma40 and ma40_prev and ma40 > ma40_prev, last=dt.datetime.fromtimestamp(d[-1]["t"], dt.timezone.utc))


def load_hist():
    try:
        with open(HIST, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def upcoming_earnings(days=8):
    files = sorted(glob.glob(os.path.join(OUT_DIR, "业绩估值", "20??-??-??.json")))
    if not files:
        return []
    with open(files[-1], encoding="utf-8") as f:
        data = json.load(f)
    today = dt.date.today()
    out = []
    for sec, rs in data.items():
        for r in rs:
            if r.get("next_er") and 0 <= (dt.date.fromisoformat(r["next_er"]) - today).days <= days:
                out.append((r["next_er"], r["sym"], r.get("name", ""), sec))
    return sorted(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(WK_DIR, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    syms = [s for s, _ in INDEXES] + [s for s, _, _ in SECTORS] + [s for s, _ in MACRO]
    with ThreadPoolExecutor(8) as ex:
        P = dict(ex.map(perf, syms))
    hist = load_hist()
    last = hist[-1] if hist else None
    week_ago = None
    if hist:
        cutoff = str(dt.date.today() - dt.timedelta(days=6))
        older = [h for h in hist if h["date"] <= cutoff]
        week_ago = older[-1] if older else hist[0]

    factors = []

    def add(name, score, fact):
        factors.append(dict(name=name, score=score, fact=fact))
    spy = P.get("SPY")
    if spy and spy["ma10"]:
        add("SPY 与 10 周线", 1 if spy["close"] > spy["ma10"] else -1,
            f"SPY {spy['close']:.2f}，10 周线 {spy['ma10']:.2f}（{'上方' if spy['close'] > spy['ma10'] else '下方'}）")
    if spy and spy["ma40"]:
        up = spy["ma10"] > spy["ma40"]
        add("10 周线 vs 40 周线", 1 if up else -1,
            f"10 周线 {spy['ma10']:.2f} {'>' if up else '<'} 40 周线 {spy['ma40']:.2f}；40 周线{'向上' if spy['ma40_up'] else '向下或走平'}")
    if last and week_ago and last is not week_ago:
        d = float(last["above50"]) - float(week_ago["above50"])
        add("市场宽度一周变化", 1 if d >= 3 else -1 if d <= -3 else 0,
            f"50 天线以上比例 {float(week_ago['above50']):.1f}%（{week_ago['date']}）→ {float(last['above50']):.1f}%（{last['date']}），{d:+.1f} 点")
    if last:
        b = float(last["above50"])
        add("市场宽度水平", 1 if b > 60 else -1 if b < 40 else 0, f"{b:.1f}% 的大型股在 50 天线之上")
    vix = P.get("^VIX")
    if vix:
        s = 1 if vix["close"] < 18 else -1 if vix["close"] > 25 else 0
        if vix["w1"] is not None and vix["w1"] > 20:
            s = -1
        add("VIX 恐慌指数", s, f"VIX {vix['close']:.1f}，一周 {vix['w1']:+.0f}%" if vix["w1"] is not None else f"VIX {vix['close']:.1f}")
    off = [P[s]["m1"] for s, _, k in SECTORS if k == "进攻" and P.get(s) and P[s]["m1"] is not None]
    dfn = [P[s]["m1"] for s, _, k in SECTORS if k == "防守" and P.get(s) and P[s]["m1"] is not None]
    if off and dfn:
        gap = sum(off) / len(off) - sum(dfn) / len(dfn)
        add("进攻 vs 防守板块（1 个月）", 1 if gap > 1 else -1 if gap < -1 else 0,
            f"进攻板块平均 {sum(off)/len(off):+.1f}%，防守板块平均 {sum(dfn)/len(dfn):+.1f}%（差 {gap:+.1f} 点）")
    hyg, ief = P.get("HYG"), P.get("IEF")
    if hyg and ief and hyg["m1"] is not None and ief["m1"] is not None:
        g = hyg["m1"] - ief["m1"]
        add("信用风险偏好（HYG − IEF，1 个月）", 1 if g > 0.5 else -1 if g < -0.5 else 0,
            f"高收益债 {hyg['m1']:+.1f}%，国债 {ief['m1']:+.1f}%，差 {g:+.1f} 点")
    if last:
        st = last["state"]
        add("大盘体温计", 1 if "躺赚" in st else -1 if "血汗钱" in st else 0, f"{st}（{last['date']}）")
        dd = int(last.get("spy_dist") or 0)
        add("出货日（SPY 近 20 日）", -1 if dd >= 5 else 0, f"{dd} 个")
    total = sum(f["score"] for f in factors)
    if total >= 3:
        verdict, col, bg = "偏多", GREEN, "#E8F5E9"
        plan = "可以按检查清单 D 在突破点买入领导股；顺手时逐步加仓。仍要设止损，留意下周高影响力数据。"
        turn = "如果 SPY 跌破 10 周线，或宽度跌回 50% 以下，就降为中性。"
    elif total <= -3:
        verdict, col, bg = "偏空", RED, "#FDECEA"
        plan = "以现金为主，减少新仓；只观察逆市走强的股票和板块，等见底信号（大力反弹、10 周线升穿 40 周线、宽度回到 70%）。"
        turn = "如果 SPY 收复 10 周线、宽度回到 50% 以上、VIX 回落到 20 以下，就升为中性。"
    else:
        verdict, col, bg = "中性 / 震荡", AMBER, "#FFF4E0"
        plan = "降低仓位、提高选股标准：只做形态最紧、相对强度最好的股票，单笔风险减半，有利润就收紧止损。"
        turn = "合计分数升到 +3 以上转偏多，跌到 −3 以下转偏空。"

    # ---- 表格 ----
    frows = "".join(f'<tr><td {TD}>{esc(f["name"])}</td><td {TDN}><b style="color:{GREEN if f["score"] > 0 else RED if f["score"] < 0 else GREY};">'
                    f'{f["score"]:+d}</b></td><td {TD}>{esc(f["fact"])}</td></tr>' for f in factors)

    def prow(sym, name, extra=""):
        x = P.get(sym)
        if not x:
            return f'<tr><td {TD}>{esc(name)}</td><td {TDN} colspan="5" style="color:#aaa;">没有取到数据</td></tr>'
        trend = ("—" if not x["ma10"] else ("10 周线上方" if x["close"] > x["ma10"] else "10 周线下方"))
        return (f'<tr><td {TD}><b>{esc(name)}</b> <span style="color:#999;font-size:11px;">{esc(sym)}</span>{extra}</td>'
                f'<td {TDN}>{x["close"]:,.2f}</td><td {TDN}>{pct(x["w1"])}</td><td {TDN}>{pct(x["m1"])}</td><td {TDN}>{pct(x["m3"])}</td>'
                f'<td {TDN}>{trend}</td></tr>')
    idx_tbl = table(("指数", "收盘", "1 周", "1 个月", "3 个月", "周线趋势"), "".join(prow(s, n) for s, n in INDEXES))
    ranked = sorted([s for s in SECTORS if P.get(s[0]) and P[s[0]]["m1"] is not None], key=lambda s: -P[s[0]]["m1"])
    sec_tbl = table(("板块（按 1 个月排序）", "收盘", "1 周", "1 个月", "3 个月", "周线趋势"),
                    "".join(prow(s, n, f' <span style="color:#888;font-size:11px;">{k}</span>') for s, n, k in ranked))
    mac_tbl = table(("品种", "最新", "1 周", "1 个月", "3 个月", "周线趋势"), "".join(prow(s, n) for s, n in MACRO))
    cal = calendar(False if now.weekday() == 6 or now.weekday() < 5 else True)
    if cal:
        crow = "".join(f'<tr><td {TDN}>{to_et(e["when"]):%m-%d %a %H:%M}</td><td {TDN}>'
                       + (f'<span style="color:{RED};font-weight:700;">高</span>' if e["impact"] == "High" else f'<span style="color:{AMBER};">中</span>')
                       + f'</td><td {TD}>{esc(CAL_ZH.get(e["title"], e["title"]))}</td><td {TDN}>{esc(e["forecast"] or "—")}</td>'
                       f'<td {TDN}>{esc(e["previous"] or "—")}</td></tr>' for e in cal if e["when"] >= now - dt.timedelta(hours=12))
        cal_html = table(("时间（美东）", "影响", "数据", "预期", "前值"), crow) if crow else '<p style="color:#888;">没有中、高影响力数据。</p>'
    else:
        cal_html = '<p style="color:#888;">没有取到经济日历。</p>'
    ers = upcoming_earnings()
    er_html = ('<ul style="margin:0;padding-left:20px;">' + "".join(
        f'<li>{esc(d)} · <b>{esc(sym)}</b> {esc(name[:28])} <span style="color:#888;font-size:12px;">{esc(sec)}</span></li>' for d, sym, name, sec in ers)
        + "</ul>") if ers else '<p style="color:#888;">各板块前 10 大公司里，下周没有公布业绩的（或还没有业绩估值数据）。</p>'

    got = sum(1 for s in syms if P.get(s))
    fresh = sum(1 for s in syms if P.get(s) and (now - P[s]["last"]).days <= 4)
    checks = [dict(name="行情数据", ok=got == len(syms), critical=got < len(syms) * 0.7, detail=f"{got}/{len(syms)} 个品种"),
              dict(name="数据新鲜度", ok=fresh == got, critical=False, detail=f"{fresh}/{got} 个在 4 天内更新"),
              dict(name="大盘历史", ok=len(hist) >= 2, critical=False, detail=f"{len(hist)} 条记录（宽度一周变化需要至少 2 条）"),
              dict(name="打分因素", ok=len(factors) >= 8, critical=len(factors) < 5, detail=f"{len(factors)}/9 个可计算")]
    head = (f'<div style="font-size:26px;font-weight:700;color:{col};">{verdict}（合计 {total:+d} 分）</div>'
            f'<div style="margin-top:8px;font-size:14px;line-height:1.6;"><b>按 J Law 规则的操作参考：</b>{esc(plan)}</div>'
            f'<div style="margin-top:4px;font-size:13px;color:#555;"><b>什么情况会改变判断：</b>{esc(turn)}</div>')
    body = (head + h3("9 个因素打分") + table(("因素", "分数", "数据"), frows)
            + h3("主要指数") + idx_tbl + h3("板块轮动") + sec_tbl + h3("利率、美元、大宗、波动率") + mac_tbl
            + h3("下周美国经济日历（中、高影响力）") + cal_html + h3("下周公布业绩的大公司") + er_html
            + h3("数据核对", GREY) + check_list_html(checks)
            + '<p style="color:#888;font-size:11px;margin-top:14px;">方向判断完全按上面 9 个因素的规则打分，不是预测；'
              '市场可能因突发消息改变方向。数据来自 Yahoo Finance、TradingView 选股器与 Forex Factory 日历。仅供学习，不构成投资建议。</p>')
    sub = f'<div style="font-size:13px;color:#555;">每周市场展望 · 截至 {to_et(now):%Y-%m-%d}（美东）</div>'
    page = card("下周市场方向", body, accent=col, bg=bg, sub=sub)
    base = os.path.join(WK_DIR, str(to_et(now).date()))
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "</head><body style=\"margin:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222;\">"
                + page + "</body></html>")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(dict(verdict=verdict, total=total, factors=factors, checks=checks), f, ensure_ascii=False, indent=1)
    print(json.dumps({"html": base + ".html", "verdict": verdict, "total": total, "factors": factors, "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
