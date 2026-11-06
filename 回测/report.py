"""回测第 3 步：把 results.pkl 做成 HTML 报告（回测报告.html）。结论文字放在 conclusions.json（看过数字后再写）。"""
import html as h
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "回测报告.html")
STATES = ("躺赚", "警戒", "血汗钱")
SCOL = {"躺赚": "#2E7D32", "警戒": "#B26A00", "血汗钱": "#C62828"}
JLAW_RISK = 0.35          # J Law：每笔风险账户 0.35%


def pc(x, d=1, signed=True):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    s = f"{x:+.{d}f}%" if signed else f"{x:.{d}f}%"
    col = "#2E7D32" if x > 0 else "#C62828" if x < 0 else "#555"
    return f'<span style="color:{col};">{s}</span>'


def rr(x):
    if x is None or np.isnan(x):
        return "—"
    col = "#2E7D32" if x > 0 else "#C62828" if x < 0 else "#555"
    return f'<span style="color:{col};">{x:+.2f}R</span>'


def table(head, rows):
    hd = "".join(f"<th>{x}</th>" for x in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table><tr>{hd}</tr>{body}</table></div>'


def trade_stats(t, col):
    r = t[col].dropna()
    if not len(r):
        return None
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    return dict(n=len(r), win=(r > 0).mean() * 100, avg=r.mean(), med=r.median(), pf=pos / neg if neg else np.inf,
                days=t.loc[r.index, col.replace("_r", "_days")].mean(), total=r.sum())


def equity_svg(series_list, w=900, ht=240):
    """series_list: [(名字, 颜色, pd.Series 累计值)]"""
    allv = pd.concat([s for _, _, s in series_list])
    lo, hi = min(0, allv.min()), allv.max()
    span = (hi - lo) or 1
    t0 = min(s.index.min() for _, _, s in series_list)
    t1 = max(s.index.max() for _, _, s in series_list)
    tspan = (t1 - t0).days or 1
    X = lambda d: 40 + (d - t0).days / tspan * (w - 60)
    Y = lambda v: 10 + (hi - v) / span * (ht - 40)
    parts = [f'<line x1="40" x2="{w - 20}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="#bbb" stroke-dasharray="3 3"/>']
    for yr in range(t0.year + 1, t1.year + 1):
        x = X(pd.Timestamp(f"{yr}-01-01"))
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="10" y2="{ht - 30}" stroke="#eee"/><text x="{x + 3:.1f}" y="{ht - 14}" font-size="11" fill="#888">{yr}</text>')
    for v in (lo, hi):
        parts.append(f'<text x="2" y="{Y(v) + 4:.1f}" font-size="11" fill="#888">{v:.0f}R</text>')
    legend = ""
    for i, (name, col, s) in enumerate(series_list):
        pts = " ".join(f"{X(d):.1f},{Y(v):.1f}" for d, v in s.items())
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.6"/>')
        legend += f'<span style="margin-right:14px;"><span style="display:inline-block;width:14px;height:3px;background:{col};vertical-align:middle;"></span> {h.escape(name)}</span>'
    return (f'<svg viewBox="0 0 {w} {ht}" style="width:100%;height:auto;max-width:{w}px;">{"".join(parts)}</svg>'
            f'<div style="font-size:12px;color:#555;">{legend}</div>')


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    R = pickle.load(open(os.path.join(HERE, "results.pkl"), "rb"))
    trades, ev, state = R["trades"], R["ev"], R["state"]
    start, end = R["start"], R["end"]
    concl = json.load(open(os.path.join(HERE, "conclusions.json"), encoding="utf-8")) if os.path.exists(os.path.join(HERE, "conclusions.json")) else {}
    st = state.loc[start:]
    days = st.value_counts()
    spy = R["spy"].loc[start:]
    spy_ret = (spy.iloc[-1] / spy.iloc[0] - 1) * 100

    # ---------- J Law 模拟交易 ----------
    modes = [("5R", "5R 目标（止损或 5R 止盈，最多 40 天）"), ("MA10", "10 天线移动止损（收盘跌破 10 天线卖，最多 60 天）"),
             ("MA20", "20 天线移动止损（收盘跌破 20 天线卖，最多 60 天）")]
    rows, curves = [], []
    colors = {("META", "5R"): "#1565C0", ("META", "MA10"): "#64B5F6", ("VCP", "5R"): "#6A1B9A", ("VCP", "MA10"): "#BA68C8",
              ("META", "MA20"): "#0D47A1", ("VCP", "MA20"): "#4A148C"}
    stat_json = {}
    for kind in ("META", "VCP"):
        t = trades[trades["kind"] == kind] if len(trades) else trades
        for m, label in modes:
            s = trade_stats(t, f"{m}_r") if len(t) else None
            if not s:
                rows.append([kind, label, "0"] + ["—"] * 7)
                continue
            stat_json[f"{kind}_{m}"] = s
            cum = t.dropna(subset=[f"{m}_r"]).sort_values(f"{m}_exit_d").set_index(f"{m}_exit_d")[f"{m}_r"].cumsum()
            dd = (cum - cum.cummax()).min()
            curves.append((f"{kind} · {m}", colors[(kind, m)], cum))
            rows.append([f"<b>{kind}</b>", label, f"{s['n']:,}", f"{s['win']:.0f}%", rr(s["avg"]), rr(s["med"]),
                         f"{s['pf']:.2f}", f"{s['days']:.0f} 天", rr(s["total"]).replace("R<", "R<"), f"{dd:.0f}R",
                         pc(s["total"] * JLAW_RISK)])
    trade_tbl = table(("形态", "卖出方法", "交易数", "胜率", "平均每笔", "中位数", "盈亏比", "平均持有", "累计", "最大回撤",
                       f"约等于账户（每笔风险 {JLAW_RISK}%）"), rows)
    curve_html = equity_svg(curves) if curves else ""

    # 按大盘状态
    srows = []
    for kind in ("META", "VCP"):
        t = trades[trades["kind"] == kind] if len(trades) else trades
        if not len(t):
            continue
        t = t.assign(state=t["d"].map(state))
        for m, _ in modes:
            cells = [f"<b>{kind}</b> · {m}"]
            for sname in STATES:
                s = trade_stats(t[t["state"] == sname], f"{m}_r")
                cells.append(f'{rr(s["avg"])} <span class="sm">胜率 {s["win"]:.0f}% · {s["n"]} 笔</span>' if s else "—")
            srows.append(cells)
    state_tbl = table(["形态 · 卖法"] + [f'<span style="color:{SCOL[s]};">信号日大盘：{s}</span>' for s in STATES], srows)

    # 按年份
    yrows = []
    for kind in ("META", "VCP"):
        t = trades[trades["kind"] == kind] if len(trades) else trades
        if not len(t):
            continue
        for y, g in t.groupby(t["d"].dt.year):
            cells = [f"<b>{kind}</b>", str(y), str(len(g))]
            for m, _ in modes:
                s1 = trade_stats(g, f"{m}_r")
                cells += [rr(s1["avg"]) if s1 else "—", f'{s1["win"]:.0f}%' if s1 else "—"]
            yrows.append(cells)
    year_tbl = table(("形态", "年份", "交易数", "5R 平均", "5R 胜率", "10 天线平均", "10 天线胜率", "20 天线平均", "20 天线胜率"), yrows)

    # ---------- 名单：上榜后报酬 ----------
    order = ["J Law META 就绪", "J Law VCP 就绪", "Stage 1→2 候选（新上榜）", "Stage 1→2 刚突破 + 得分 ≥4", "Stage 2 新进入",
             "Luk Strong Day（前 30）", "Luk Gappers（前 30）", "Luk Leaders（每周前 50）"]
    erows, srows2, ev_json = [], [], {}
    for name in order:
        g = ev[ev["list"] == name]
        if not len(g):
            continue
        cells = [f"<b>{h.escape(name)}</b>", f"{len(g):,}"]
        rec = {}
        for N in (5, 10, 20):
            x = g.dropna(subset=[f"r{N}"])
            ex_spy = (x[f"r{N}"] - x[f"spy{N}"]) * 100
            ex_base = (x[f"r{N}"] - x[f"base{N}"]) * 100
            rec[N] = dict(n=len(x), avg=x[f"r{N}"].mean() * 100, med=x[f"r{N}"].median() * 100, win=(x[f"r{N}"] > 0).mean() * 100,
                          beat=(ex_spy > 0).mean() * 100, ex_spy=ex_spy.mean(), ex_base=ex_base.mean())
        ev_json[name] = rec
        for N in (5, 10, 20):
            r_ = rec[N]
            cells.append(f'{pc(r_["avg"])}<br><span class="sm">中位 {pc(r_["med"])}</span>')
        r20 = rec[20]
        cells += [f'{r20["win"]:.0f}%', f'{r20["beat"]:.0f}%', pc(r20["ex_spy"]), pc(r20["ex_base"])]
        erows.append(cells)
        g20 = g.dropna(subset=["r20"])
        cs = [f"<b>{h.escape(name)}</b>"]
        for sname in STATES:
            x = g20[g20["state"] == sname]
            ex = ((x["r20"] - x["spy20"]) * 100).mean() if len(x) else np.nan
            cs.append(f'{pc(ex)} <span class="sm">{len(x):,} 次 · 胜率 {(x["r20"] > 0).mean() * 100:.0f}%</span>' if len(x) else "—")
        srows2.append(cs)
    ev_tbl = table(("名单", "上榜次数", "5 天平均", "10 天平均", "20 天平均", "20 天胜率", "20 天跑赢 SPY", "20 天超额 vs SPY",
                    "20 天超额 vs 全部股票"), erows)
    ev_state_tbl = table(["名单（20 天超额 vs SPY）"] + [f'<span style="color:{SCOL[s]};">上榜日大盘：{s}</span>' for s in STATES], srows2)

    # 大盘状态本身：各状态下 SPY 之后 20 天
    spy20 = (R["spy"].shift(-20) / R["spy"] - 1) * 100
    mrows = []
    for sname in STATES:
        idx = st[st == sname].index
        x = spy20.loc[idx].dropna()
        mrows.append([f'<b style="color:{SCOL[sname]};">{sname}</b>', f"{len(idx)} 天（{len(idx) / len(st) * 100:.0f}%）",
                      pc(x.mean()), f"{(x > 0).mean() * 100:.0f}%"])
    mkt_tbl = table(("大盘状态", "天数", "SPY 之后 20 天平均", "SPY 之后 20 天上涨的比例"), mrows)

    with open(os.path.join(HERE, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(dict(trades=stat_json, lists=ev_json, days=days.to_dict(), spy_ret=spy_ret), f, ensure_ascii=False, indent=1, default=float)

    concl_html = ("".join(f"<li>{c}</li>" for c in concl.get("points", [])) or "<li>（结论待补）</li>")
    caveats = [
        "<b>幸存者偏差</b>：股票池是今天还在交易、市值 ≥3 亿美元的 2,254 只美股。期间退市、被收购或跌到市值很小的股票不在里面，所以结果会<b>偏好</b>，尤其是 Luk 的小型股名单。",
        "<b>历史市值是估算</b>：今天市值 × 当时股价 ÷ 今天股价（假设股数不变）。",
        "<b>没有历史业绩日期</b>：META 的「业绩 / 催化剂」优势在回测里永远不成立，所以 META 信号比网站上少一些、条件更严。",
        "<b>Luk 的「1 周波动率」是近似</b>：用近 5 天 (最高 − 最低) ÷ 收盘 的平均，TradingView 的公式可能不同。Leaders 的「本周成交额」用每周五的 5 天合计。",
        "<b>大盘状态的宽度</b>：用股票池里市值 ≥100 亿的股票重算 50 天线以上比例，和网站用的 TradingView 数据接近但不完全一样。",
        "<b>交易成本</b>：没有扣佣金和滑点。止损和止盈当天同时碰到时，按先止损计算（偏保守）。",
        "<b>报酬是单笔平均</b>：「约等于账户」= 累计 R × 每笔风险，假设每笔都能下单、不考虑同时持仓太多、没有复利，只是粗略换算。",
        "<b>过去不代表将来</b>：这段时间（主要是 2023–2026 的牛市）的结果，未必适用于其他市况。",
    ]
    method = f"""<ul>
<li><b>期间</b>：{start:%Y-%m-%d} 至 {end:%Y-%m-%d}（约 {(end - start).days / 365:.1f} 年；前 300 个交易日只用来计算指标）。同期 SPY {pc(spy_ret)}。</li>
<li><b>股票池</b>：{R["n_stocks"]:,} 只现有美股，Yahoo 日线。</li>
<li><b>J Law META / VCP</b>：直接用网站「每日选股」的同一份程序（<code>analyse()</code>），每天收盘后重跑一次，挑出和网站一样的「就绪」名单。
META：第二天开盘买，止损用程序给的止损价。VCP：第二天价格碰到突破点才买（开盘就高于突破点 5% 不追），止损用程序给的止损价。同一只股票持仓期间不重复买。</li>
<li><b>三种卖法</b>：① 5R 目标：碰到止损或赚到 5 倍风险就卖，最多拿 40 天；② 10 天线移动止损：碰到止损，或收盘跌破 10 天线就卖，最多拿 60 天；③ 20 天线移动止损：同上，改用 20 天线。</li>
<li><b>名单（Stage、Luk）</b>：没有固定买卖点，所以看「上榜后第二天开盘买、持有 5 / 10 / 20 天」的报酬，和同期 SPY、以及全部股票的平均比较。
Stage 名单只算「新上榜」那一天（Stage 2：之前 20 天不在名单；Stage 1→2：之前 10 天不在）。</li>
<li><b>大盘状态</b>：按网站「大盘报告」的规则逐日重算（SPY / QQQ 均线、出货日、突兀大跌、宽度）。</li>
</ul>"""
    css = """<style>
:root{--bg:#f4f5f7;--card:#fff;--fg:#222;--muted:#666;--line:#eee}
body{margin:0;background:var(--bg);font-family:Arial,'Microsoft YaHei',sans-serif;color:var(--fg)}
.wrap{max-width:1100px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid #e3e3e3;border-radius:8px;padding:16px 18px;margin-bottom:14px;line-height:1.6;font-size:14px}
h1{font-size:22px;margin:4px 0}h2{font-size:17px;margin:4px 0 10px;color:#1F4E78}
.tw{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}
th{padding:6px 8px;background:#f5f5f5;text-align:left;font-weight:600;border-bottom:1px solid #ddd;white-space:nowrap}
td{padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:top}
.sm{color:#888;font-size:11px}.note{color:#666;font-size:12px}code{background:#f2f2f2;padding:0 4px;border-radius:3px}
ul{margin:0;padding-left:20px}
</style>"""
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>选股回测报告</title>{css}</head><body><div class="wrap">
<div class="card" style="border-left:6px solid #1F4E78;"><div class="note">J Law 与 Martin Luk 选股回测 · {start:%Y-%m-%d} 至 {end:%Y-%m-%d}</div>
<h1>选股回测报告</h1><div class="note">用每日报告网站上同样的选股规则，在过去 {(end - start).days / 365:.1f} 年每天重跑一次，看这些名单之后的表现。仅供学习，不构成投资建议。</div></div>
<div class="card"><h2>结论</h2><ul>{concl_html}</ul></div>
<div class="card"><h2>1. J Law META 回调 / VCP 突破：模拟交易</h2>{trade_tbl}
<p class="note">R = 每笔的风险（买入价 − 止损价）。平均每笔 +0.30R 表示长期每冒 1 元风险平均赚 0.3 元。盈亏比 = 赚的 R 合计 ÷ 亏的 R 合计（&gt;1 才赚钱）。</p>
<h2 style="margin-top:14px;">累计 R（按卖出日期）</h2>{curve_html}</div>
<div class="card"><h2>2. 大盘状态有没有用？</h2>
<p class="note" style="margin-top:0;">先看大盘状态本身：各状态下，SPY 之后 20 天的表现。</p>{mkt_tbl}
<p class="note">再看 J Law 两个形态在不同大盘状态下的平均每笔（按买入信号当天的状态分）：</p>{state_tbl}</div>
<div class="card"><h2>3. J Law 按年份</h2>{year_tbl}</div>
<div class="card"><h2>4. 所有名单：上榜后 5 / 10 / 20 天的报酬</h2>{ev_tbl}
<p class="note">超额 vs SPY = 同期比 SPY 多赚（或少赚）多少。超额 vs 全部股票 = 比同一天全部股票的平均多赚多少（扣掉「那段时间大家都涨」的部分）。</p>
<h2 style="margin-top:14px;">按上榜日的大盘状态（20 天超额 vs SPY）</h2>{ev_state_tbl}</div>
<div class="card"><h2>5. 回测方法</h2>{method}</div>
<div class="card"><h2>6. 限制（请务必看）</h2><ul>{"".join(f"<li>{c}</li>" for c in caveats)}</ul></div>
</div></body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(OUT)


if __name__ == "__main__":
    main()
