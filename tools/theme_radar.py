"""主题雷达：现在哪些主题在走、哪些刚转强、哪些在转弱，以及每个主题里可以复查的股票。每天跟着每日报告自动更新。

主题 = 主题 / 行业 ETF（清单 ETFS，固定）。每个 ETF 用 RS Rating 同一条公式（2×c/c[63] + c/c[126] + c/c[189] + c/c[252]）算分，
对照当天全部行业组（量化股票池 量化/data/stocks，TradingView industry，成员 ≥5 只，成员等权指数用同一条公式），看它赢过多少比例的行业组。
状态（固定规则，没有 AI 判断）：
  进行中   现在赢过 ≥90% 的行业组，而且之前 12 个月底里 ≥6 个月也是
  刚转强   现在赢过 ≥90%，之前 12 个月底里 <6 个月是
  接近中   现在 75%–90%，比 3 个月前上升 ≥15 个百分位，而且 ETF 收盘在 200 天线上
  转弱中   现在 <75%，但之前 12 个月底里 ≥6 个月在前 10%
可复查的股票（★）= ETF 前十大持股（Yahoo topHoldings）或行业组成员里，RS Rating ≥ 90 且 Stage 2（条件同 jlaw_daily_screen.stage_check，不含成交额门槛），
并排除 每日选股/deals.json 里被收购的股票。★ 这个条件没有单独回测过。
回测依据和局限：回测/主题/（研究报告发布在 docs/theme_research.html）。

用法：python tools/theme_radar.py <仓库目录>     写 主题雷达/<日期>.html，最后一行输出 JSON（html、sub、checks）
"""
import datetime as dt
import html
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import tv_scan, yahoo_chart, yahoo_summary  # noqa: E402
from rs_rating import tv_link  # noqa: E402

RESEARCH = "https://yeohkj-dev.github.io/jlaw-daily-report/theme_research.html"
TOP, MIN_N = 0.9, 5
ETFS = {"SMH": "半导体", "SOXX": "半导体（iShares）", "XSD": "半导体（等权，偏中小型）", "IGV": "软件", "SKYY": "云端", "WCLD": "云端 SaaS", "HACK": "网络安全", "CIBR": "网络安全（First Trust）",
        "BOTZ": "机器人 / AI", "ROBO": "机器人 / 自动化", "AIQ": "AI / 大数据", "ARTY": "AI（iShares）", "IGM": "科技（广义）", "QTUM": "量子计算", "ITA": "航天国防", "XAR": "航天国防（等权）", "SHLD": "国防科技",
        "UFO": "太空", "ARKX": "太空探索（ARK）", "URA": "铀矿 / 核能", "URNM": "铀矿", "NLR": "核能", "NUKZ": "核能复兴", "GRID": "电网 / 电气化", "PAVE": "美国基建", "IFRA": "基建（iShares）",
        "XLU": "公用事业", "TAN": "太阳能", "ICLN": "清洁能源", "QCLN": "清洁能源（纳指）", "LIT": "锂 / 电池", "DRIV": "电动车 / 自动驾驶", "HYDR": "氢能", "COPX": "铜矿", "GDX": "金矿", "GDXJ": "小型金矿",
        "SIL": "银矿", "REMX": "稀土 / 战略金属", "SLX": "钢铁", "XME": "金属矿业", "XOP": "油气开采", "XLE": "能源", "OIH": "油田服务", "FCG": "天然气", "BLOK": "区块链", "WGMI": "比特币矿企",
        "BITQ": "加密货币产业", "FINX": "金融科技", "ARKF": "金融科技（ARK）", "XBI": "生物科技（等权）", "IBB": "生物科技", "ARKG": "基因革命（ARK）", "IHI": "医疗器材", "IHF": "医疗服务 / 保险",
        "PPH": "制药", "XLV": "医疗保健", "XHB": "住宅建筑", "ITB": "住宅建筑（iShares）", "KRE": "区域银行", "KBE": "银行", "KIE": "保险", "IAI": "券商 / 交易所", "XLF": "金融", "JETS": "航空",
        "IYT": "运输", "XRT": "零售", "FDN": "互联网", "ESPO": "电竞 / 游戏", "KWEB": "中国互联网", "INDA": "印度", "EWJ": "日本", "ARKK": "创新成长（ARK）", "MSOS": "美国大麻", "MJ": "大麻",
        "PHO": "水资源", "MOO": "农业", "SRVR": "数据中心 / 通讯 REIT", "DTCR": "数据中心 / 数字基建", "XLRE": "房地产", "XLK": "科技", "XLI": "工业", "XLY": "非必需消费", "XLP": "必需消费",
        "XLB": "原材料", "XLC": "通讯服务"}
ORDER = ["进行中", "刚转强", "接近中", "转弱中", "没有信号"]
COLOR = {"进行中": "#1B5E20", "刚转强": "#1565C0", "接近中": "#F57C00", "转弱中": "#C62828", "没有信号": "#777"}
TITLE = {"进行中": "① 进行中的主题", "刚转强": "② 刚转强（最近才进前 10%）", "接近中": "③ 接近中（往上爬，还没进前 10%）", "转弱中": "④ 转弱中（之前的主题在退潮）"}
# 回测数字（回测/主题/data/results.json，2006–2026；重跑回测后要人工同步）
BT = dict(top12=0.047, top24=0.032, persist12=0.19, per_year=20, big=0.12, base_big=0.11)
TD = 'style="padding:6px 8px;border-bottom:1px solid #eee;vertical-align:top;"'
TH = 'style="padding:6px 8px;background:#f5f5f5;text-align:left;font-weight:600;border-bottom:1px solid #ddd;vertical-align:bottom;"'
IND_CN = {"Packaged Software": "套装软件", "Real Estate Investment Trusts": "房地产信托 REIT", "Pharmaceuticals: Major": "大型制药", "Biotechnology": "生物科技", "Medical Specialties": "医疗器材",
          "Regional Banks": "区域银行", "Miscellaneous Commercial Services": "商业服务（杂项）", "Industrial Machinery": "工业机械", "Semiconductors": "半导体", "Major Banks": "大型银行",
          "Information Technology Services": "IT 服务", "Electric Utilities": "电力公用事业", "Finance/Rental/Leasing": "金融 / 租赁", "Aerospace & Defense": "航天国防", "Specialty Stores": "专卖店",
          "Investment Managers": "资产管理", "Precious Metals": "贵金属", "Internet Software/Services": "互联网软件 / 服务", "Investment Banks/Brokers": "投行 / 券商", "Electrical Products": "电气设备",
          "Medical/Nursing Services": "医疗 / 护理服务", "Integrated Oil": "综合石油", "Engineering & Construction": "工程建筑", "Restaurants": "餐饮", "Multi-Line Insurance": "综合保险",
          "Property/Casualty Insurance": "财产保险", "Marine Shipping": "海运", "Other Metals/Minerals": "其他金属 / 矿产", "Chemicals: Specialty": "特种化学", "Data Processing Services": "数据处理服务",
          "Apparel/Footwear": "服装鞋类", "Food: Specialty/Candy": "特色食品", "Wholesale Distributors": "批发分销", "Electronic Equipment/Instruments": "电子设备 / 仪器", "Auto Parts: OEM": "汽车零件",
          "Other Consumer Services": "其他消费服务", "Oil & Gas Pipelines": "油气管道", "Oilfield Services/Equipment": "油田服务", "Trucks/Construction/Farm Machinery": "卡车 / 工程 / 农业机械",
          "Hotels/Resorts/Cruise lines": "酒店 / 邮轮", "Electronic Production Equipment": "电子生产设备", "Oil & Gas Production": "油气开采", "Gas Distributors": "燃气", "Movies/Entertainment": "影视娱乐",
          "Homebuilding": "住宅建筑", "Apparel/Footwear Retail": "服装零售", "Telecommunications Equipment": "通讯设备", "Financial Conglomerates": "金融集团", "Containers/Packaging": "包装",
          "Real Estate Development": "房地产开发", "Building Products": "建材产品", "Electronic Components": "电子元件", "Household/Personal Care": "家庭 / 个人护理", "Air Freight/Couriers": "空运快递",
          "Life/Health Insurance": "人寿 / 健康保险", "Agricultural Commodities/Milling": "农产品", "Motor Vehicles": "汽车", "Internet Retail": "网络零售", "Airlines": "航空", "Casinos/Gaming": "博彩",
          "Industrial Specialties": "工业特种材料", "Recreational Products": "休闲用品", "Trucking": "卡车运输", "Computer Peripherals": "电脑周边", "Contract Drilling": "钻井承包",
          "Wireless Telecommunications": "无线通讯", "Beverages: Non-Alcoholic": "非酒精饮料", "Insurance Brokers/Services": "保险经纪", "Construction Materials": "建筑材料", "Oil Refining/Marketing": "炼油",
          "Major Telecommunications": "大型电信", "Investment Trusts/Mutual Funds": "投资信托", "Computer Processing Hardware": "电脑硬件", "Hospital/Nursing Management": "医院管理",
          "Managed Health Care": "管理式医保", "Environmental Services": "环保服务", "Steel": "钢铁", "Financial Publishing/Services": "金融信息服务", "Specialty Insurance": "专业保险", "Savings Banks": "储蓄银行",
          "Chemicals: Major Diversified": "综合化工", "Miscellaneous Manufacturing": "制造（杂项）", "Railroads": "铁路", "Food Retail": "食品零售", "Personnel Services": "人力服务",
          "Chemicals: Agricultural": "农业化工", "Other Transportation": "其他运输", "Home Furnishings": "家居用品", "Metal Fabrication": "金属加工", "Coal": "煤炭", "Electronics Distributors": "电子分销",
          "Alternative Power Generation": "替代能源发电", "Food Distributors": "食品分销", "Publishing: Newspapers": "报纸出版", "Food: Major Diversified": "综合食品", "Electronics/Appliances": "电子 / 家电",
          "Water Utilities": "水务"}
esc = html.escape


def pct(x, d=0):
    if x is None or x != x:
        return "—"
    return f'<span style="color:{"#2E7D32" if x >= 0 else "#C62828"};">{x*100:+.{d}f}%</span>'


def table(head, rows):
    h = "".join(f"<th {TH}>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td {TD}>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12.5px;"><tr>{h}</tr>{b}</table></div>'


def status(p, m12, d3, above200):
    if p >= TOP:
        return "进行中" if m12 >= 6 else "刚转强"
    if p >= 0.75 and d3 >= 0.15 and above200:
        return "接近中"
    if p < 0.75 and m12 >= 6:
        return "转弱中"
    return "没有信号"


def et_date(t):
    return dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=-5))).strftime("%Y-%m-%d")


def fetch_etf(sym):
    try:
        bars, _ = yahoo_chart(sym, rng="5y")
        return sym, {et_date(b["t"]): b["c"] for b in bars}
    except Exception:
        return sym, None


def score(P):
    return 2 * P / P.shift(63) + P / P.shift(126) + P / P.shift(189) + P / P.shift(252)


def build(repo):
    import numpy as np
    import pandas as pd
    qd = os.path.join(repo, "量化", "data")
    uni = {r["name"]: r for r in json.load(open(os.path.join(qd, "universe.json"), encoding="utf-8"))}
    raw = {}
    for f in os.listdir(os.path.join(qd, "stocks")):
        s = f[:-5]
        if f.endswith(".json") and s in uni and uni[s].get("industry") and uni[s]["industry"] != "ETF":
            raw[s] = json.load(open(os.path.join(qd, "stocks", f)))
    # 排名日 = 最近一个 ≥90% 股票有收盘的交易日（同 rs_rating.py）
    from collections import Counter
    cnt = Counter(x for d in raw.values() for x in d["d"][-5:])
    last = max(x for x, n in cnt.items() if n >= 0.9 * len(raw))
    cal = sorted({x for s in ("AAPL", "MSFT", "JPM", "XOM") if s in raw for x in raw[s]["d"] if x <= last})
    syms = sorted(raw)
    C = pd.DataFrame({s: pd.Series(raw[s]["c"], index=raw[s]["d"]) for s in syms}).reindex(cal)
    C[C <= 0] = np.nan
    S = score(C)
    valid = S.notna()
    R = C.pct_change(fill_method=None).clip(-0.9, 3.0)
    ind = {}
    for s in syms:
        ind.setdefault(uni[s]["industry"], []).append(s)
    ind = {g: m for g, m in ind.items() if len(m) >= MIN_N}
    GI = pd.DataFrame({g: (1 + R[m].where(valid[m].shift(1, fill_value=False)).mean(axis=1).fillna(0)).cumprod() for g, m in ind.items()})
    GS = score(GI)
    GN = pd.DataFrame({g: valid[m].sum(axis=1) for g, m in ind.items()})
    GS = GS.where(GN >= MIN_N)
    idx = pd.Index(cal)
    ym = pd.Series(cal, index=cal).str[:7]
    ends = list(ym.groupby(ym).apply(lambda x: x.index[-1]))          # 每月最后一个交易日
    if ends[-1] == last:
        ends = ends[:-1]
    evals = ends[-12:] + [last]                                       # 之前 12 个月底 + 排名日

    # 个股：RS Rating、Stage 2
    sc = S.loc[last].dropna()
    base = np.sort(sc.values)
    snap = {}
    for s in sc.index:
        d = raw[s]
        k = len(d["d"]) - d["d"][::-1].index(last) if last in d["d"][-5:] else None
        if not k or k < 253:
            continue
        c, h, l = np.array(d["c"][:k], float), np.array(d["h"][:k], float), np.array(d["l"][:k], float)
        s50, s200 = c[-50:].mean(), c[-200:].mean()
        hi, lo = np.nanmax(h[-252:]), np.nanmin(l[-252:])
        s2 = bool(c[-1] > s50 > s200 and s200 / c[-221:-21].mean() - 1 >= 0.01 and s50 / c[-60:-10].mean() - 1 > 0 and c[-1] >= 0.75 * hi and c[-1] >= 1.25 * lo)
        rs = int(max(1, min(99, np.searchsorted(base, sc[s], side="right") / len(base) * 100)))
        snap[s] = dict(score=float(sc[s]), rs=rs, s2=s2, from_hi=c[-1] / hi - 1, r12=c[-1] / c[-253] - 1, ex=uni[s].get("exchange") or "", ind=uni[s]["industry"],
                       name=uni[s].get("description") or "", star=rs >= 90 and s2)
    try:
        deals = json.load(open(os.path.join(repo, "每日选股", "deals.json"), encoding="utf-8"))["deals"]
    except (OSError, ValueError, KeyError):
        deals = {}
    for s in deals:
        if s in snap:
            snap[s]["star"], snap[s]["deal"] = False, True

    # 行业组（排名日）
    gs = GS.loc[last].dropna()
    groups = []
    for g in gs.index:
        mem = [s for s in ind[g] if s in snap]
        n90 = sum(snap[s]["rs"] >= 90 for s in mem)
        groups.append(dict(group=g, n=len(mem), p=float((gs <= gs[g]).mean()), rs90=n90 / max(1, len(mem)), n90=n90, r12=float(GI[g].loc[last] / GI[g].iloc[idx.get_loc(last) - 252] - 1)))
    gdf = pd.DataFrame(groups)
    gdf["p90"] = gdf["rs90"].rank(pct=True)

    # ETF
    with ThreadPoolExecutor(6) as ex:
        etf_raw = dict(ex.map(fetch_etf, ETFS))
    rows, lastc = [], {}
    spy = etf_raw.get("SPY") or fetch_etf("SPY")[1] or {}
    spy_s = pd.Series(spy).reindex(cal).ffill()
    spy12, spy3 = float(spy_s.iloc[-1] / spy_s.iloc[-253] - 1), float(spy_s.iloc[-1] / spy_s.iloc[-64] - 1)
    for e, name in ETFS.items():
        d = etf_raw.get(e)
        if not d:
            continue
        c = pd.Series(d).reindex(cal).ffill(limit=3)
        if c.iloc[-253:].isna().any() or pd.isna(c.iloc[-1]):
            continue                                                   # 不满 1 年K线
        nd = max(d)
        lastc[e] = (nd, float(d[nd]))                                 # ETF 自己最新一根（核对用，可能比排名日新）
        es = score(c)
        ps = [float((GS.loc[x].dropna() <= es[x]).mean()) if pd.notna(es[x]) else np.nan for x in evals]
        p, prev = ps[-1], ps[:-1]
        m12 = int(sum(x >= TOP for x in prev if x == x))
        p3 = prev[-3] if len(prev) >= 3 and prev[-3] == prev[-3] else None
        streak = 0
        for x in ps[::-1]:
            if x == x and x >= TOP:
                streak += 1
            else:
                break
        ma200, hi52 = float(c.iloc[-200:].mean()), float(c.iloc[-252:].max())
        rows.append(dict(etf=e, name=name, p=p, p3=p3, m12=m12, streak=streak, st=status(p, m12, (p - p3) if p3 is not None else 0, c.iloc[-1] > ma200),
                         r3=float(c.iloc[-1] / c.iloc[-64] - 1), r12=float(c.iloc[-1] / c.iloc[-253] - 1), from_hi=float(c.iloc[-1] / hi52 - 1), above200=bool(c.iloc[-1] > ma200), to200=float(c.iloc[-1] / ma200 - 1)))
    df = pd.DataFrame(rows)
    df["o"] = df["st"].map(ORDER.index)
    df = df.sort_values(["o", "p"], ascending=[True, False])
    return dict(last=last, df=df, gdf=gdf, snap=snap, spy12=spy12, spy3=spy3, n_groups=len(gs), lastc=lastc, n_stocks=len(snap), n_etf_fail=sum(1 for e in ETFS if not etf_raw.get(e)))


def get_holdings(etfs):
    out = {}
    for e in etfs:
        try:
            h = yahoo_summary(e, ["topHoldings"])["topHoldings"]["holdings"]
            out[e] = [(x["symbol"], x.get("holdingName") or "", x["holdingPercent"]["raw"]) for x in h]
        except Exception:
            out[e] = None
    return out


def cand_table(rows):
    """rows = [(代码, 名称, 权重或 None, 快照或 None)]"""
    out = []
    for sym, nm, w, v in rows:
        if v is None:
            out.append([esc(sym), esc(nm[:28]), "—" if w is None else f"{w*100:.1f}%", '<span style="color:#999;">不在股票池，没有 RS</span>', "", "", "", ""])
            continue
        out.append([tv_link(sym, ex=v["ex"]), esc((nm or v["name"])[:28]), "—" if w is None else f"{w*100:.1f}%",
                    f'<b style="color:{"#1B5E20" if v["rs"] >= 90 else "#2E7D32" if v["rs"] >= 80 else "#666" if v["rs"] >= 50 else "#C62828"};">{v["rs"]}</b>',
                    '<span style="color:#2E7D32;">✔</span>' if v["s2"] else '<span style="color:#999;">✘</span>', pct(v["from_hi"]), pct(v["r12"]),
                    '<b style="color:#1B5E20;">★ 符合</b>' if v["star"] else '<span style="color:#C62828;">被收购，排除</span>' if v.get("deal") else ""])
    return table(["股票", "公司", "占 ETF", "RS", "Stage 2", "距 52 周高", "12 个月", "RS ≥ 90 且 Stage 2"], out)


def render(b, hold):
    df, gdf, snap, last = b["df"], b["gdf"], b["snap"], b["last"]
    cnt = df["st"].value_counts()
    stars = {e: [x[0] for x in (hold.get(e) or []) if snap.get(x[0], {}).get("star")] for e in hold}
    P = []
    add = P.append
    names = lambda st: "、".join(f'{r["name"]}（{r["etf"]}）' for _, r in df[df["st"] == st].iterrows()) or "没有"
    star_line = "；".join(f'{r["name"]}：' + ("　".join(tv_link(x, ex=snap[x]["ex"]) for x in stars.get(r["etf"], [])) or "没有")
                         for _, r in df[df["st"].isin(["进行中", "刚转强", "接近中"])].iterrows()) or "没有"
    add(f'''<div style="background:#FFF8E1;border-left:5px solid #F9A825;border-radius:6px;padding:12px 16px;margin:12px 0;line-height:1.85;">
<div style="font-size:16px;font-weight:700;margin-bottom:4px;">一眼看懂（{last} 收盘，{len(df)} 个主题 ETF）</div>
<div><b style="color:{COLOR["进行中"]};">进行中（{cnt.get("进行中",0)}）</b>：{names("进行中")}</div>
<div><b style="color:{COLOR["刚转强"]};">刚转强（{cnt.get("刚转强",0)}）</b>：{names("刚转强")}</div>
<div><b style="color:{COLOR["接近中"]};">接近中（{cnt.get("接近中",0)}）</b>：{names("接近中")}</div>
<div><b style="color:{COLOR["转弱中"]};">转弱中（{cnt.get("转弱中",0)}）</b>：{names("转弱中")}</div>
<div style="margin-top:6px;"><b>可复查的股票（★ = ETF 前十大持股里 RS ≥ 90 且 Stage 2）：</b>{star_line}</div>
<div style="margin-top:6px;font-size:12.5px;color:#555;">这是指标现在的状态，<b>不是预测，也不是买卖建议</b>。同期 SPY：近 3 个月 {pct(b["spy3"])}、近 12 个月 {pct(b["spy12"])}。</div></div>''')

    def etf_table(st):
        out = []
        for _, r in df[df["st"] == st].iterrows():
            out.append([f'<b>{r["name"]}</b>', tv_link(r["etf"]), f'<b>{r["p"]*100:.0f}%</b>', "—" if r["p3"] is None or r["p3"] != r["p3"] else f'{r["p3"]*100:.0f}%', f'{r["m12"]} / 12', f'{r["streak"]} 个月' if r["streak"] else "—",
                        pct(r["r3"]), f'{pct(r["r12"])}<br><span style="color:#888;font-size:11px;">每 $1 万比 SPY {"多" if r["r12"] >= b["spy12"] else "少"} ${abs(r["r12"]-b["spy12"])*10000:,.0f}</span>',
                        pct(r["from_hi"]), ("上方 " if r["above200"] else '<span style="color:#C62828;">下方</span> ') + pct(r["to200"])])
        return table(["主题", "ETF", "现在赢过多少行业组", "3 个月前", "之前 12 个月有几个月在前 10%", "已连续在前 10%", "近 3 个月", "近 12 个月", "距 52 周高", "对 200 天线"], out)

    for st in ORDER[:4]:
        add(f'<h3 style="margin:22px 0 8px;color:{COLOR[st]};">{TITLE[st]}</h3>')
        x = df[df["st"] == st]
        if not len(x):
            add('<p style="color:#777;margin:6px 0;">现在没有。</p>')
            continue
        add(etf_table(st))
        for _, r in x.iterrows():
            h = hold.get(r["etf"])
            if not h:
                add(f'<p style="color:#777;font-size:13px;margin:6px 0;">{r["name"]}（{r["etf"]}）：这次取不到持股。</p>')
                continue
            n = len(stars[r["etf"]])
            add(f'<details class="fold" style="margin:6px 0;" {"open" if st in ("进行中", "刚转强") and n else ""}><summary style="cursor:pointer;font-weight:600;">{r["name"]}（{r["etf"]}）前十大持股：{n} 只 ★'
                + (f'（{"、".join(stars[r["etf"]])}）' if n else "") + "</summary>" + cand_table([(a, nm, w, snap.get(a)) for a, nm, w in h]) + "</details>")

    add('<h3 style="margin:22px 0 8px;color:#1F4E78;">⑤ 行业组：RS ≥ 90 的成员最多的组</h3>')
    add('<p style="font-size:12.5px;color:#555;line-height:1.7;margin:4px 0;">第二个角度：不看 ETF，看股票池里每个行业组有多少成员的 RS Rating ≥ 90（回测里唯一「第一次进前 10%」后 6–12 个月有小优势的指标）。和上面 ETF 两边都出现的主题比较可信。</p>')
    x = gdf[gdf["p90"] >= TOP].sort_values("rs90", ascending=False)
    gname = lambda g: (f'{IND_CN[g]}<br><span style="color:#999;font-size:11px;">{esc(g)}</span>' if g in IND_CN else esc(g))
    add(table(["行业组", "成员数", "RS ≥ 90 成员", "组 RS 排名（赢过多少组）", "组近 12 个月（SPY " + pct(b["spy12"]) + "）"],
              [[gname(r["group"]), int(r["n"]), f'{r["rs90"]*100:.0f}%（{int(r["n90"])} 只）', f'{r["p"]*100:.0f}%', pct(r["r12"])] for _, r in x.iterrows()]))
    for _, r in x.iterrows():
        mem = sorted(((s, v) for s, v in snap.items() if v["ind"] == r["group"] and v["star"]), key=lambda t: -t[1]["score"])
        if mem:
            add(f'<details class="fold" style="margin:6px 0;"><summary style="cursor:pointer;font-weight:600;">{IND_CN.get(r["group"], r["group"])}：{len(mem)} 只 ★' + ("，列出前 8 只" if len(mem) > 8 else "")
                + f'（{"、".join(s for s, _ in mem[:8])}）</summary>' + cand_table([(s, v["name"], None, v) for s, v in mem[:8]]) + "</details>")

    add('<h3 style="margin:22px 0 8px;color:#555;">⑥ 规则、回测依据、局限</h3>')
    add(f'''<details class="fold"><summary style="cursor:pointer;font-weight:600;">怎么判断状态、回测说了什么（展开）</summary>
{table(["状态", "规则"], [
    [f'<b style="color:{COLOR["进行中"]};">进行中</b>', "ETF 的 RS 分数现在赢过 ≥90% 的行业组，而且之前 12 个月底里至少 6 个月也是"],
    [f'<b style="color:{COLOR["刚转强"]};">刚转强</b>', "现在赢过 ≥90% 的行业组，但之前 12 个月底里不到 6 个月是（也可能只是短暂反弹）"],
    [f'<b style="color:{COLOR["接近中"]};">接近中</b>', "现在赢过 75%–90%，比 3 个月前上升 ≥15 个百分位，而且 ETF 在 200 天线上"],
    [f'<b style="color:{COLOR["转弱中"]};">转弱中</b>', "之前 12 个月底里至少 6 个月在前 10%，现在掉到 75% 以下"],
    ["★ 符合", "RS Rating ≥ 90 且 Stage 2（收盘 > 50 天线 > 200 天线、200 天线向上、离 52 周高 ≤25%、离 52 周低 ≥25%）；被收购、股价钉住的股票排除"]])}
<ul style="line-height:1.8;font-size:13px;padding-left:20px;margin:8px 0;">
<li>RS 分数 = 2×(收盘 ÷ 63 天前) + 收盘 ÷ 126 天前 + ÷ 189 天前 + ÷ 252 天前，和网站 RS Rating 同一条公式。行业组 = 股票池（{b["n_stocks"]:,} 只）按 TradingView 行业分，成员 ≥5 只，今天 {b["n_groups"]} 组，成员等权。</li>
<li><b>回测（2006–2026）</b>：组 RS 排名在前 10% 的行业组，之后 12 个月平均比「全部股票平均」多 {BT["top12"]*100:.1f}%（每 $1 万约多 ${BT["top12"]*10000:,.0f}），24 个月后 {BT["top24"]*100:+.1f}% 且统计上不可靠；
前 10% 的组 12 个月后还留在前 10% 的只有 {BT["persist12"]*100:.0f}%。<b>强势平均只维持 6–12 个月，不是 2–3 年。</b></li>
<li>行业组「第一次进前 10%」的信号每年约 {BT["per_year"]} 次，之后 24 个月赢 SPY 50 个百分点以上的只有 {BT["big"]*100:.0f}%（随便挑也有 {BT["base_big"]*100:.0f}%）。<b>「刚转强」「接近中」没有回测证明会变成大主题。</b></li>
<li>回测里的 % 是比同期「全部股票各买一样多」，不是比 SPY；数据只有今天还在交易的股票（幸存者偏差），真实结果会更差。</li>
<li>「★ 符合」这两个条件<b>没有单独回测过</b>，只是方便你点开图复查的名单。只列 ETF 前十大持股；外国股票、ADR、上市不满 1 年的没有 RS。</li>
<li>主题由 ETF 定义：没有 ETF 的新主题、或 ETF 上市不满 1 年的看不到。同一主题有多个 ETF 会重复出现，ETF 之间持股有重叠。</li>
</ul><p style="font-size:13px;margin:6px 0;">完整研究报告（20 年回测、过去 7 个大主题、价格以外的数据）：<a href="{RESEARCH}" target="_blank" rel="noopener" style="color:#1565C0;">打开 ↗</a></p></details>''')
    add(f'<details class="fold" style="margin-top:8px;"><summary style="cursor:pointer;font-weight:600;">没有信号的 {cnt.get("没有信号", 0)} 个主题（展开）</summary>' + etf_table("没有信号") + "</details>")
    return ('<div style="max-width:1080px;margin:0 auto;padding:0 16px 16px;"><div style="background:#fff;border:1px solid #e3e3e3;border-radius:8px;padding:4px 18px 14px;font-size:14px;line-height:1.6;">'
            + "".join(P) + "</div></div>")


def summary_fragment(b, hold):
    """放进「大盘报告」的小结（jlaw_daily_report.theme_part 插在「大资金」后面、行业前面）：四种状态各有哪些主题 + 去主题雷达分页的链接。"""
    df, snap = b["df"], b["snap"]
    line = lambda st: "、".join(f'{r["name"]} {tv_link(r["etf"], bold=False)}' for _, r in df[df["st"] == st].iterrows()) or '<span style="color:#777;">没有</span>'
    stars = []
    for _, r in df[df["st"].isin(["进行中", "刚转强", "接近中"])].iterrows():
        for x in (hold.get(r["etf"]) or []):
            if snap.get(x[0], {}).get("star") and x[0] not in stars:
                stars.append(x[0])
    n_none = int((df["st"] == "没有信号").sum())
    return (f'<h3 style="margin:22px 0 6px;">主题动向</h3>'
            f'<p style="margin:0 0 6px;font-size:12px;color:#666;line-height:1.6;">{b["last"]} 收盘 · {len(df)} 个主题 ETF 对照 {b["n_groups"]} 个行业组的强弱（RS 分数）。固定规则，是现在的状态，不是预测。</p>'
            f'<div style="line-height:1.9;font-size:14px;">'
            f'<div><b style="color:{COLOR["进行中"]};">进行中</b>（强了半年以上）：{line("进行中")}</div>'
            f'<div><b style="color:{COLOR["刚转强"]};">刚转强</b>（最近才进前 10%）：{line("刚转强")}</div>'
            f'<div><b style="color:{COLOR["接近中"]};">接近中</b>（往上爬，还没进前 10%）：{line("接近中")}</div>'
            f'<div><b style="color:{COLOR["转弱中"]};">转弱中</b>（之前的主题在退潮）：{line("转弱中")}</div>'
            f'<div style="font-size:13px;color:#555;">其余 {n_none} 个主题没有信号。'
            + (f'这些主题的前十大持股里，RS ≥ 90 且 Stage 2 的有 {len(stars)} 只：' + "　".join(tv_link(x, ex=snap[x]["ex"], bold=False) for x in stars[:12]) + ("…" if len(stars) > 12 else "") + "。" if stars else "")
            + ' <a href="#" onclick="if(window.show){show(&#39;t-theme&#39;);}return false;" style="color:#1565C0;">看完整的主题雷达 →</a></div></div>')


def checks_for(b, hold):
    out = [dict(name="主题 ETF 数据", ok=len(b["df"]) >= 0.8 * len(ETFS), critical=False, detail=f'{len(ETFS)} 个 ETF 取到 {len(b["df"])} 个可排名（{b["n_etf_fail"]} 个下载失败，其余不满 1 年K线），排名日 {b["last"]}，{b["n_groups"]} 个行业组')]
    try:
        data = tv_scan({"symbols": {"tickers": [f"{x}:{e}" for e in b["lastc"] for x in ("AMEX", "NASDAQ", "NYSE", "CBOE")]}, "columns": ["name", "close"]})
        tv = {x["d"][0]: x["d"][1] for x in data if x["d"][1]}
        newest = max(d for d, _ in b["lastc"].values())
        cmpd = [(e, b["lastc"][e][1], tv[e]) for e in b["lastc"] if e in tv and b["lastc"][e][0] == newest]
        bad = [e for e, a, c in cmpd if abs(a / c - 1) > 0.03]
        out.append(dict(name="主题 ETF 收盘 vs TradingView", ok=len(cmpd) >= 50 and len(bad) <= 0.1 * len(cmpd), critical=False,
                        detail=f'{len(cmpd)} 个 ETF 的 Yahoo 最新收盘（{newest}）对 TradingView 现价，{len(cmpd) - len(bad)} 个相差 ≤3%' + (f'；相差较大：{"、".join(bad[:6])}' if bad else "")))
    except Exception as e:
        out.append(dict(name="主题 ETF 收盘 vs TradingView", ok=False, critical=False, detail=f"TradingView 取不到：{e}"))
    try:
        site = json.load(open(os.path.join(b["repo"], "量化", "data", "rs_rating.json"), encoding="utf-8"))
        d = [abs(v["rs"] - site["stocks"][k]["rating"]) for k, v in b["snap"].items() if k in site["stocks"]]
        far = sum(x > 3 for x in d)
        out.append(dict(name="主题雷达的 RS vs 网站 RS Rating", ok=site["date"] != b["last"] or far <= 0.02 * len(d), critical=False,
                        detail=f'{len(d)} 只股票，相差 >3 分的 {far} 只（网站 RS 日期 {site["date"]}，主题雷达 {b["last"]}）'))
    except Exception as e:
        out.append(dict(name="主题雷达的 RS vs 网站 RS Rating", ok=False, critical=False, detail=f"读不到网站 RS：{e}"))
    got = sum(1 for v in hold.values() if v)
    out.append(dict(name="ETF 持股（Yahoo）", ok=got == len(hold), critical=False, detail=f"{len(hold)} 个有状态的 ETF 取到 {got} 个的前十大持股"))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    repo = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(HERE)
    b = build(repo)
    b["repo"] = repo
    df = b["df"]
    hold = get_holdings(list(df[df["st"] != "没有信号"]["etf"]))
    body = render(b, hold)
    assert "\x08" not in body
    out_dir = os.path.join(repo, "主题雷达")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{b['last']}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>主题雷达 {b["last"]}</title></head>'
                f'<body style="margin:0;background:#eef1f5;font-family:\'Segoe UI\',\'Microsoft YaHei\',Arial,sans-serif;color:#1f2933;">{body}</body></html>')
    cnt = df["st"].value_counts()
    print(json.dumps(dict(html=path, date=b["last"], sub=f'进行中 {cnt.get("进行中", 0)} · 刚转强 {cnt.get("刚转强", 0)}',
                          status={st: list(df[df["st"] == st]["etf"]) for st in ORDER[:4]}, fragment=summary_fragment(b, hold), checks=checks_for(b, hold)), ensure_ascii=False))


if __name__ == "__main__":
    main()
