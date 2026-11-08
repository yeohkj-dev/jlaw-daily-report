"""综合观察名单：量化红绿灯 + J Law 每日选股 + Luk 选股 + 回测有效的K线形态，合成一张「今天怎么做」清单。

读：量化/data/results.json、signals.json、stocks/*.json（run.py 产生）
    每日选股/<最新>.csv 和 .md（J Law）、Luk选股/<最新>.json
写：量化/data/combined.html（分页内容）
K线形态只用 回测/K线形态/README.md 里评为「有效」的那几种；其余形态回测是噪音，不显示。
"""
import glob
import html
import json
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")
sys.path.insert(0, os.path.join(ROOT, "回测", "K线形态"))
from patterns import detect          # noqa: E402
from patterns2 import detect2        # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "tools"))
from rs_rating import load as rs_load, badge as rs_badge, stale_note as rs_stale, tv_link   # noqa: E402
RS = rs_load()

# 回测「有效」的形态（回测/K线形态/README.md）
BULL = {"stopping_vol": "低位放量长下影", "three_soldiers": "红三兵", "gap_up": "向上跳空",
        "island_bottom": "岛形底", "oops_bull": "Oops 低开收回"}
BEAR = {"three_crows": "三只乌鸦", "bear_harami": "看跌孕线", "three_inside_down": "三内降",
        "rsi2_ob_dn": "RSI2>95 且在 200 日线下"}
LOOKBACK = 3          # 最近 3 个交易日内出现都算

o = json.load(open(os.path.join(DATA, "results.json"), encoding="utf-8"))
S = json.load(open(os.path.join(DATA, "signals.json"), encoding="utf-8"))
qgate = S["now"]["gate"]
# J Law 大盘状态（大盘报告/大盘历史.csv 最后一行）。两个灯取较严的那个。
jstate = ""
hist = os.path.join(ROOT, "大盘报告", "大盘历史.csv")
if os.path.exists(hist):
    last = open(hist, encoding="utf-8-sig").read().strip().splitlines()[-1].split(",")
    jstate = last[1] if len(last) > 1 else ""
ORDER = ["现金", "谨慎", "进攻"]
jgate = {"🟢": "进攻", "🟡": "谨慎", "🔴": "现金"}.get(jstate[:1])
gate = min([qgate] + ([jgate] if jgate else []), key=ORDER.index)

# ---------------------------------------------------------------- J Law
csv = sorted(glob.glob(os.path.join(ROOT, "每日选股", "*.csv")))[-1]
jl = pd.read_csv(csv, encoding="utf-8-sig")
md = open(csv[:-4] + ".md", encoding="utf-8").read()
m = re.search(r"1M ≥([\d.]+)%、6M ≥([\d.]+)%", md)
min1m, min6m = (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)
JL = {}
for _, r in jl.iterrows():
    t = r["代码"]
    if r.get("就绪") == "META":
        JL[t] = ("META 回调就绪", r["META止损"])
    elif r.get("就绪") == "VCP":
        JL[t] = ("VCP 突破就绪", r["VCP止损"])
    elif pd.notna(r["META优势"]) and r["META优势"] >= 3 and r["META止损%"] <= 8:
        JL[t] = ("META 观察", r["META止损"])
    elif (r["得分(8)"] >= 5 and r["VCP状态"] in ("等突破", "刚突破") and r["VCP止损%"] <= 8
          and r["1个月%"] >= min1m and r["6个月%"] >= min6m):
        JL[t] = ("VCP 观察", r["VCP止损"])
JL_NAME = dict(zip(jl["代码"], jl["名称"]))
JL_IND = dict(zip(jl["代码"], jl["行业"]))

# ---------------------------------------------------------------- Luk
LUK = {}
lj = sorted(glob.glob(os.path.join(ROOT, "Luk选股", "*.json")))
LUKN = {"strong": "Luk 强势", "gap": "Luk 跳空", "leader": "Luk 龙头"}
if lj:
    for k, names in json.load(open(lj[-1], encoding="utf-8"))["lists"].items():
        for t in names:
            LUK.setdefault(t, []).append(LUKN.get(k, k))

# ---------------------------------------------------------------- 量化动量名单
Q = {c["t"]: c for c in S["now"]["cands"]}

# ---------------------------------------------------------------- 每只股票
rows = []
for t in sorted(set(JL) | set(LUK) | set(Q)):
    p = os.path.join(DATA, "stocks", t + ".json")
    if not os.path.exists(p):
        continue
    d = json.load(open(p))
    df = pd.DataFrame({k: d[k] for k in "ohlcv"}, index=pd.to_datetime(d["d"])).dropna()
    if len(df) < 260:
        continue
    P, _ = detect(df)
    P2, _ = detect2(df)
    P.update(P2)
    bull = [n for k, n in BULL.items() if k in P and P[k].iloc[-LOOKBACK:].any()]
    bear = [n for k, n in BEAR.items() if k in P and P[k].iloc[-LOOKBACK:].any()]
    c = df["c"]
    close, ma50, ma200 = c.iloc[-1], c.rolling(50).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
    q = Q.get(t)
    qbuy = [s.replace(" ✓", "") for s in (q["setup"] if q else []) if "✓" in s]
    jl_tag, jl_stop = JL.get(t, (None, None))
    systems = []
    if jl_tag: systems.append("J Law")
    if q: systems.append("量化")
    if t in LUK: systems.append("Luk")
    ready = bool(jl_tag and "就绪" in jl_tag) or bool(qbuy)
    stop = jl_stop if jl_tag and pd.notna(jl_stop) else (q["stop"] if q else None)

    if bear or close < ma50:
        grade = "C"
        why = ("出现回测有效的看跌K线：" + "、".join(bear)) if bear else "收盘在 50 日线下面"
    elif ready:
        grade = "A"
        why = "买点出现：" + "、".join(([jl_tag] if jl_tag and "就绪" in jl_tag else []) + qbuy)
    elif len(systems) >= 2:
        grade = "B"
        why = "多个系统同时看好，还没到买点"
    else:
        continue      # 只在一个名单、也没买点：不显示，免得太长
    rows.append(dict(t=t, name=JL_NAME.get(t, ""), ind=JL_IND.get(t) or "", grade=grade, why=why,
                     systems=systems, jl=jl_tag, luk=LUK.get(t, []), qrank=q["rank"] if q else None,
                     bull=bull, bear=bear, close=close, ma50=ma50, stop=stop,
                     score=len(systems) * 10 + len(bull) * 3 - (q["rank"] / 100 if q else 0)))

rows.sort(key=lambda r: -r["score"])
A = [r for r in rows if r["grade"] == "A"]
B = [r for r in rows if r["grade"] == "B"]
C = [r for r in rows if r["grade"] == "C" and ("J Law" in r["systems"] or "量化" in r["systems"])][:15]   # 只看 J Law / 量化名单里的，最多 15 只

# ---------------------------------------------------------------- HTML
LIGHT = {"进攻": ("#2E7D32", "🟢 绿灯"), "谨慎": ("#B26A00", "🟡 黄灯"), "现金": ("#C62828", "🔴 红灯")}
fg, light = LIGHT[gate]
size = {"进攻": "正常仓位（每笔最多亏账户 1%）", "谨慎": "半仓（每笔最多亏账户 0.5%）", "现金": "红灯：先不买，只观察"}[gate]
date = S["now"]["date"]


def chips(r):
    out = []
    if r["jl"]:
        out.append(f'<span class="ch jl">{html.escape(r["jl"])}</span>')
    if r["qrank"]:
        out.append(f'<span class="ch q">量化动量 #{r["qrank"]}</span>')
    for x in r["luk"]:
        out.append(f'<span class="ch lk">{html.escape(x)}</span>')
    for x in r["bull"]:
        out.append(f'<span class="ch up">▲ {html.escape(x)}</span>')
    for x in r["bear"]:
        out.append(f'<span class="ch dn">▼ {html.escape(x)}</span>')
    return " ".join(out)


def table(rs, action):
    if not rs:
        return '<div class="empty">今天没有。</div>'
    body = ""
    for r in rs:
        stop = f'{r["stop"]:.2f}<small>（−{1 - r["stop"] / r["close"]:.0%}）</small>' if r["stop"] and r["stop"] < r["close"] else "—"
        body += (f'<tr><td>{tv_link(r["t"], RS)}{rs_badge(RS, r["t"])}<div class="sub">{html.escape(str(r["name"])[:22])}</div></td>'
                 f'<td>{chips(r)}<div class="sub">{html.escape(r["why"])}</div></td>'
                 f'<td class="num">{r["close"]:.2f}</td><td class="num">{stop}</td><td>{action(r)}</td></tr>')
    return ('<div class="tw"><table><tr><th>股票</th><th>哪些系统看好 / 原因</th><th class="num">收盘</th>'
            f'<th class="num">止损</th><th>怎么做</th></tr>{body}</table></div>')


actA = (lambda r: "明天开盘买，" + ("半仓" if gate == "谨慎" else "正常仓位") + "，马上设止损") if gate != "现金" else (lambda r: "红灯：先不买，放进观察；转黄灯再买")
actB = lambda r: "放进观察，等买点出现"
actC = lambda r: "有持有的话：明天卖 / 收紧止损；没有就别买"

TAB = f"""<style>
.cw{{max-width:1080px;margin:0 auto;padding:4px 16px 24px;font-size:14px;line-height:1.65;color:#222}}
.cw .card{{background:#fff;border:1px solid #e3e6eb;border-radius:12px;padding:14px 16px;margin:12px 0}}
.cw h3{{margin:0 0 4px;font-size:17px}}.cw .sub{{color:#666;font-size:12px}}.cw .empty{{color:#666;padding:6px 0}}
.cw .tw{{overflow-x:auto}}.cw table{{border-collapse:collapse;width:100%;font-size:13.5px}}
.cw th,.cw td{{padding:7px 8px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}}.cw th{{color:#666;font-size:12px;white-space:nowrap}}
.cw .num{{text-align:right;white-space:nowrap}}
.cw .ch{{display:inline-block;font-size:11.5px;padding:1px 7px;border-radius:99px;margin:1px 2px 1px 0;white-space:nowrap}}
.cw .jl{{background:#E3F2FD;color:#0D47A1}}.cw .q{{background:#EDE7F6;color:#4527A0}}.cw .lk{{background:#FFF3E0;color:#E65100}}
.cw .up{{background:#E8F5E9;color:#1B5E20}}.cw .dn{{background:#FDECEA;color:#B71C1C}}
</style>
<div class="cw">
<div class="card" style="border:2px solid {fg}">
<div class="sub">综合观察名单（{date} 收盘）· 量化红绿灯 + J Law + Luk + K线形态</div>
<div style="font-size:22px;font-weight:800;color:{fg}">{light} · {"今天不买新股票，只观察" if gate == "现金" else "今天买入用" + size}</div>
<div style="margin-top:2px;font-size:13px">量化红绿灯：<b>{LIGHT[qgate][1]}</b> · J Law 大盘：<b>{html.escape(jstate or "未知")}</b> → 两个取较严的</div>
<div style="margin-top:4px">可以买 <b>{len(A)}</b> 只 · 等买点 <b>{len(B)}</b> 只 · 要小心 <b>{len(C)}</b> 只</div>
{rs_stale(RS)}<div class="sub" style="margin-top:4px">怎么排出来的：① 先看量化红绿灯决定买多少 → ② J Law / 量化动量 / Luk 名单选股，越多系统同时看好排越前 → ③ 只用回测有效的K线形态：看涨的加分，看跌的直接放进「要小心」。</div>
</div>
<div class="card"><h3 style="color:#2E7D32">🟢 买点已经出现{"（今天红灯：先观察，不买）" if gate == "现金" else ""}</h3>
<div class="sub">J Law 就绪名单或量化买点（52 周新高放量 / 收窄突破 / 回踩 20 日线），在 50 日线上，最近 3 天没有看跌K线。</div>
{table(A, actA)}</div>
<div class="card"><h3 style="color:#B26A00">🟡 等买点（2 个以上系统看好）</h3>
<div class="sub">好股票但今天还不是买点。每天看一次，出现买点会自动移到上面。</div>
{table(B, actB)}</div>
<div class="card"><h3 style="color:#C62828">🔴 要小心（名单里的股票出现卖出信号）</h3>
<div class="sub">J Law / 量化名单里的股票：收盘跌破 50 日线，或最近 3 天出现回测有效的看跌K线（三只乌鸦、看跌孕线、三内降）。</div>
{table(C, actC)}</div>
<div class="card sub">
<b>各标签是什么：</b><span class="ch jl">J Law</span>每日选股的 META 回调 / VCP 突破（就绪 = 可以买，观察 = 快了）
<span class="ch q">量化动量 #</span>2,250 只美股按「一年涨幅 ÷ 波动」排名
<span class="ch lk">Luk</span>Luk 选股名单
<span class="ch up">▲</span><span class="ch dn">▼</span>回测有效的K线形态（2,250 只美股、约 96 万次信号测过；锤子线、吞没、早晨之星等回测是噪音，不显示）。<br>
数据：J Law {os.path.basename(csv)[:-4]} · Luk {os.path.basename(lj[-1])[:-5] if lj else "—"} · 量化与K线 {date}。规则计算，不是 AI 生成；回测有幸存者偏差，仅供学习，不构成投资建议。
</div></div>"""
open(os.path.join(DATA, "combined.html"), "w", encoding="utf-8").write(TAB)
print(json.dumps(dict(A=[r["t"] for r in A], B=[r["t"] for r in B], C=[r["t"] for r in C], gate=gate, qgate=qgate, jstate=jstate), ensure_ascii=False))
