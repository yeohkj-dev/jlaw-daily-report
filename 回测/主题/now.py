"""主题现况：现在哪些主题在走、哪些在转强、哪些在转弱。写 主题现况.html。

主题 = 主题 / 行业 ETF（不用事后挑股；ETF 清单在 download_extra.py）。每个 ETF 用 RS Rating 同一条公式算分，
对照当月全部行业组（build_indicators.py 的 panel），看它赢过多少比例的行业组（= 组 RS 排名）。
状态规则（固定规则，没有 AI 判断）：
  进行中   现在在前 10%，而且最近 12 个月里 ≥6 个月在前 10%
  刚转强   现在在前 10%，最近 12 个月里 <6 个月在前 10%
  接近中   现在在 75%–90%，比 3 个月前上升 ≥15 个百分位，而且收盘在 200 天线上
  转弱中   现在 <75%，但最近 12 个月里 ≥6 个月在前 10%
  没有信号 其余
先跑 download_extra.py、build_indicators.py、analyze.py。用法：python 回测/主题/now.py
"""
import html
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, HERE)
from rs_rating import tv_link  # noqa: E402
from report import CN, TD, TH, pct, plain, table, g  # noqa: E402

D = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "主题现况.html")
TOP = 0.9
NAME = {"SMH": "半导体", "SOXX": "半导体（iShares）", "XSD": "半导体（等权，偏中小型）", "IGV": "软件", "SKYY": "云端", "WCLD": "云端 SaaS", "HACK": "网络安全", "CIBR": "网络安全（First Trust）",
        "BOTZ": "机器人 / AI", "ROBO": "机器人 / 自动化", "AIQ": "AI / 大数据", "ARTY": "AI（iShares）", "IGM": "科技（广义）", "QTUM": "量子计算", "ITA": "航天国防", "XAR": "航天国防（等权）", "SHLD": "国防科技",
        "UFO": "太空", "ARKX": "太空探索（ARK）", "URA": "铀矿 / 核能", "URNM": "铀矿", "NLR": "核能", "NUKZ": "核能复兴", "GRID": "电网 / 电气化", "PAVE": "美国基建", "IFRA": "基建（iShares）",
        "XLU": "公用事业", "TAN": "太阳能", "ICLN": "清洁能源", "QCLN": "清洁能源（纳指）", "LIT": "锂 / 电池", "DRIV": "电动车 / 自动驾驶", "HYDR": "氢能", "COPX": "铜矿", "GDX": "金矿", "GDXJ": "小型金矿",
        "SIL": "银矿", "REMX": "稀土 / 战略金属", "SLX": "钢铁", "XME": "金属矿业", "XOP": "油气开采", "XLE": "能源", "OIH": "油田服务", "FCG": "天然气", "BLOK": "区块链", "WGMI": "比特币矿企",
        "BITQ": "加密货币产业", "FINX": "金融科技", "ARKF": "金融科技（ARK）", "XBI": "生物科技（等权）", "IBB": "生物科技", "ARKG": "基因革命（ARK）", "IHI": "医疗器材", "IHF": "医疗服务 / 保险",
        "PPH": "制药", "XLV": "医疗保健", "XHB": "住宅建筑", "ITB": "住宅建筑（iShares）", "KRE": "区域银行", "KBE": "银行", "KIE": "保险", "IAI": "券商 / 交易所", "XLF": "金融", "JETS": "航空",
        "IYT": "运输", "XRT": "零售", "FDN": "互联网", "ESPO": "电竞 / 游戏", "KWEB": "中国互联网", "INDA": "印度", "EWJ": "日本", "ARKK": "创新成长（ARK）", "MSOS": "美国大麻", "MJ": "大麻",
        "PHO": "水资源", "MOO": "农业", "SRVR": "数据中心 / 通讯 REIT", "DTCR": "数据中心 / 数字基建", "XLRE": "房地产", "XLK": "科技", "XLI": "工业", "XLY": "非必需消费", "XLP": "必需消费",
        "XLB": "原材料", "XLC": "通讯服务"}
LASTD = {}
ORDER = ["进行中", "刚转强", "接近中", "转弱中", "没有信号"]
COLOR = {"进行中": "#1B5E20", "刚转强": "#1565C0", "接近中": "#F57C00", "转弱中": "#C62828", "没有信号": "#777"}


def stock_snapshot(last):
    """排名日当天每只股票：RS Rating（同 tools/rs_rating.py）、是否 Stage 2（同 jlaw_daily_screen.stage_check，不含成交额门槛）、距 52 周高、12 个月涨跌。"""
    import numpy as np
    bt = os.environ.get("BT_DIR") or os.path.join(os.path.dirname(REPO), "回测")
    uni = {r["name"]: r for r in json.load(open(os.path.join(bt, "universe.json"), encoding="utf-8"))}
    out = {}
    for f in os.listdir(os.path.join(bt, "cache20")):
        sym = f[:-5]
        if sym not in uni or not uni[sym].get("industry") or uni[sym]["industry"] == "ETF":
            continue
        d = json.load(open(os.path.join(bt, "cache20", f)))
        if last not in d["d"][-3:]:
            continue
        k = len(d["d"]) - d["d"][::-1].index(last)
        c, h, l = np.array(d["c"][:k], float), np.array(d["h"][:k], float), np.array(d["l"][:k], float)
        if len(c) < 253 or min(c[-1], c[-64], c[-127], c[-190], c[-253]) <= 0:
            continue
        s50, s200 = c[-50:].mean(), c[-200:].mean()
        hi, lo = h[-252:].max(), l[-252:].min()
        s2 = bool(c[-1] > s50 > s200 and s200 / c[-221:-21].mean() - 1 >= 0.01 and s50 / c[-60:-10].mean() - 1 > 0 and c[-1] >= 0.75 * hi and c[-1] >= 1.25 * lo)
        out[sym] = dict(score=2 * c[-1] / c[-64] + c[-1] / c[-127] + c[-1] / c[-190] + c[-1] / c[-253], s2=s2, from_hi=c[-1] / hi - 1, r12=c[-1] / c[-253] - 1,
                        ex=uni[sym].get("exchange") or "", ind=uni[sym]["industry"], name=uni[sym].get("description") or "")
    base = np.sort([v["score"] for v in out.values()])
    for v in out.values():
        v["rs"] = int(max(1, min(99, np.searchsorted(base, v["score"], side="right") / len(base) * 100)))
        v["star"] = bool(v["rs"] >= 90 and v["s2"])
    return out


def holdings(etfs):
    """ETF 前十大持股（Yahoo topHoldings，要 crumb）。同一天只抓一次，存 data/holdings.json。"""
    import datetime as dt
    import time
    from common import yahoo_summary
    path = os.path.join(D, "holdings.json")
    today = dt.date.today().isoformat()
    try:
        old = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    out = old.get("etf", {}) if old.get("date") == today else {}
    for e in etfs:
        if out.get(e):
            continue
        try:
            h = yahoo_summary(e, ["topHoldings"])["topHoldings"]["holdings"]
            out[e] = [[x["symbol"], x.get("holdingName") or "", x["holdingPercent"]["raw"]] for x in h]
        except Exception:
            out[e] = None
        time.sleep(0.25)
    json.dump(dict(date=today, etf=out), open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return out, today


def cand_table(rows):
    """rows = [(代码, 名称, 权重或 None, 快照或 None)]"""
    out = []
    for sym, nm, w, v in rows:
        if v is None:
            out.append([html.escape(sym), html.escape(nm[:28]), "—" if w is None else f"{w*100:.1f}%", '<span style="color:#999;">不在股票池（外国股票 / ADR / 上市不满 1 年），没有 RS</span>', "", "", "", ""])
            continue
        out.append([tv_link(sym, ex=v["ex"]), html.escape((nm or v["name"])[:28]), "—" if w is None else f"{w*100:.1f}%",
                    f'<b style="color:{"#1B5E20" if v["rs"] >= 90 else "#2E7D32" if v["rs"] >= 80 else "#666" if v["rs"] >= 50 else "#C62828"};">{v["rs"]}</b>',
                    '<span style="color:#2E7D32;">✔</span>' if v["s2"] else '<span style="color:#999;">✘</span>', pct(v["from_hi"], 0), pct(v["r12"], 0),
                    '<b style="color:#1B5E20;">★ 符合</b>' if v["star"] else '<span style="color:#C62828;">被收购（股价钉住），排除</span>' if v.get("deal") else ""])
    return table(["股票", "公司", "占 ETF", "RS Rating", "Stage 2", "距 52 周高点", "12 个月涨跌", "RS ≥ 90 且 Stage 2"], out, small=True)


def status(p, m12, d3, above200):
    if p >= TOP:
        return "进行中" if m12 >= 6 else "刚转强"
    if p >= 0.75 and d3 >= 0.15 and above200:
        return "接近中"
    if p < 0.75 and m12 >= 6:
        return "转弱中"
    return "没有信号"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ef = pd.read_pickle(os.path.join(D, "etf.pkl"))
    panel = pd.read_pickle(os.path.join(D, "panel.pkl"))
    lv = pd.read_pickle(os.path.join(D, "levels.pkl"))
    R = json.load(open(os.path.join(D, "results.json"), encoding="utf-8"))
    last = panel["date"].max()
    spy = lv["SPY"].dropna()
    spy12, spy3 = spy.iloc[-1] / spy.iloc[-253] - 1, spy.iloc[-1] / spy.iloc[-64] - 1
    rows = []
    for e, x in ef.groupby("group"):
        x = x.set_index("date").sort_index()
        c = lv[e].dropna()
        if last not in x.index or len(c) < 253 or pd.isna(x.loc[last, "p_score"]):
            continue
        h = x["p_score"]
        p = float(h.loc[last])
        prev12 = h.iloc[-13:-1]                       # 之前 12 个月底（不含现在）
        m12 = int((prev12 >= TOP).sum())
        p3 = float(h.iloc[-4]) if len(h) >= 4 and pd.notna(h.iloc[-4]) else None
        streak = 0
        for v in h.iloc[::-1]:
            if v >= TOP:
                streak += 1
            else:
                break
        ma200 = c.iloc[-200:].mean()
        hi52 = c.iloc[-252:].max()
        st = status(p, m12, (p - p3) if p3 is not None else 0, c.iloc[-1] > ma200)
        raw = json.load(open(os.path.join(HERE, "cache_extra", e + ".json")))        # 缓存里比排名日更新的收盘（ETF 是后来下载的）
        newer = raw["c"][-1] / float(c.iloc[-1]) - 1 if raw["d"][-1] > str(last.date()) else None
        LASTD[e] = (raw["d"][-1], raw["c"][-1])
        rows.append(dict(etf=e, name=NAME.get(e, e), newer=newer, p=p, p3=p3, m12=m12, streak=streak, st=st, r12=c.iloc[-1] / c.iloc[-253] - 1, r3=c.iloc[-1] / c.iloc[-64] - 1,
                         from_hi=c.iloc[-1] / hi52 - 1, above200=bool(c.iloc[-1] > ma200), to200=c.iloc[-1] / ma200 - 1))
    df = pd.DataFrame(rows)
    newest = max(d for d, _ in LASTD.values())
    # 核对：ETF 最新收盘 vs TradingView 选股器
    try:
        from common import tv_scan
        data = tv_scan({"symbols": {"tickers": [f"{x}:{e}" for e in LASTD for x in ("AMEX", "NASDAQ", "NYSE", "CBOE")]}, "columns": ["name", "close"]})
        tv = {x["d"][0]: x["d"][1] for x in data if x["d"][1]}
        cmpd = [(e, LASTD[e][1], tv[e]) for e in LASTD if e in tv and LASTD[e][0] == newest]
        bad = [e for e, a, b in cmpd if abs(a / b - 1) > 0.02]
        check = (f'数据核对：{len(cmpd)} 个 ETF 的 Yahoo 最新收盘（{newest}）对 TradingView 选股器现价，{len(cmpd) - len(bad)} 个相差 ≤2%'
                 + (f'；相差较大：{"、".join(bad[:8])}（TradingView 可能已是下一个交易日）' if bad else "") + "。")
    except Exception as ex:
        check = f"数据核对：TradingView 取不到（{ex}），这次没有核对。"
    print(check)
    df["o"] = df["st"].map(ORDER.index)
    df = df.sort_values(["o", "p"], ascending=[True, False])
    json.dump(dict(asof=str(last.date()), spy12=float(spy12), spy3=float(spy3), rows=df.drop(columns="o").to_dict("records")), open(os.path.join(D, "now.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def tab(st):
        x = df[df["st"] == st]
        if not len(x):
            return '<p style="color:#777;margin:6px 0;">现在没有。</p>'
        out = []
        for _, r in x.iterrows():
            out.append([f'<b>{r["name"]}</b>', tv_link(r["etf"]), f'<b>{plain(r["p"])}</b>', "—" if r["p3"] is None else plain(r["p3"]), f'{r["m12"]} / 12', f'{r["streak"]} 个月' if r["streak"] else "—",
                        f'{pct(r["r3"],0)}<br><span style="color:#888;font-size:11px;">SPY {pct(spy3,0)}</span>', f'{pct(r["r12"],0)}<br><span style="color:#888;font-size:11px;">SPY {pct(spy12,0)}；每 $1 万比 SPY {"多" if r["r12"]>=spy12 else "少"} ${abs(r["r12"]-spy12)*10000:,.0f}</span>',
                        pct(r["from_hi"], 0), ("在上方 " if r["above200"] else '<span style="color:#C62828;">在下方</span> ') + pct(r["to200"], 0),
                        "—" if r["newer"] is None or pd.isna(r["newer"]) else pct(r["newer"], 1)])
        return table(["主题", "代表 ETF", "现在赢过多少行业组", "3 个月前", "之前 12 个月有几个月在前 10%", "已连续在前 10%", "ETF 近 3 个月涨跌", "ETF 近 12 个月涨跌", "距 52 周高点", "对 200 天线", f"排名日之后到 {newest} 的涨跌（没算进排名）"], out, small=True)

    cnt = df["st"].value_counts()
    snap = stock_snapshot(str(last.date()))
    # 被收购、股价钉在收购价的股票（网站每日选股的 deals.json）不算符合
    try:
        deals = json.load(open(os.path.join(REPO, "每日选股", "deals.json"), encoding="utf-8"))["deals"]
    except (OSError, ValueError, KeyError):
        deals = {}
    for s_ in deals:
        if s_ in snap:
            snap[s_]["star"], snap[s_]["deal"] = False, True
    # 核对：这里算的 RS Rating vs 网站的 量化/data/rs_rating.json（日期可能差几天）
    try:
        site = json.load(open(os.path.join(REPO, "量化", "data", "rs_rating.json"), encoding="utf-8"))
        import statistics
        diffs = [abs(v["rs"] - site["stocks"][k]["rating"]) for k, v in snap.items() if k in site["stocks"]]
        rs_check = (f'RS Rating 核对：这里用 20 年日线算的（{last.date()}）对网站的 RS 档（{site["date"]}），{len(diffs)} 只股票差距中位数 {statistics.median(diffs):.0f} 分，'
                    f'{sum(d <= 10 for d in diffs) / len(diffs) * 100:.0f}% 的股票差 ≤10 分（两边日期不同，不会完全一样）。')
    except Exception as ex:
        rs_check = f"RS Rating 核对：读不到网站的 RS 档（{ex}），这次没有核对。"
    print(rs_check)
    shown = list(df[df["st"] != "没有信号"]["etf"])
    hold, hold_date = holdings(shown)
    stars = {e: [x[0] for x in (hold.get(e) or []) if snap.get(x[0], {}).get("star")] for e in shown}

    def cands(st):
        out = ""
        for _, r in df[df["st"] == st].iterrows():
            h = hold.get(r["etf"])
            if not h:
                out += f'<p style="color:#777;font-size:13px;">{r["name"]}（{r["etf"]}）：这次取不到持股。</p>'
                continue
            n_star = len(stars[r["etf"]])
            out += (f'<details {"open" if st != "转弱中" else ""}><summary style="cursor:pointer;font-weight:600;margin:10px 0 4px;">{r["name"]}（{r["etf"]}）前十大持股：{n_star} 只符合「RS ≥ 90 且 Stage 2」'
                    + (f'（{"、".join(stars[r["etf"]])}）' if n_star else "") + "</summary>"
                    + cand_table([(x[0], x[1], x[2], snap.get(x[0])) for x in h]) + "</details>")
        return out
    P = []
    add = P.append
    sec = lambda t, c: add(f'<h2 style="margin:30px 0 8px;padding:8px 12px;background:{c};color:#fff;font-size:17px;border-radius:4px;">{t}</h2>')
    names = lambda st: "、".join(f'{r["name"]}（{r["etf"]}）' for _, r in df[df["st"] == st].iterrows()) or "没有"
    top = R["in_top"]["p_score"]
    star_line = "；".join(f'{r["name"]}：' + ("　".join(tv_link(x, ex=snap[x]["ex"]) for x in stars[r["etf"]]) or "没有") for _, r in df[df["st"].isin(["进行中", "刚转强", "接近中"])].iterrows()) or "没有"
    add(f'''<div style="background:#FFF8E1;border-left:5px solid #F9A825;padding:14px 18px;margin:14px 0;line-height:1.85;">
<div style="font-size:17px;font-weight:700;margin-bottom:6px;">一眼看懂（{last.date()} 收盘，共 {len(df)} 个主题 ETF）</div>
<div><b style="color:{COLOR["进行中"]};">进行中（{cnt.get("进行中",0)} 个）</b>：{names("进行中")}</div>
<div><b style="color:{COLOR["刚转强"]};">刚转强（{cnt.get("刚转强",0)} 个）</b>：{names("刚转强")}</div>
<div><b style="color:{COLOR["接近中"]};">接近中（{cnt.get("接近中",0)} 个）</b>：{names("接近中")}</div>
<div><b style="color:{COLOR["转弱中"]};">转弱中（{cnt.get("转弱中",0)} 个）</b>：{names("转弱中")}</div>
<div style="margin-top:8px;"><b>可复查的股票（★ = ETF 前十大持股里 RS ≥ 90 且 Stage 2）：</b>{star_line}</div>
<div style="margin-top:8px;font-size:13px;color:#555;">这是指标现在的状态，<b>不是预测，也不是买卖建议</b>。回测（主题雷达研究.html）的结论：组 RS 排名在前 10% 的行业组，之后 12 个月平均比全部股票平均 {pct(top["12"]["ex_uni"])}（每 $1 万约多 ${top["12"]["ex_uni"]*10000:,.0f}），
24 个月后 {pct(top["24"]["ex_uni"])} 且统计上不可靠；前 10% 的组 12 个月后还留在前 10% 的只有 {plain(R["persist"]["p_score"]["12"]["top10"])}。「刚转强」「接近中」这两类<b>没有回测证明会变成大主题</b>——过去每年约 20 个类似信号，约 8 个里只有 1 个之后成为大主题。</div>
</div>''')
    add(table(["状态", "规则"], [
        [f'<b style="color:{COLOR["进行中"]};">进行中</b>', "ETF 的 RS 分数现在赢过 ≥90% 的行业组，而且之前 12 个月里至少 6 个月也是 → 已经走了一段时间的主题"],
        [f'<b style="color:{COLOR["刚转强"]};">刚转强</b>', "现在赢过 ≥90% 的行业组，但之前 12 个月里不到 6 个月是 → 最近才冒出来（也可能只是短暂反弹）"],
        [f'<b style="color:{COLOR["接近中"]};">接近中</b>', "现在赢过 75%–90% 的行业组，比 3 个月前上升 ≥15 个百分位，而且 ETF 在 200 天线上 → 正在往上爬，还没到前 10%"],
        [f'<b style="color:{COLOR["转弱中"]};">转弱中</b>', "之前 12 个月里至少 6 个月在前 10%，现在掉到 75% 以下 → 之前的主题在退潮"],
    ], small=True))
    add(f'<p style="font-size:13px;color:#555;line-height:1.7;">RS 分数 = 2×(收盘 ÷ 63 天前) + 收盘 ÷ 126 天前 + ÷ 189 天前 + ÷ 252 天前（和网站 RS Rating 同一条公式）。「赢过多少行业组」= 这个分数在当月约 {int(panel[panel["date"]==last]["group"].count())} 个行业组（成员等权）里的位置。'
        f'ETF 涨跌是价格本身的涨跌（不含股息），旁边是同期 SPY。</p>')
    add(f'''<div style="background:#FDECEA;border-left:5px solid #C62828;padding:10px 16px;margin:10px 0;line-height:1.8;font-size:13.5px;"><b>注意日期：</b>排名用的是 {last.date()} 收盘（个股日线缓存的最后一天，行业组门槛只能算到这天），不是今天。
ETF 自己的日线到 {newest}，每张表最后一栏列出排名日之后的涨跌——如果这几天变动很大（例如急跌后反弹），状态可能已经不同，要重新下载个股日线再跑一次才准。{check} {rs_check}</div>''')
    for st in ORDER[:4]:
        sec({"进行中": "① 进行中的主题", "刚转强": "② 刚转强（最近才进前 10%）", "接近中": "③ 接近中（往上爬，还没进前 10%）", "转弱中": "④ 转弱中（之前的主题在退潮）"}[st], COLOR[st])
        add(tab(st))
        if len(df[df["st"] == st]):
            add(f'<div style="margin-top:8px;font-size:13px;color:#555;">下面是每个 ETF 的前十大持股（Yahoo，{hold_date} 抓取）和它们在 {last.date()} 的 RS Rating / Stage 2。<b>★ 只表示符合两个固定条件，是「可以点开图复查」的名单，不是买进建议。</b></div>')
            add(cands(st))
    sec("⑤ 行业组（个股层面的核对）：现在哪些组 RS≥90 的成员最多", "#1F4E78")
    cur = panel[panel["date"] == last]
    x = cur[cur["p_rs90"] >= TOP].sort_values("rs90", ascending=False)
    add('<p style="font-size:13px;color:#555;line-height:1.7;">第二个角度：不看 ETF，看股票池里每个行业组有多少成员的个股 RS Rating ≥ 90。回测里这是唯一「第一次进前 10%」后 6–12 个月有小优势的指标。和上面 ETF 的结果互相对照：两边都出现的主题比较可信。</p>')
    add(table(["行业组", "成员数", "RS≥90 成员", "组 RS 排名（赢过多少组）", "近 21 天创 52 周新高的成员", "组过去 12 个月涨跌（SPY " + pct(spy12, 0) + "）"],
              [[g(r["group"]), int(r["n"]), f'{plain(r["rs90"])}（{int(r["n_rs90"])} 只）', plain(r["p_score"]), plain(r["nh"]), pct(r["r12"], 0)] for _, r in x.iterrows()], small=True))
    add('<div style="margin-top:12px;font-size:13px;font-weight:600;">上面这些行业组里，符合「RS ≥ 90 且 Stage 2」的成员（每组最多 8 只，按 RS 分数由高到低）</div>')
    for _, r in x.iterrows():
        mem = sorted(((s_, v) for s_, v in snap.items() if v["ind"] == r["group"] and v["star"]), key=lambda t: -t[1]["score"])
        if not mem:
            add(f'<p style="color:#777;font-size:13px;margin:6px 0;">{CN.get(r["group"], r["group"])}：没有成员同时符合两个条件。</p>')
            continue
        add(f'<details open><summary style="cursor:pointer;font-weight:600;margin:10px 0 4px;">{CN.get(r["group"], r["group"])}（{html.escape(r["group"])}）：{len(mem)} 只符合' + ("，列出前 8 只" if len(mem) > 8 else "") + "</summary>"
            + cand_table([(s_, v["name"], None, v) for s_, v in mem[:8]]) + "</details>")
    x = cur[cur["p_score"] >= TOP].sort_values("p_score", ascending=False)
    add('<div style="margin-top:10px;font-size:13px;font-weight:600;">组 RS 排名前 10% 的行业组</div>')
    add(table(["行业组", "成员数", "组 RS 排名", "RS≥90 成员", "组过去 12 个月涨跌"], [[g(r["group"]), int(r["n"]), plain(r["p_score"]), f'{plain(r["rs90"])}（{int(r["n_rs90"])} 只）', pct(r["r12"], 0)] for _, r in x.iterrows()], small=True))
    sec("⑥ 没有信号的主题（全部列出，方便以后对照）", "#777")
    add('<details><summary style="cursor:pointer;font-weight:600;margin:6px 0;">展开 ' + str(cnt.get("没有信号", 0)) + " 个</summary>" + tab("没有信号") + "</details>")
    add('''<h2 style="margin:30px 0 8px;padding:8px 12px;background:#1F4E78;color:#fff;font-size:17px;border-radius:4px;">局限</h2>
<ul style="line-height:1.85;font-size:14px;padding-left:20px;"><li>主题由 ETF 定义：没有 ETF 的新主题（或 ETF 太新、不满 1 年K线）看不到。清单是固定的 ''' + str(len(NAME)) + ''' 个，可以再加。</li>
<li>同一个主题有多个 ETF 时（例如半导体 3 个）会重复出现；ETF 持股不同，状态可能不一样。</li>
<li>ETF 之间有重叠（AI、半导体、科技、量子的大持股很多是同一批公司），「进行中」的数量多不代表有那么多个独立的主题。</li>
<li>「★ 符合」只用两个条件（RS Rating ≥ 90、Stage 2）。网站回测里 RS ≥ 90 是 A0 名单的门槛，但单看这两个条件<b>没有另外回测过</b>；只列 ETF 前十大持股，较小的成分股不在表里（行业组那一节会补到一部分）。不在股票池的持股（外国股票、ADR、上市不满 1 年）没有 RS。网站「每日选股」判定为被收购、股价钉住的股票（deals.json）不算符合。</li>
<li>这是「现在强不强」，不是「2–3 年后会不会强」。回测没有找到能提前 2–3 年的数据。</li>
<li>个股日线是 Yahoo 缓存，和研究报告同一份（已对过 TradingView，见研究报告第 9 节）；ETF 最新收盘的核对结果在页面上方红框。</li></ul>''')
    page = f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>主题现况 {last.date()}</title>
<style>body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;max-width:1180px;margin:0 auto;padding:18px;color:#222;font-size:14.5px;background:#fff;}} table tr:hover td{{background:#FAFAFA;}}</style></head><body>
<h1 style="font-size:23px;margin:6px 0 4px;">主题现况：现在哪些主题在走、哪些在转强</h1>
<div style="color:#777;font-size:13px;">固定规则，不含 AI 生成内容 · 数据到 {last.date()} 收盘 · 对照 SPY · 不是投资建议</div>
{"".join(P)}</body></html>'''
    assert "\x08" not in page
    open(OUT, "w", encoding="utf-8").write(page)
    print("写好", OUT)
    pd.set_option("display.width", 220)
    print(df[df["st"] != "没有信号"][["st", "etf", "name", "p", "p3", "m12", "streak", "r3", "r12", "from_hi", "above200"]].round(2).to_string())
    print("SPY 3m/12m", round(spy3, 3), round(spy12, 3))
    print(cur.sort_values("rs90", ascending=False).head(10)[["group", "n", "rs90", "n_rs90", "p_score", "r12"]].round(2).to_string())


if __name__ == "__main__":
    main()
