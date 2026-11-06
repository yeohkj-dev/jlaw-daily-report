"""读 results.json，生成 D:\\AI\\Claude AI\\量化投资系统.html"""
import json, os, html
from trade_section import build as trade_build
TRADE = trade_build()
from simple import build as simple_build

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.environ.get("QUANT_OUT") or os.path.join(DATA, "量化系统.html")
o = json.load(open(os.path.join(DATA, "results.json"), encoding="utf-8"))
now = o["now"]
SIMPLE = simple_build(o, json.load(open(os.path.join(DATA, "signals.json"), encoding="utf-8")))


def pct(x, d=1, sign=False):
    if x is None:
        return "–"
    s = f"{x*100:+.{d}f}%" if sign else f"{x*100:.{d}f}%"
    return s


def cls(x):
    return "pos" if x is not None and x > 0 else ("neg" if x is not None and x < 0 else "")


# ---------- 当前读数
reg = now["regime"]
reg_cls = {"进攻": "good", "中性": "mid", "防守": "bad"}[reg]
sig_rows = "".join(f'<li class="{"on" if v else "off"}"><span>{"✓" if v else "✗"}</span>{html.escape(k)}</li>'
                   for k, v in now["signals"].items())
expo_txt = {"进攻": "100%", "中性": "60%", "防守": "20%"}[reg]
lev_ok = now["score"] >= 75 and now["qqq_rv20"] < 0.25
lev_txt = ("可以持有 2 倍杠杆 ETF（状态 ≥75 且纳指波动 <25%）" if lev_ok else
           ("杠杆 ETF 减到一半（状态 45–75 分）" if now["score"] >= 45 else "杠杆 ETF 全部清掉换现金（防守）"))
if not now["qqq_above200"]:
    lev_txt = "纳指在 200 日线下：杠杆 ETF 应全部换现金"
sec_rows = "".join(
    f'<tr class="{"pick" if s["t"] in now["rot_picks"] else ""}"><td>{i+1}</td><td><b>{s["t"]}</b></td><td>{pct(s["mom"])}</td>'
    f'<td class="{cls(s["r1m"])}">{pct(s["r1m"], sign=True)}</td><td>{"✓" if s["above200"] else "✗"}</td></tr>'
    for i, s in enumerate(now["sectors"]))
SECN = {"XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "医疗", "XLY": "可选消费", "XLP": "必需消费", "XLI": "工业", "XLU": "公用事业", "XLB": "原材料"}
sec_rows = sec_rows
for t, n in SECN.items():
    sec_rows = sec_rows.replace(f"<b>{t}</b>", f"<b>{t}</b> <small>{n}</small>")
stk_rows = "".join(
    f'<tr><td>{i+1}</td><td><b>{s["t"]}</b></td><td class="ind">{html.escape(s["industry"] or s["sector"])}</td>'
    f'<td>{pct(s["mom"],0)}</td><td>{pct(s["vol"],0)}</td><td>{pct(s["near_high"],0)}</td><td class="{cls(s["r1m"])}">{pct(s["r1m"],0,True)}</td></tr>'
    for i, s in enumerate(now["stocks"][:25]))

# ---------- 策略表
GROUPS = ["大盘择时", "智能杠杆", "杠杆 ETF", "轮动", "组合方案"]
def strat_rows(keys):
    rows = ""
    for k in keys:
        s = o["strategies"][k]; t = s["stats"]
        star = " ★" if k in ("combo_core", "combo_growth", "rot3_rg", "l2ma_QQQ", "voltarget") else ""
        rows += (f'<tr><td><b>{html.escape(s["name"])}</b>{star}<div class="desc">{html.escape(s["desc"])}</div></td>'
                 f'<td class="num">{pct(t["cagr"])}</td><td class="num">{pct(t["vol"])}</td><td class="num">{t["sharpe"]:.2f}</td>'
                 f'<td class="num neg">{pct(t["mdd"])}</td><td class="num {cls(t["worst_year"])}">{pct(t["worst_year"])}</td>'
                 f'<td class="num">{pct(t.get("avg_expo",1),0)}</td></tr>')
    return rows
by_group = {}
for k, s in o["strategies"].items():
    by_group.setdefault(s["group"], []).append(k)
strat_html = ""
for g in GROUPS:
    keys = (["bh", "qqq"] if g != "大盘择时" else []) + by_group.get(g, [])
    strat_html += f'<tr class="grp"><td colspan="7">{g}</td></tr>' + strat_rows(keys)

per_keys = ["bh", "qqq", "ma200", "voltarget", "rot3_rg", "l2bh_QQQ", "l2ma_QQQ", "combo_core", "combo_growth"]
per_html = "".join(
    f'<tr><td>{html.escape(o["strategies"][k]["name"])}</td>' +
    "".join(f'<td class="num {cls(o["by_period"][k][p])}">{pct(o["by_period"][k][p],0)}</td>' for p in o["periods"]) + "</tr>"
    for k in per_keys)
per_head = "".join(f"<th>{p}</th>" for p in o["periods"])

pred_html = "".join(
    f'<tr><td><b>{p["bucket"]}</b></td><td class="num">{pct(p["share"],0)}</td><td class="num">{pct(p["f63"],1,True)}</td>'
    f'<td class="num">{pct(p["win63"],0)}</td><td class="num">{pct(p["vol21"],0)}</td><td class="num neg">{pct(p["dd63"],1)}</td>'
    f'<td class="num"><div class="bar"><i style="width:{p["crash63"]*100/0.35:.0f}%"></i><span>{pct(p["crash63"],0)}</span></div></td></tr>'
    for p in o["pred"])
rob_html = "".join(f'<tr><td>{k}</td><td class="num">{pct(v["cagr"])}</td><td class="num">{v["sharpe"]:.2f}</td><td class="num neg">{pct(v["mdd"])}</td></tr>'
                   for k, v in o["robust"].items())
stk_bt = "".join(
    f'<tr><td>{html.escape(s["name"])}</td><td class="num">{pct(s["stats"]["cagr"])}</td><td class="num">{pct(s["stats"]["vol"])}</td>'
    f'<td class="num">{s["stats"]["sharpe"]:.2f}</td><td class="num neg">{pct(s["stats"]["mdd"])}</td></tr>'
    for k, s in o["stocks"].items())

chart_data = {k: dict(n=s["name"], d=s["d"], eq=s["eq"], dd=s["dd"]) for k, s in o["strategies"].items()}
stock_chart = {k: dict(n=s["name"], d=s["d"], eq=s["eq"]) for k, s in o["stocks"].items()}
S = o["strategies"]
g = S["combo_growth"]["stats"]; c = S["combo_core"]["stats"]; b = S["bh"]["stats"]; q = S["qqq"]["stats"]
l2 = S["l2bh_QQQ"]["stats"]; l2m = S["l2ma_QQQ"]["stats"]

HTML = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>量化系统：今天怎么做</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--mute:#6a7180;--line:#e3e6eb;--acc:#2f5bea;--pos:#14895a;--neg:#c8372d;--mid:#b7791f;--soft:#eef2ff}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#0f1115;--card:#171a21;--ink:#e8eaee;--mute:#9aa2b1;--line:#2a2f3a;--acc:#7c9cff;--pos:#3ecf8e;--neg:#ff6b5e;--mid:#f0b54a;--soft:#1d2433}}}}
:root[data-theme=dark]{{--bg:#0f1115;--card:#171a21;--ink:#e8eaee;--mute:#9aa2b1;--line:#2a2f3a;--acc:#7c9cff;--pos:#3ecf8e;--neg:#ff6b5e;--mid:#f0b54a;--soft:#1d2433}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:20px 16px 60px}}
h1{{font-size:26px;margin:4px 0}}h2{{font-size:20px;margin:36px 0 12px;padding-top:8px;border-top:1px solid var(--line)}}h3{{font-size:16px;margin:18px 0 8px}}
.sub{{color:var(--mute);font-size:13px}}
nav{{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0;display:flex;gap:6px;overflow-x:auto;border-bottom:1px solid var(--line)}}
nav a{{white-space:nowrap;font-size:13px;color:var(--ink);text-decoration:none;padding:4px 10px;border-radius:99px;background:var(--card);border:1px solid var(--line)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}}
.grid{{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}}
.kpi .v{{font-size:26px;font-weight:700}}.kpi .l{{font-size:12px;color:var(--mute)}}
.good{{color:var(--pos)}}.bad{{color:var(--neg)}}.mid{{color:var(--mid)}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
.tl li{{margin:6px 0}}
ul.sig{{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:6px}}
ul.sig li{{padding:6px 10px;border-radius:8px;background:var(--soft);font-size:14px}}ul.sig li span{{display:inline-block;width:20px;font-weight:700}}
ul.sig li.on span{{color:var(--pos)}}ul.sig li.off span{{color:var(--neg)}}ul.sig li.off{{opacity:.8}}
.tw{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{border-collapse:collapse;width:100%;font-size:13.5px}}th,td{{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--mute);font-weight:600;font-size:12px;white-space:nowrap}}td.num,th.num{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
tr.grp td{{background:var(--soft);font-weight:700;font-size:13px}}tr.pick td{{background:var(--soft)}}
.desc{{color:var(--mute);font-size:12px;line-height:1.5;margin-top:2px}}td.ind{{color:var(--mute);font-size:12px}}
.bar{{position:relative;background:var(--soft);border-radius:4px;height:18px;min-width:90px}}.bar i{{position:absolute;left:0;top:0;bottom:0;background:var(--neg);opacity:.35;border-radius:4px}}.bar span{{position:relative;padding-left:6px;font-size:12px}}
.note{{border-left:3px solid var(--mid);padding:8px 12px;background:var(--soft);border-radius:0 8px 8px 0;font-size:14px;margin:10px 0}}
.method{{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}}
.method .card{{margin:0}}.method h3{{margin-top:0}}.tag{{display:inline-block;font-size:11px;padding:1px 8px;border-radius:99px;margin-left:6px;vertical-align:2px}}
.t-good{{background:#14895a22;color:var(--pos)}}.t-mid{{background:#b7791f22;color:var(--mid)}}.t-bad{{background:#c8372d22;color:var(--neg)}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}}.chips label{{font-size:12px;padding:3px 9px;border:1px solid var(--line);border-radius:99px;cursor:pointer;background:var(--card)}}
.chips input{{margin-right:4px}}canvas{{max-width:100%}}.cv{{position:relative;height:340px}}
.big{{font-size:44px;font-weight:800;line-height:1}}ol li,ul li{{margin:4px 0}}code{{background:var(--soft);padding:1px 6px;border-radius:4px;font-size:13px}}
.theme{{float:right;font-size:12px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:99px;padding:3px 10px;cursor:pointer}}
@media(max-width:600px){{h1{{font-size:21px}}.big{{font-size:36px}}.cv{{height:260px}}}}
</style></head><body><div class="wrap">
<button class="theme" onclick="tg()">深色 / 浅色</button>
<h1>量化系统：今天怎么做</h1>
<div class="sub">数据截至 {now["date"]}（ETF/指数，Yahoo）· 个股宽度截至 {now["breadth_date"]} · 回测期 {o["start"]} 至 {o["end"]} · 所有信号收盘计算、次日生效，含交易成本</div>
<div style="max-width:820px">{SIMPLE}</div>
<details id="more" style="margin-top:24px"><summary style="cursor:pointer;font-weight:700;font-size:16px;padding:12px 16px;background:var(--card);border:1px solid var(--line);border-radius:12px">📚 详细研究、回测和数据（想深入了解才看，不看也能用）</summary>
<nav><a href="#tldr">结论</a><a href="#now">今天的市场</a><a href="#research">量化研究</a><a href="#bt">回测结果</a><a href="#regime">状态模型</a><a href="#stocks">个股动量</a><a href="#trade">买卖规则</a><a href="#today">今日信号</a><a href="#howto">怎么用</a><a href="#limits">局限</a></nav>

<h2 id="tldr">一、结论先看</h2>
<div class="grid">
<div class="kpi"><div class="l">进取组合（年化 / 最大回撤）</div><div class="v good">{pct(g["cagr"])}</div><div class="sub">回撤 {pct(g["mdd"])} · 夏普 {g["sharpe"]:.2f}</div></div>
<div class="kpi"><div class="l">稳健组合（年化 / 最大回撤）</div><div class="v">{pct(c["cagr"])}</div><div class="sub">回撤 {pct(c["mdd"])} · 夏普 {c["sharpe"]:.2f}</div></div>
<div class="kpi"><div class="l">SPY 买入持有</div><div class="v">{pct(b["cagr"])}</div><div class="sub">回撤 {pct(b["mdd"])} · 夏普 {b["sharpe"]:.2f}</div></div>
<div class="kpi"><div class="l">2x 纳指：死拿 vs 加 200 日线</div><div class="v">{pct(l2["mdd"],0)} → <span class="good">{pct(l2m["mdd"],0)}</span></div><div class="sub">最大回撤；年化 {pct(l2["cagr"])} / {pct(l2m["cagr"])}</div></div>
</div>
<div class="card tl"><ol>
<li><b>量化不是预测明天涨跌，而是管理风险。</b>我们 8 个信号的「市场状态分」对未来 3 个月涨幅几乎没有预测力，但对<b>风险</b>预测很准：分数 ≥75 时，未来 3 个月跌 10% 以上的概率只有 {pct(o["pred"][-1]["crash63"],0)}；分数 &lt;25 时是 {pct(o["pred"][0]["crash63"],0)}，高 5 倍。</li>
<li><b>单纯择时会少赚：</b>200 日线择时把最大回撤从 {pct(b["mdd"],0)} 降到 {pct(S["ma200"]["stats"]["mdd"],0)}，但年化也从 {pct(b["cagr"])} 降到 {pct(S["ma200"]["stats"]["cagr"])}（踏空反弹）。</li>
<li><b>提高回报的正确方法 = 先用量化把回撤砍掉，再把省下来的风险拿去「多承担一点」</b>：板块动量轮动、适度杠杆、动量个股。进取组合年化 {pct(g["cagr"])}，高过 SPY 的 {pct(b["cagr"])}，而最大回撤只有 {pct(g["mdd"],0)}（SPY {pct(b["mdd"],0)}）。</li>
<li><b>2 倍杠杆 ETF 最需要量化规则。</b>死拿 2x 纳指历史最大回撤 {pct(l2["mdd"],0)}（2000–2002、2008 那种跌法要 10 年以上才回本）；只加一条「纳指跌破 200 日线就清仓」，回撤减到 {pct(l2m["mdd"],0)}。</li>
<li><b>今天的读数：状态分 {now["score"]:.0f}（{reg}）。</b>趋势还在（SPY 在 200 日线上），但 VIX {now["vix"]:.1f}、期限结构倒挂、信用和风险偏好走弱 —— 典型「涨势中出现压力」。建议总仓位 {expo_txt}，{lev_txt}。</li>
</ol></div>

<h2 id="now">二、今天的市场读数（{now["date"]}）</h2>
<div class="grid">
<div class="kpi"><div class="l">市场状态分（0–100）</div><div class="big {reg_cls}">{now["score"]:.0f}</div><div class="sub">{reg} · 建议股票仓位 {expo_txt}</div></div>
<div class="kpi"><div class="l">SPY vs 200 / 50 日线</div><div class="v">{now["spy"]/now["spy_ma200"]-1:+.1%}</div><div class="sub">距 200 日线；距 50 日线 {now["spy"]/now["spy_ma50"]-1:+.1%}</div></div>
<div class="kpi"><div class="l">VIX / VIX3M</div><div class="v {"bad" if now["vix_ts"]>1 else "good"}">{now["vix"]:.1f} / {now["vix_ts"]:.2f}</div><div class="sub">比值 &gt;1 = 期限结构倒挂（短期恐慌）</div></div>
<div class="kpi"><div class="l">个股宽度（{now["breadth_date"]}）</div><div class="v">{pct(now["breadth200"],0)}</div><div class="sub">2,250 只股票在 200 日线上；50 日线上 {pct(now["breadth50"],0)}</div></div>
<div class="kpi"><div class="l">波动目标仓位（SPY 20 日波动 {pct(now["rv20"],0)}）</div><div class="v">{pct(now["expo_vt"],0)}</div><div class="sub">= 15% ÷ 实际波动</div></div>
<div class="kpi"><div class="l">杠杆 ETF 规则</div><div class="v" style="font-size:17px">{lev_txt}</div><div class="sub">纳指 20 日波动 {pct(now["qqq_rv20"],0)}</div></div>
</div>
<div class="card"><h3 style="margin-top:0">8 个信号</h3><ul class="sig">{sig_rows}</ul>
<div class="cv" style="margin-top:14px"><canvas id="cScore"></canvas></div><div class="sub">市场状态分（周）与 SPY（对数，右轴）。分数掉到 45 以下的时期基本覆盖了 2008、2011、2015–16、2018 底、2020、2022 的大跌。</div></div>
<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr))">
<div class="card"><h3 style="margin-top:0">板块动量排名（6+12 月）</h3><div class="tw"><table><tr><th>#</th><th>板块</th><th class="num">动量</th><th class="num">近 1 月</th><th>200线</th></tr>{sec_rows}</table></div>
<div class="sub">底色 = 板块轮动策略本月持有的 Top 3：{", ".join(now["rot_picks"])}。前三名是医疗、能源、必需消费 —— 资金在往防守板块走，跟状态分偏弱一致。</div></div>
<div class="card"><h3 style="margin-top:0">个股宽度（% 在 200 日线上）</h3><div class="cv" style="height:260px"><canvas id="cBreadth"></canvas></div></div>
</div>
<div class="card"><h3 style="margin-top:0">风险调整动量 Top 25（个股）</h3>
<div class="sub">排名 = 12-1 月动量 ÷ 6 个月波动；只看在 200 日线上、6 月波动 &gt;20% 的股票（排除被收购锁价的）。这是候选名单，不是买入清单 —— 进场看第七、八部分的买点规则和止损。</div>
<div class="tw"><table><tr><th>#</th><th>代号</th><th>行业</th><th class="num">12-1 月动量</th><th class="num">年化波动</th><th class="num">距 52 周高</th><th class="num">近 1 月</th></tr>{stk_rows}</table></div></div>

<h2 id="research">三、量化研究：哪些方法真正有效</h2>
<p>下面是学术界和对冲基金几十年验证过的方法，按「对散户有没有用」打分。每个都在第四部分用真实数据回测过。</p>
<div class="method">
<div class="card"><h3>1. 趋势跟随（时间序列动量）<span class="tag t-good">核心</span></h3>资产涨在 200 日线上 / 过去 12 个月跑赢现金就持有，否则离场。Moskowitz、Ooi & Pedersen（2012）在 58 个市场验证；Hurst 等（2017）回测 100 年都有效。<b>主要价值是躲过大熊市</b>（2008、2022），代价是来回打脸、少赚反弹。</div>
<div class="card"><h3>2. 横截面动量<span class="tag t-good">核心</span></h3>买过去 12 个月（剔除最近 1 个月）涨最多的股票。Jegadeesh & Titman（1993）发现，至今仍是最强的因子之一。弱点：熊市反弹时会「动量崩盘」（Daniel & Moskowitz 2016），所以要配合市场状态。用「动量 ÷ 波动」排名效果更稳（Barroso & Santa-Clara 2015）。</div>
<div class="card"><h3>3. 波动率管理<span class="tag t-good">核心</span></h3>市场越乱，仓位越小：仓位 = 目标波动 ÷ 实际波动。Moreira & Muir（2017）证明能提高夏普率。原理：高波动期的回报并不更高，但风险高很多。我们的测试里它是<b>单一方法夏普最高</b>的。</div>
<div class="card"><h3>4. 双动量 / 板块轮动<span class="tag t-good">实用</span></h3>Antonacci（2014）：先比相对强弱选最强的，再用绝对动量（是否跑赢现金）决定要不要持有。用 9 个板块 ETF 做，没有幸存者偏差，每月只看一次。</div>
<div class="card"><h3>5. 市场状态 / 宏观风险指标<span class="tag t-good">风险用</span></h3>信用利差（高收益债 vs 国债）往往领先股市（Gilchrist & Zakrajšek 2012）；VIX 期限结构倒挂代表短期恐慌；板块宽度、可选/必需消费比反映风险偏好。<b>综合起来预测「风险」很准，预测「涨幅」不准。</b></div>
<div class="card"><h3>6. 多资产风险平价<span class="tag t-mid">保守</span></h3>股、债、金、商品按波动倒数分配（桥水全天候思路），再加趋势过滤。回撤极小（约 10%），但回报也低，适合保本型资金。</div>
<div class="card"><h3>7. 低波动 / 质量 / 价值<span class="tag t-mid">长期有效，近年弱</span></h3>低波动异象（Frazzini & Pedersen 2014）、质量（Novy-Marx 2013、Asness QMJ）、价值（Fama-French）长期都有超额，但 2015 年后价值和低波动在美股明显落后。我们把「低波动」加进动量组合，2023–26 结果反而大幅变差 —— AI 行情里低波动＝错过龙头。</div>
<div class="card"><h3>8. 财报后漂移（PEAD）<span class="tag t-mid">可延伸</span></h3>财报大超预期的股票，之后 1–3 个月继续涨（Bernard & Thomas 1989）。可以和你的 /earnings-brief 财报简报结合，作为下一步研究。</div>
<div class="card"><h3>9. 杠杆 ETF 的数学<span class="tag t-bad">陷阱</span></h3>2 倍 ETF 每天再平衡，在震荡市会「波动损耗」（Cheng & Madhavan 2009）：指数来回跌涨回原点，2x ETF 却是亏的。所以 2x ETF <b>只适合在趋势向上、波动低的时候拿</b>，这正好是趋势 + 波动规则能判断的。</div>
<div class="card"><h3>10. 过拟合：最大的敌人<span class="tag t-bad">必读</span></h3>Harvey、Liu & Zhu（2016）：几百个已发表的「因子」大多是数据挖掘出来的；McLean & Pontiff（2016）：因子被发表后超额平均少约 1/3。所以本系统<b>所有参数都用业界标准值、不针对这段数据优化</b>，并检查参数换一换结果是否还稳。</div>
</div>

<h2 id="bt">四、回测结果（{o["start"]} – {o["end"]}，约 23 年）</h2>
<div class="note">怎么看：<b>年化</b>=每年平均回报；<b>最大回撤</b>=从最高点跌下来最多亏几成；<b>夏普</b>=每承担一单位风险换来多少回报（越高越好，&gt;0.7 已经很好）。★ = 进入组合的策略。</div>
<div class="card"><div class="tw"><table><tr><th>策略</th><th class="num">年化</th><th class="num">波动</th><th class="num">夏普</th><th class="num">最大回撤</th><th class="num">最差年</th><th class="num">平均仓位</th></tr>{strat_html}</table></div></div>
<div class="card"><h3 style="margin-top:0">资金曲线（对数）</h3><div class="chips" id="chips"></div><div class="cv"><canvas id="cEq"></canvas></div>
<h3>回撤</h3><div class="cv" style="height:220px"><canvas id="cDD"></canvas></div></div>
<div class="card"><h3 style="margin-top:0">分段和危机表现（累计回报）</h3><div class="tw"><table><tr><th>策略</th>{per_head}</tr>{per_html}</table></div>
<div class="sub">稳健/进取组合在 2008 只亏 9%/15%（SPY −46%）。代价：2015–2026 的长牛市里，稳健组合落后 SPY —— 这是风险控制的正常代价。</div></div>
<div class="card"><h3 style="margin-top:0">稳健性：换参数结果会不会崩？</h3><div class="tw"><table><tr><th>参数</th><th class="num">年化</th><th class="num">夏普</th><th class="num">最大回撤</th></tr>{rob_html}</table></div>
<div class="sub">100–250 日均线、不同状态阈值、10–20% 目标波动，结果都在同一范围 —— 说明效果来自方法本身，不是碰巧挑中某个参数。</div></div>

<h2 id="regime">五、市场状态模型：它能预测什么</h2>
<div class="card"><div class="tw"><table><tr><th>状态分</th><th class="num">占时间</th><th class="num">未来 3 月平均涨幅</th><th class="num">3 月上涨概率</th><th class="num">未来 1 月波动</th><th class="num">未来 3 月平均最大跌幅</th><th class="num">3 月内跌 &gt;10% 概率</th></tr>{pred_html}</table></div>
<div class="note">关键发现：<b>低分时未来平均涨幅并不低</b>（大跌后常有暴力反弹），但<b>波动和暴跌概率高 3–5 倍</b>。所以低分的正确反应是「降低仓位、降杠杆、收紧止损」，不是「做空」或「全部卖光等底」。</div></div>

<h2 id="stocks">六、个股动量回测（2,250 只美股，{o["stocks"]["s_spy"]["d"][0]} 起）</h2>
<div class="note">⚠️ 幸存者偏差：股票池是「今天还在交易的股票」，退市的、跌没了的不在里面，所以个股结果<b>偏乐观</b>。对照：全池等权 {pct(o["stocks"]["s_eq"]["stats"]["cagr"])}，高过 SPY {pct(o["stocks"]["s_spy"]["stats"]["cagr"])}，多出来的部分大多就是偏差。只有 3 年数据，看相对排名，别看绝对数字。</div>
<div class="card"><div class="tw"><table><tr><th>方法（每月换仓，等权）</th><th class="num">年化</th><th class="num">波动</th><th class="num">夏普</th><th class="num">最大回撤</th></tr>{stk_bt}</table></div>
<div class="cv" style="margin-top:12px"><canvas id="cStk"></canvas></div>
<div class="sub">结论：纯动量 Top50 和风险调整动量明显跑赢全池等权（扣掉偏差后仍有超额），但波动 40%+，单月可以亏 20%。加「低波动」反而毁了它。状态仓位在这 3 年（基本是牛市）少赚了，但降低了回撤 —— 和长期 ETF 测试一致。</div></div>

{TRADE}
<h2 id="howto">九、怎么用来提高你的回报</h2>
<div class="card"><h3 style="margin-top:0">每周一次（周末，10 分钟）</h3><ol>
<li>网站每个交易日早上自动更新（GitHub Actions）；本机可跑 <code>python 量化/run.py</code>。</li>
<li><b>看状态分 → 定总仓位：</b>≥75 进攻（100%）；45–75 中性（60%）；&lt;45 防守（20%）。</li>
<li><b>杠杆 ETF（QLD、TQQQ、个股 2x ETF 等）：</b>只在「状态 ≥75 + 纳指在 200 日线上 + 纳指 20 日波动 &lt;25%」时满仓；状态 45–75 减半；纳指跌破 200 日线 → 全部清掉。持有杠杆 ETF 的话，这是影响最大的一条。</li>
<li><b>持仓：</b>每只持股检查：出现「卖出」条件（收盘跌破 50 日线或 3×ATR 移动止损）就在下一个交易日卖。</li>
<li><b>选股和买入：</b>看「买入候选」里绿色的买点（52 周新高放量 / 收窄突破 / 回踩 20 日线），止损 = 买价 − 2×ATR，股数 = 账户 × 1% ÷ 止损距离。</li>
</ol></div>
<div class="card"><h3 style="margin-top:0">每月一次（月底）</h3><ol>
<li>板块轮动部分：持有动量 Top 3 板块 ETF；某个板块 12 个月动量不如现金 → 那份改放 IEF；状态 &lt;45 → 全部 IEF。</li>
<li>个股部分：跌出动量前 100 名、或跌破 200 日线的，换掉。</li>
</ol></div>
<div class="card"><h3 style="margin-top:0">建议的资金结构（进取组合的思路）</h3><ul>
<li><b>40% 板块动量轮动 + 状态过滤</b>（XLK/XLV/XLE… ETF，每月调一次）</li>
<li><b>30% 波动目标的大盘核心</b>（SPY/QQQ，仓位 = 15% ÷ 实际波动）</li>
<li><b>30% 进攻部分</b>：2x 杠杆 ETF 或动量个股，严格受 200 日线和状态分控制</li>
</ul><div class="sub">历史上这个结构年化 {pct(g["cagr"])}、最大回撤 {pct(g["mdd"])}，2008 金融危机期间 {pct(o['by_period']['combo_growth']['2008 金融危机'],0)}（SPY {pct(o['by_period']['bh']['2008 金融危机'],0)}）。不要求你全部照做 —— 哪怕只把「杠杆 ETF 规则」用上，就能避开最致命的回撤。</div></div>

<h2 id="limits">十、局限和风险（一定要读）</h2>
<div class="card"><ul>
<li><b>回测 ≠ 未来。</b>23 年里美股是全球最强市场，QQQ 尤其如此；选纳指做杠杆本身带有「事后知道它会赢」的偏差。</li>
<li><b>趋势规则会被打脸：</b>2011、2015–16、2018 年底这种「跌破又收回」的行情会连续小亏。坚持规则是最难的部分。</li>
<li><b>个股结果有幸存者偏差</b>，只有 3 年；ETF 部分没有这个问题。</li>
<li><b>没算税和汇率</b>；马来西亚/新加坡账户买美股 ETF 有 30% 股息预扣税，对高股息资产影响更大。</li>
<li><b>杠杆 ETF 的模拟</b>用 2× 日回报 − 融资成本 − 0.95% 费率，跟真实 QLD/TQQQ 接近，但单一个股 2x ETF 波动更大，规则应该更严。</li>
<li>这是研究工具，不是投资建议。所有决定和风险由你自己承担。</li>
</ul>
<div class="sub">文件（仓库 <code>量化/</code>）：<code>run.py</code>（一键运行）、<code>fetch_data.py</code>（下载数据）、<code>quant_lab.py</code>（模型+回测）、<code>build_report.py</code>（生成本页）、<code>signals.py</code>（进出场回测 + 今日信号）、<code>oversold.py</code>、<code>trade_section.py</code>。参考文献：Faber 2007；Jegadeesh &amp; Titman 1993；Moskowitz, Ooi &amp; Pedersen 2012；Hurst, Ooi &amp; Pedersen 2017；Moreira &amp; Muir 2017；Barroso &amp; Santa-Clara 2015；Daniel &amp; Moskowitz 2016；Antonacci 2014；Frazzini &amp; Pedersen 2014；Novy-Marx 2013；Gilchrist &amp; Zakrajšek 2012；Cheng &amp; Madhavan 2009；Harvey, Liu &amp; Zhu 2016；McLean &amp; Pontiff 2016。</div></div>
</details>
</div>
<script>
const D={json.dumps(chart_data, ensure_ascii=False)};
const SK={json.dumps(stock_chart, ensure_ascii=False)};
const SC={json.dumps(o["score_hist"])};
const BR={json.dumps(o["breadth_hist"])};
function tg(){{const r=document.documentElement;const dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;r.dataset.theme=dark?'light':'dark';location.hash||0;drawAll()}}
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const PAL=['#2f5bea','#e8702a','#14895a','#c8372d','#8e44ad','#b7791f','#1e9bd7','#d63384','#6c757d','#20c997','#795548','#17a2b8'];
let charts=[];const ON=new Set(['bh','qqq','combo_core','combo_growth','l2bh_QQQ','l2ma_QQQ']);
function base(){{Chart.defaults.color=css('--mute');Chart.defaults.borderColor=css('--line');Chart.defaults.font.family='system-ui';}}
function drawAll(){{charts.forEach(c=>c.destroy());charts=[];base();
 const keys=Object.keys(D);
 const ds=keys.map((k,i)=>({{label:D[k].n,data:D[k].eq,borderColor:PAL[i%PAL.length],borderWidth:k.startsWith('combo')?2.6:1.4,pointRadius:0,hidden:!ON.has(k)}}));
 charts.push(new Chart(cEq,{{type:'line',data:{{labels:D.bh.d,datasets:ds}},options:{{maintainAspectRatio:false,animation:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+c.parsed.y.toFixed(2)+'x'}}}}}},scales:{{x:{{ticks:{{maxTicksLimit:8}}}},y:{{type:'logarithmic'}}}}}}}}));
 const dd=keys.map((k,i)=>({{label:D[k].n,data:D[k].dd.map(x=>x*100),borderColor:PAL[i%PAL.length],borderWidth:1.2,pointRadius:0,hidden:!ON.has(k)}}));
 charts.push(new Chart(cDD,{{type:'line',data:{{labels:D.bh.d,datasets:dd}},options:{{maintainAspectRatio:false,animation:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{maxTicksLimit:8}}}},y:{{ticks:{{callback:v=>v+'%'}}}}}}}}}}));
 const chips=document.getElementById('chips');chips.innerHTML='';
 keys.forEach((k,i)=>{{const l=document.createElement('label');l.innerHTML=`<input type=checkbox ${{ON.has(k)?'checked':''}}><span style="color:${{PAL[i%PAL.length]}}">●</span> ${{D[k].n}}`;
  l.querySelector('input').onchange=e=>{{e.target.checked?ON.add(k):ON.delete(k);charts[0].data.datasets[i].hidden=!e.target.checked;charts[1].data.datasets[i].hidden=!e.target.checked;charts[0].update();charts[1].update()}};chips.appendChild(l)}});
 charts.push(new Chart(cScore,{{data:{{labels:SC.d,datasets:[{{type:'line',label:'状态分（10 日平均）',data:SC.s,borderColor:css('--acc'),backgroundColor:'rgba(47,91,234,.12)',borderWidth:1,pointRadius:0,yAxisID:'y',fill:'origin'}},{{type:'line',label:'SPY',data:SC.spy,borderColor:css('--mute'),borderWidth:1.4,pointRadius:0,yAxisID:'y2'}}]}},
  options:{{maintainAspectRatio:false,animation:false,interaction:{{mode:'index',intersect:false}},scales:{{x:{{ticks:{{maxTicksLimit:8}}}},y:{{min:0,max:100}},y2:{{position:'right',type:'logarithmic',grid:{{display:false}}}}}}}}}}));
 charts.push(new Chart(cBreadth,{{type:'line',data:{{labels:BR.d,datasets:[{{label:'% 在 200 日线上',data:BR.b,borderColor:css('--acc'),pointRadius:0,borderWidth:1.6,fill:{{target:{{value:50}},above:'#14895a22',below:'#c8372d22'}}}}]}},options:{{maintainAspectRatio:false,animation:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{maxTicksLimit:6}}}},y:{{min:0,max:100}}}}}}}}));
 const sk=Object.keys(SK);
 charts.push(new Chart(cStk,{{type:'line',data:{{labels:SK.s_spy.d,datasets:sk.map((k,i)=>({{label:SK[k].n,data:SK[k].eq,borderColor:PAL[i%PAL.length],borderWidth:k==='s_spy'?2.4:1.3,pointRadius:0}}))}},options:{{maintainAspectRatio:false,animation:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{labels:{{boxWidth:10,font:{{size:11}}}}}}}},scales:{{x:{{ticks:{{maxTicksLimit:6}}}}}}}}}}));
}}
drawAll();
document.getElementById('more').addEventListener('toggle',e=>{{if(e.target.open)drawAll()}});
</script></body></html>"""
open(OUT, "w", encoding="utf-8").write(HTML)
print("写入", os.path.abspath(OUT))
