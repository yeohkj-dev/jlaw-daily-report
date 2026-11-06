"""生成报告里的「选股 · 买 · 卖 · 拿现金」部分（读 signals.json + oversold.json）。"""
import json, os, html

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def pct(x, d=0, sign=False):
    if x is None:
        return "–"
    return f"{x*100:+.{d}f}%" if sign else f"{x*100:.{d}f}%"


def cls(x):
    return "pos" if x is not None and x > 0 else ("neg" if x is not None and x < 0 else "")


def build():
    S = json.load(open(os.path.join(DATA, "signals.json"), encoding="utf-8"))
    OS = json.load(open(os.path.join(DATA, "oversold.json")))
    G, now = S["grid"], S["now"]
    EN, EX = S["entries"], S["exits"]

    # ---- 进出场矩阵（动量名单）：均 R
    best = max((v["avgR"], k) for k, v in G.items() if v and k.endswith("动量名单") and v["n"] > 300)[1]
    head = "".join(f'<th class="num">{EX[x][0]}</th>' for x in EX)
    rows = ""
    for e in EN:
        rows += f'<tr><td><b>{EN[e][0]}</b><div class="desc">{html.escape(EN[e][1])}</div></td>'
        for x in EX:
            v = G.get(f"{e}|{x}|动量名单")
            if not v:
                rows += "<td></td>"; continue
            hl = ' style="outline:2px solid var(--pos);outline-offset:-2px"' if f"{e}|{x}|动量名单" == best else ""
            rows += (f'<td class="num"{hl}><b class="{cls(v["avgR"])}">{v["avgR"]:+.2f}R</b><div class="desc">胜率 {pct(v["win"])} · 均 {pct(v["avg"],1,True)}'
                     f'<br>赚 {pct(v["avg_win"])} / 亏 {pct(v["avg_loss"])} · {v["hold"]:.0f} 天 · {v["n"]} 笔</div></td>')
        rows += "</tr>"

    # ---- 名单 vs 普通上升股
    cmp = ""
    for e in ["E2", "E3", "E4"]:
        a, b = G.get(f"{e}|X2|动量名单"), G.get(f"{e}|X2|普通上升股")
        if a and b:
            cmp += (f'<tr><td>{EN[e][0]}</td><td class="num">{pct(a["win"])} / {pct(b["win"])}</td>'
                    f'<td class="num"><b>{a["avgR"]:+.2f}R</b> / {b["avgR"]:+.2f}R</td><td class="num">{a["pf"]:.2f} / {b["pf"]:.2f}</td></tr>')

    # ---- 提高胜率的条件
    base = S["filters"][0]
    frows = ""
    for f in S["filters"]:
        dw = f["win"] - base["win"]
        frows += (f'<tr><td>{html.escape(f["name"])}</td><td class="num">{f["n"]}</td>'
                  f'<td class="num"><b>{pct(f["win"])}</b> <small class="{cls(dw)}">{dw*100:+.0f}</small></td>'
                  f'<td class="num {cls(f["avg"])}">{pct(f["avg"],1,True)}</td><td class="num">{f["avgR"]:+.2f}R</td><td class="num">{f["pf"]:.2f}</td></tr>')

    # ---- 什么时候拿现金
    def grp_rows(d):
        return "".join(f'<tr><td>{k}</td><td class="num">{v["n"]}</td><td class="num">{pct(v["win"])}</td><td class="num {cls(v["avg"])}">{pct(v["avg"],1,True)}</td><td class="num">{v["pf"]:.2f}</td></tr>'
                       for k, v in d.items() if v)
    yrows = grp_rows(S["years"])

    # ---- 今天：持仓
    gate = now["gate"]
    gate_cls = {"进攻": "good", "谨慎": "mid", "现金": "bad"}[gate]
    gate_rule = {"进攻": "正常开新仓，单笔风险 1% 账户", "谨慎": "只做最好的形态，单笔风险减到 0.5%（杠杆 ETF 看第二部分的规则）",
                 "现金": "不开新仓，让止损把仓位自然清掉"}[gate]
    hrows = ""
    for h in now["holds"]:
        via = ("经 " + "、".join(sorted(set(h["via"])))) if h.get("via") else "正股"
        b50 = h.get("br50")
        trig = (f'{b50["date"][5:]} 收 {b50["px"]:.2f}<div class="desc">之后又 {pct(b50["chg"],0,True)}</div>' if b50 else "–")
        b20 = h.get("br20")
        trig20 = (f'{b20["date"][5:]} 收 {b20["px"]:.2f}' if b20 else "–")
        col = {1: "good", 2: "mid", 3: "bad"}[h["lvl"]]
        hrows += (f'<tr><td><b>{h["t"]}</b><div class="desc">{via}</div></td><td class="{col}"><b>{h["exit"]}</b></td>'
                  f'<td class="num">{h["close"]:.2f}</td><td class="num {cls(h["ext"])}">{pct(h["ext"],0,True)}</td>'
                  f'<td class="num">{trig20}</td><td class="num">{trig}</td><td class="num">{h["ma50"]:.2f}</td></tr>')

    crows = ""
    for c in now["cands"][:30]:
        ok = any("✓" in s for s in c["setup"])
        crows += (f'<tr><td>{c["rank"]}</td><td><b>{c["t"]}</b></td><td class="{"good" if ok else ""}">{html.escape(" / ".join(c["setup"]))}</td>'
                  f'<td class="num">{c["close"]:.2f}</td><td class="num {cls(c["ext"])}">{pct(c["ext"],0,True)}</td>'
                  f'<td class="num">{c["stop"]:.2f}<div class="desc">−{(c["close"]-c["stop"])/c["close"]*100:.0f}%</div></td><td class="num">{c["ma50"]:.2f}</td></tr>')
    n_setups = sum(any("✓" in s for s in c["setup"]) for c in now["cands"][:30])
    o20 = OS["20"]; o60 = OS["60"]
    e3x2 = G["E3|X2|动量名单"]; e1x3 = G["E1|X3|动量名单"]; e2x1 = G["E2|X1|动量名单"]; e1x5 = G["E1|X5|动量名单"]
    ra, br_ = S["reg_all"], S["br_all"]
    weak = br_.get("宽度 <40%"); strong = br_.get("宽度 >60%")

    PRIVATE = bool(now["holds"])
    lev_names = "、".join(sorted({v for h in now["holds"] for v in (h.get("via") or [])})) or "杠杆 ETF"
    HOLD_CARD = f"""<div class="card"><h3 style="margin-top:0">你的持仓：出场信号（杠杆 ETF 看正股）</h3>
<div class="tw"><table><tr><th>正股</th><th>信号</th><th class="num">收盘</th><th class="num">离 20 日线</th><th class="num">跌破 20 日线</th><th class="num">跌破 50 日线（卖出信号）</th><th class="num">50 日线</th></tr>{hrows}</table></div>
<div class="sub">持仓来自你 Portfolio Dashboard 最近的结单，之后有买卖就以你实际为准。「跌破 50 日线」那一列是规则<b>原本会叫你卖的日期和价格</b>，后面的百分比是那之后又跌了多少。</div></div>

""" if PRIVATE else ""
    OVERSOLD = f"""<div class="note"><b>现在已经跌深了，还要卖吗？</b>回测了 {o20["n"]:,} 次同样的情况：前强势股（一年涨 &gt;50%）跌到 20 日线下 20% 以上。之后 20 天：
中位数 {pct(o20["med"],1,True)}，{pct(o20["bounce10"])} 的机会出现 &gt;10% 反弹，但也有 {pct(o20["worse10"])} 的机会再跌 10% 以上。60 天内 {pct(o60["worse10"])} 会再跌 10% 以上。
<b>结论：这是抛硬币，而且波动极大。</b>
<br>• <b>2 倍杠杆 ETF（{lev_names}）</b>：在这种高波动里每天都在损耗，规则是优先处理掉。
<br>• <b>正股</b>：不一定要卖在最低点。合理的做法是先减一半，剩下的在反弹 10% 或碰到 20 日线时卖；如果重新站回 50 日线、又进动量名单，再按买点规则买回。</div>

""" if PRIVATE else f"""<div class="note"><b>持股已经跌深了（远低于 20 日线），还要卖吗？</b>回测了 {o20["n"]:,} 次同样的情况：前强势股（一年涨 &gt;50%）跌到 20 日线下 20% 以上。之后 20 天：
中位数 {pct(o20["med"],1,True)}，{pct(o20["bounce10"])} 的机会出现 &gt;10% 反弹，但也有 {pct(o20["worse10"])} 的机会再跌 10% 以上。60 天内 {pct(o60["worse10"])} 会再跌 10% 以上。
<b>结论：这是抛硬币，而且波动极大。</b>
<br>• <b>2 倍杠杆 ETF</b>：在这种高波动里每天都在损耗，规则是优先处理掉。
<br>• <b>正股</b>：不一定要卖在最低点。合理的做法是先减一半，剩下的在反弹 10% 或碰到 20 日线时卖；如果重新站回 50 日线、又进动量名单，再按买点规则买回。</div>

"""
    return f"""
<h2 id="trade">七、选股 · 买入 · 卖出 · 什么时候拿现金</h2>
<div class="sub">个股规则回测：2,250 只美股，{S["period"][0]} 至 {S["period"][1]}，共 {S["n_trades"]:,} 笔模拟交易。信号用收盘判断、次日开盘成交。每笔都有初始止损 = 买价 − 2×ATR（这段距离 = 1R）。</div>

<div class="card" style="border:2px solid var(--acc)"><h3 style="margin-top:0">一句话答案：量化在每一步帮你什么</h3>
<div class="tw"><table><tr><th>步骤</th><th>量化规则</th><th>回测证据</th></tr>
<tr><td><b>1. 选股</b></td><td>每周五按「12-1 月动量 ÷ 波动」排名，只看 Top 100、在 200 日线上的股票</td><td>同样的突破买点，动量名单的平均收益 {G["E3|X2|动量名单"]["avgR"]:+.2f}R，普通上升股只有 {G["E3|X2|普通上升股"]["avgR"]:+.2f}R</td></tr>
<tr><td><b>2. 买入</b></td><td>在名单里等<b>52 周新高 + 放量</b>突破（或刚进名单），次日开盘买；止损 = 买价 − 2×ATR</td><td>突破 + 50 日线出场：{e3x2["avgR"]:+.2f}R/笔，盈亏比 {e3x2["pf"]:.2f}</td></tr>
<tr><td><b>3. 卖出</b></td><td><b>收盘跌破 50 日线</b>或<b>从最高收盘回落 3×ATR</b>就卖（不要用 20 日线，太紧）</td><td>20 日线出场：只有 {e2x1["avgR"]:+.2f}R；50 日线和 3×ATR 出场的结果高 3–5 倍</td></tr>
<tr><td><b>4. 拿现金</b></td><td>现金不是靠预测，而是规则的结果：持仓跌破 50 日线卖掉，又没有新的买点 → 自然就是现金。杠杆 ETF 和大盘仓位另外看状态分</td><td>状态分低时，3 个月内跌 &gt;10% 的概率约为高分时的 5 倍（见第五部分）</td></tr>
<tr><td><b>5. 仓位</b></td><td>每笔最多亏账户的 1%：股数 = 账户 × 1% ÷ (买价 − 止损价)。状态「谨慎」时减到 0.5%</td><td>胜率只有 30–40%，连亏 8–10 笔很正常，仓位小才撑得过去</td></tr>
</table></div></div>

<div class="note"><b>关于「提高胜率」，最重要的一点：</b>动量/趋势交易的胜率天生只有 30–40%。赚钱靠的是<b>赚的时候赚得多</b>（平均 +14%），<b>亏的时候亏得少</b>（平均 −6%）。
胜率最高的规则是「固定持有 20 天」（{pct(e1x5["win"])}），但它每笔只赚 {e1x5["avgR"]:+.2f}R；胜率较低的「3×ATR 移动止损」（{pct(e1x3["win"])}）每笔反而赚 {e1x3["avgR"]:+.2f}R。
<b>为了提高胜率而太早卖，通常会让你少赚。</b>该追求的是每笔的期望收益（平均 R），不是胜率。</div>

<h3>A. 进场 × 出场：哪个组合最好（动量名单，每格 = 平均每笔赚多少 R）</h3>
<div class="card"><div class="tw"><table><tr><th>进场 \\ 出场</th>{head}</tr>{rows}</table></div>
<div class="sub">绿框 = 最好的组合。1R = 买价到止损的距离：+0.25R 的意思是，每冒 1% 账户风险，平均赚 0.25%。规律很清楚：出场放宽（50 日线、3×ATR）比出场收紧（20 日线、+3R 卖一半）好得多，因为它让赢家跑得更远。</div></div>

<h3>B. 动量筛选到底有没有用？（同样的买点，出场都是跌破 50 日线）</h3>
<div class="card"><div class="tw"><table><tr><th>进场</th><th class="num">胜率 名单 / 普通</th><th class="num">平均 R</th><th class="num">盈亏比</th></tr>{cmp}</table></div>
<div class="sub">对<b>突破</b>和<b>收窄突破</b>买点有明显帮助（收益约翻倍）；对<b>回踩 20 日线</b>买点帮助不大。胜率本身几乎一样，提高的是赢的时候的幅度。</div></div>

<h3>C. 哪些条件能提高胜率（所有进场，跌破 50 日线出场）</h3>
<div class="card"><div class="tw"><table><tr><th>条件</th><th class="num">笔数</th><th class="num">胜率（vs 全部）</th><th class="num">平均</th><th class="num">平均 R</th><th class="num">盈亏比</th></tr>{frows}</table></div>
<div class="sub">发现：
① <b>市场弱的时候买最强的股票</b>（宽度 &lt;40% 或 SPY 在 50 日线下）胜率和收益都最高。大跌之后率先站稳的领涨股，就是下一波的赢家。
② 买在<b>当天弱势收盘</b>（下 1/3）比追当天强势收盘胜率高。
③ 排名前 20 和「离 50 日线很远」胜率不高，但平均收益高：少数大赢家拉高了平均。
④ 放量本身没有提高胜率。
⚠️ 只有 3 年数据，弱市样本主要来自 2022 年底、2023 年 10 月和 2025 年 4 月三段，结论偏乐观。</div></div>

<h3>D. 什么时候应该拿现金？</h3>
<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr))">
<div class="card" style="margin:0"><b>按进场时的市场宽度</b><div class="tw"><table><tr><th>宽度</th><th class="num">笔数</th><th class="num">胜率</th><th class="num">平均</th><th class="num">盈亏比</th></tr>{grp_rows(br_)}</table></div></div>
<div class="card" style="margin:0"><b>按进场时的状态分</b><div class="tw"><table><tr><th>状态</th><th class="num">笔数</th><th class="num">胜率</th><th class="num">平均</th><th class="num">盈亏比</th></tr>{grp_rows(ra)}</table></div></div>
<div class="card" style="margin:0"><b>按年份</b><div class="tw"><table><tr><th>年</th><th class="num">笔数</th><th class="num">胜率</th><th class="num">平均</th><th class="num">盈亏比</th></tr>{yrows}</table></div></div>
</div>
<div class="note">结论分两半，看起来矛盾，其实不矛盾：
<br>• <b>已经持有的仓位和杠杆</b>：市场转坏时要减。23 年 ETF 数据显示，状态 &lt;45 分时暴跌概率是平时的 5 倍，杠杆 ETF 在这种时候最伤（这次的回落就是例子）。
<br>• <b>新的买入</b>：市场弱的时候反而是最好的进场期（宽度 &lt;40% 时胜率 {pct(weak["win"]) if weak else "–"}，宽度 &gt;60% 时只有 {pct(strong["win"]) if strong else "–"}），<b>前提是只买还在动量名单、还守在 50 日线上的强股</b>，而且有止损。
<br>• 所以「拿现金」的正确方法 = <b>止损和 50 日线规则把你自动带出场 → 拿着现金 → 等大跌后领涨股出现突破，再用小仓位进场</b>。不要在市场狂热（宽度 &gt;60%、状态满分）的时候追加重仓。2022 年这样的单边熊市，新买的胜率只有 24%：那时候止损会让你一直很小仓位，这正是规则保护你的方式。</div>

<h2 id="today">八、今天的买卖信号（{now["date"]} 收盘）</h2>
<div class="grid">
<div class="kpi"><div class="l">市场开关</div><div class="big {gate_cls}">{gate}</div><div class="sub">状态分 {now["score"]:.0f} · 个股宽度 {pct(now["breadth"])}</div></div>
<div class="kpi" style="grid-column:span 2"><div class="l">今天的规则</div><div class="v" style="font-size:17px">{gate_rule}</div><div class="sub">动量 Top 30 里今天出现买点的：{n_setups} 只</div></div>
</div>

{HOLD_CARD}{OVERSOLD}<div class="card"><h3 style="margin-top:0">买入候选：动量 Top 30 + 今天的买点状态</h3>
<div class="sub">绿色 = 今天出现回测里的买点（下一个交易日开盘买）。「等回踩」= 离 20 日线太远，不追。止损 = 收盘 − 2×ATR，用来算股数。市场开关是「谨慎」时只做绿色的、风险 0.5%。</div>
<div class="tw"><table><tr><th>排名</th><th>代号</th><th>买点</th><th class="num">收盘</th><th class="num">离 20 日线</th><th class="num">止损</th><th class="num">50 日线</th></tr>{crows}</table></div></div>
"""
