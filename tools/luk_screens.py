"""Martin Luk 的三个 TradingView 选股器：Leaders（领导股）、Strong Day（当日强势，Luk 叫 Potent）、Gappers（跳空股）。

条件来自 Martin Luk 本人在 Trading Resource Hub 文章下的留言（2025-02-02）：
  * Potent（Strong Day）：市值 >1 亿、1 周波动率 >3.5%、股价 > 21 EMA、成交额（量×价）>5,000 万；看前一日表现最强的
  * Premarket（Gappers）：市值 >1 亿、10 日均量 >50 万、成交额 >5,000 万，按盘前涨幅排序
  * Leader（Leaders）：市值 >1 亿、10 日均量 >50 万、本周成交额 >3 亿，按 1 个月涨幅排序（他周末看）
报告在美股收盘后跑，盘前已经过去，所以 Gappers 按「开盘跳空 %」排序，并列出当天盘前涨幅。
另按 Luk 的观察名单分类：Lead = 9 EMA > 21 EMA > 50 EMA；Lag = 9 < 21 < 50；其余 Mediocre。

用法：python luk_screens.py [输出目录]
输出：<输出目录>/Luk选股/YYYY-MM-DD.html 和 .json（json 用来标出「新上榜」）
仅供学习，不构成投资建议。
"""
import datetime as dt
import glob
import html as h
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import AMBER, BLUE, GREEN, GREY, RED, card, check_list_html, h3, tv_scan, yahoo_chart
from rs_rating import load as rs_load, badge as rs_badge, stale_note as rs_stale
RS = rs_load()

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUK_DIR = os.path.join(OUT_DIR, "Luk选股")
SOURCE = "https://tradingresourcehub.substack.com/p/martin-luk-283-usic-2024-key-lessons"
COLS = ["name", "description", "exchange", "close", "change", "gap", "premarket_change", "Perf.W", "Perf.1M", "Volatility.W",
        "EMA9", "EMA21", "EMA50", "ADR", "Value.Traded", "Value.Traded|1W", "average_volume_10d_calc", "relative_volume_10d_calc",
        "market_cap_basic", "sector", "industry", "earnings_release_next_date"]
BASE = [{"left": "type", "operation": "equal", "right": "stock"},
        {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
        {"left": "market_cap_basic", "operation": "greater", "right": 1e8}]
SCREENS = [
    ("strong", "Strong Day（当日强势）", "Luk 的 Potent 选股器：找当天表现最强、波动够大的股票，第二天开始观察回调或延续。",
     BASE + [{"left": "Volatility.W", "operation": "greater", "right": 3.5},
             {"left": "close", "operation": "greater", "right": "EMA21"},
             {"left": "Value.Traded", "operation": "greater", "right": 5e7}],
     ("change", "desc"), 30, "市值 &gt;1 亿 · 1 周波动率 &gt;3.5% · 股价 &gt; 21 EMA · 成交额 &gt;5,000 万 · 按当日涨幅排序"),
    ("gap", "Gappers（跳空股）", "Luk 的 Premarket 选股器：找有消息、跳空高开的股票。报告在收盘后跑，所以按今天开盘的跳空幅度排序。",
     BASE + [{"left": "average_volume_10d_calc", "operation": "greater", "right": 5e5},
             {"left": "Value.Traded", "operation": "greater", "right": 5e7},
             {"left": "gap", "operation": "egreater", "right": 3}],
     ("gap", "desc"), 30, "市值 &gt;1 亿 · 10 日均量 &gt;50 万 · 成交额 &gt;5,000 万 · 跳空 ≥3%（为了名单精简另加） · 按开盘跳空 % 排序（Luk 原本在盘前按盘前涨幅排序）"),
    ("leader", "Leaders（领导股）", "Luk 的 Leader 选股器：过去一个月涨最多的股票，他每个周末看一次，从中找下一波的领导股和主题。",
     BASE + [{"left": "average_volume_10d_calc", "operation": "greater", "right": 5e5},
             {"left": "Value.Traded|1W", "operation": "greater", "right": 3e8}],
     ("Perf.1M", "desc"), 50, "市值 &gt;1 亿 · 10 日均量 &gt;50 万 · 本周成交额 &gt;3 亿 · 按 1 个月涨幅排序"),
]


def run_screen(filters, sort, top):
    body = {"filter": filters, "columns": COLS, "sort": {"sortBy": sort[0], "sortOrder": sort[1]}, "range": [0, top]}
    total = tv_scan(dict(body, columns=["name"], range=[0, 5000]))
    rows = [dict(zip(COLS, r["d"])) for r in tv_scan(body)]
    return rows, len(total)


def ema_list(r):
    e9, e21, e50 = r["EMA9"], r["EMA21"], r["EMA50"]
    if None in (e9, e21, e50):
        return "—"
    return "Lead" if e9 > e21 > e50 else "Lag" if e9 < e21 < e50 else "Mediocre"


def prev_lists():
    files = sorted(f for f in glob.glob(os.path.join(LUK_DIR, "20??-??-??.json")) if os.path.basename(f)[:10] != str(dt.date.today()))
    if not files:
        return {}, None
    with open(files[-1], encoding="utf-8") as f:
        d = json.load(f)
    return {k: set(v) for k, v in d.get("lists", {}).items()}, os.path.basename(files[-1])[:10]


def cross_check(rows):
    """前 5 只的收盘价：TradingView vs Yahoo（相差 >1.5% 视为不一致）。"""
    bad, ok = [], 0
    for r in rows[:5]:
        try:
            bars, _ = yahoo_chart(r["name"].replace(".", "-"), "5d", "1d")
            if abs(bars[-1]["c"] / r["close"] - 1) > 0.015:
                bad.append(r["name"])
            else:
                ok += 1
        except Exception:
            bad.append(r["name"] + "（取不到）")
    return ok, bad


def table_html(key, rows, prev, today):
    def pc(x, d=1):
        if x is None:
            return "—"
        cls = "u" if x > 0 else "s" if x < 0 else ""
        return f"<{cls}>{x:+.{d}f}%</{cls}>" if cls else f"{x:+.{d}f}%"

    lcol = {"Lead": "#2E7D32", "Mediocre": "#B26A00", "Lag": "#C62828", "—": "#888"}
    head = ["#", "股票", "行业", "收盘", "当日", "跳空" if key == "gap" else "1 周", "1 月", "ADR%", "相对成交量", "成交额", "EMA 分类", "业绩"]
    if key == "gap":
        head.insert(6, "盘前")
    body = ""
    for i, r in enumerate(rows, 1):
        ex = r["exchange"] or ""
        url = "https://www.tradingview.com/chart/?symbol=" + (f"{ex}:{r['name']}" if ex else r["name"])
        new = " <b class='nw'>新</b>" if prev is not None and r["name"] not in prev else ""
        adr = r["ADR"] / r["close"] * 100 if r["ADR"] and r["close"] else None
        adr_txt = "—" if adr is None else (f"<b>{adr:.1f}%</b>" if adr >= 5 else f"{adr:.1f}%")
        er = r.get("earnings_release_next_date")
        er_d = (dt.datetime.fromtimestamp(er, dt.timezone.utc).date() - today).days if er else None
        er_txt = "—" if er_d is None or er_d < 0 else (f"<s>⚠ {er_d} 天后</s>" if er_d <= 14 else f"{er_d} 天后")
        lst = ema_list(r)
        mid = (f"<td>{pc(r['gap'])}</td><td>{pc(r['premarket_change'])}</td>" if key == "gap" else f"<td>{pc(r['Perf.W'])}</td>")
        vt = r["Value.Traded"] or 0
        body += (f'<tr><td>{i}</td><td><a href="{h.escape(url)}" target="_blank" rel="noopener">{h.escape(r["name"])} 📈</a>{rs_badge(RS, r["name"])}{new}'
                 f'<br><small>{h.escape((r["description"] or "")[:24])}</small></td><td>{h.escape((r["industry"] or "")[:22])}</td>'
                 f'<td>{r["close"]:.2f}</td><td>{pc(r["change"])}</td>{mid}<td>{pc(r["Perf.1M"])}</td><td>{adr_txt}</td>'
                 f'<td>{(r["relative_volume_10d_calc"] or 0):.1f}x</td><td>{vt / 1e6:,.0f}M</td>'
                 f'<td><b style="color:{lcol[lst]};">{lst}</b></td><td>{er_txt}</td></tr>')
    hd = "".join(f"<th>{x}</th>" for x in head)
    return f'<div style="overflow-x:auto;"><table class="lk"><tr>{hd}</tr>{body}</table></div>'


def themes(all_rows):
    """主题：同一行业在三个名单里出现 ≥3 只。"""
    cnt, names = Counter(), {}
    for r in all_rows:
        ind = r["industry"] or ""
        if ind and r["name"] not in names.setdefault(ind, []):
            names[ind].append(r["name"])
            cnt[ind] += 1
    return [(k, names[k]) for k, n in cnt.most_common() if n >= 3][:10]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(LUK_DIR, exist_ok=True)
    today = dt.date.today()
    prev, prev_date = prev_lists()
    results, checks = {}, []
    for key, title, why, filters, sort, top, rule in SCREENS:
        try:
            rows, total = run_screen(filters, sort, top)
        except Exception as e:
            rows, total = [], 0
            checks.append(dict(name=f"{title} 选股器", ok=False, critical=False, detail=f"TradingView 取不到（{type(e).__name__}）"))
        results[key] = (rows, total)
    all_rows = [r for rows, _ in results.values() for r in rows]
    if all_rows:
        ok, bad = cross_check(results["strong"][0] or all_rows)
        checks.append(dict(name="收盘价核对（TradingView vs Yahoo）", ok=not bad, critical=False,
                           detail=f"抽查 {ok + len(bad)} 只，{ok} 只一致" + (f"；不一致：{'、'.join(bad)}" if bad else "")))
    checks.append(dict(name="三个选股器", ok=all(results[k][0] for k in results), critical=not all_rows,
                       detail="、".join(f"{t.split('（')[0]} {results[k][1]} 只" for k, t, *_ in SCREENS)))

    # ---- 一眼看懂 ----
    lead = Counter(ema_list(r) for r in results["leader"][0])
    th = themes(all_rows)
    new_cnt = {k: sum(1 for r in results[k][0] if prev and r["name"] not in prev.get(k, set())) for k in results}
    bullets = [
        f"Strong Day 今天有 <b>{results['strong'][1]}</b> 只符合，前 3 名："
        + "、".join(f"{h.escape(r['name'])}（{r['change']:+.1f}%）" for r in results["strong"][0][:3]) + "。",
        f"Gappers 今天有 <b>{results['gap'][1]}</b> 只跳空 ≥3%，最大的："
        + "、".join(f"{h.escape(r['name'])}（{r['gap']:+.1f}%）" for r in results["gap"][0][:3]) + "。",
        f"Leaders 前 50 名里，EMA 分类 Lead <b>{lead.get('Lead', 0)}</b> 只、Mediocre {lead.get('Mediocre', 0)} 只、Lag {lead.get('Lag', 0)} 只。",
    ]
    if th:
        bullets.append("主题（同一行业在名单里 ≥3 只）：" + "；".join(f"<b>{h.escape(k)}</b>（{len(v)}）" for k, v in th[:5]) + "。")
    if prev_date:
        bullets.append(f"对比 {prev_date}，新上榜：Strong Day {new_cnt['strong']} 只、Gappers {new_cnt['gap']} 只、Leaders {new_cnt['leader']} 只（表中标「新」）。")
    summary = '<ul style="margin:0;padding-left:20px;">' + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>"

    method = f"""<details style="margin-top:4px;"><summary style="cursor:pointer;color:{BLUE};font-weight:600;">Martin Luk 的用法（点开看）</summary>
<ul style="margin:6px 0 0;padding-left:20px;font-size:13px;line-height:1.7;">
<li><b>每天约 30 分钟</b>：收盘后看 Potent（Strong Day）找前一日最强的股票；开盘前看 Premarket 找跳空高开的股票。<b>周末</b>看 Leader 找过去一个月涨最多的股票。</li>
<li><b>观察名单按 EMA 分三类</b>：Lead = 9 EMA &gt; 21 EMA &gt; 50 EMA；Lag = 9 &lt; 21 &lt; 50；其余 Mediocre。股票从 Mediocre 升到 Lead 值得留意。</li>
<li><b>主题</b>：同一行业多只股票同时新上榜或升级，就在下一次回调时重点观察。</li>
<li><b>ADR</b>：主要做 ADR &gt;5% 的股票（表中 ADR% 粗体），但不是硬性规定。</li>
<li><b>止损</b>：进场前定好，成交后马上挂硬止损；多数 1–5%，而且不超过 ADR 的一半（例如 ADR 5% 的股票止损 ≤2.5%）。用 9 EMA 做移动止损。</li>
<li><b>风险</b>：每笔风险账户 0.5–1%；回撤时先减仓，逐步加回；市况差时休息，不硬做。</li>
</ul><p style="margin:6px 0 0;font-size:11px;color:#888;">来源：<a href="{SOURCE}" target="_blank" rel="noopener">Trading Resource Hub 的 Martin Luk 文章</a>，选股条件取自 Luk 本人在文章下的留言（2025-02-02）。</p></details>"""

    css = ("<style>.lk{width:100%;border-collapse:collapse;font-size:13px}.lk th{padding:6px 8px;background:#f5f5f5;text-align:left;"
           "font-weight:600;border-bottom:1px solid #ddd;white-space:nowrap}.lk td{padding:6px 8px;border-bottom:1px solid #eee;white-space:nowrap}"
           ".lk a{color:#1565C0;text-decoration:none;font-weight:700}.lk small{color:#888;font-size:11px}"
           f".lk u{{text-decoration:none;color:{GREEN}}}.lk s{{text-decoration:none;color:{RED}}}"
           ".lk .nw{background:#E3F2FD;color:#1565C0;font-size:10px;padding:0 4px;border-radius:6px}</style>")
    sections = ""
    for key, title, why, filters, sort, top, rule in SCREENS:
        rows, total = results[key]
        sections += (h3(f"{title} · {total} 只符合，显示前 {min(top, len(rows))} 只")
                     + f'<p style="margin:0 0 4px;font-size:13px;">{why}</p><p style="margin:0 0 6px;font-size:12px;color:#777;">条件：{rule}</p>'
                     + (table_html(key, rows, prev.get(key) if prev_date else None, today) if rows else '<p style="color:#888;">今天取不到数据。</p>'))
    theme_html = ("".join(f"<li><b>{h.escape(k)}</b>（{len(v)}）：{h.escape('、'.join(v[:12]))}</li>" for k, v in th)
                  if th else "<li>今天没有同一行业 ≥3 只的主题。</li>")
    body = (css + h3("一眼看懂", GREEN) + summary + rs_stale(RS) + method + sections
            + h3("主题（同一行业在三个名单里 ≥3 只）") + f'<ul style="margin:0;padding-left:20px;">{theme_html}</ul>'
            + '<p style="color:#888;font-size:11px;margin-top:14px;">数据来自 TradingView 选股器（与你在 TradingView 里看到的同一来源），收盘后的数据。'
              'ADR% = 14 日平均日波幅 ÷ 股价。相对成交量 = 当日量 ÷ 10 日均量。「本周成交额」是 TradingView 的周线数据，周一、周二时数值偏小，Leaders 名单会较短。'
              '点股票代码打开 TradingView 日线图。仅供学习，不构成投资建议。</p>')
    sub = f'<div style="font-size:13px;color:#555;">Martin Luk（美国投资冠军赛 USIC 冠军）的三个 TradingView 选股器 · 美股收盘数据</div>'
    frag = card("Martin Luk 选股 · Leaders / Strong Day / Gappers", body, accent="#00897B", bg="#E0F2F1", sub=sub)

    base = os.path.join(LUK_DIR, str(today))
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "</head><body style=\"margin:0;background:#f4f5f7;font-family:Arial,'Microsoft YaHei',sans-serif;color:#222;\">"
                + frag + "</body></html>")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"date": str(today), "lists": {k: [r["name"] for r in v[0]] for k, v in results.items()},
                   "totals": {k: v[1] for k, v in results.items()}}, f, ensure_ascii=False, indent=1)
    for f in sorted(glob.glob(os.path.join(LUK_DIR, "20??-??-??.json")))[:-30]:
        os.remove(f)
    print(json.dumps({"html": base + ".html", "totals": {k: v[1] for k, v in results.items()},
                      "top": {k: [r["name"] for r in v[0][:5]] for k, v in results.items()}, "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
