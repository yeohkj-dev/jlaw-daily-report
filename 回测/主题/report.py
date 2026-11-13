"""主题雷达研究 ⑤：把 data/results.json、sources.json、crosscheck.json 写成 主题雷达研究.html（简体中文、白话结论在前）。
全部文字是固定模板 + 回测数字，没有 AI 生成内容。
用法：python 回测/主题/report.py
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
from rs_rating import tv_link  # noqa: E402

D = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "主题雷达研究.html")
HZ = ("6", "12", "24")
EXTRA_EX = {"CGC": "NASDAQ", "ACB": "NASDAQ", "CRON": "NASDAQ", "NIO": "NYSE", "NVO": "NYSE", "TSM": "NYSE", "ASML": "NASDAQ"}
CN = {"Packaged Software": "套装软件", "Real Estate Investment Trusts": "房地产信托 REIT", "Pharmaceuticals: Major": "大型制药", "Biotechnology": "生物科技",
      "Medical Specialties": "医疗器材", "Regional Banks": "区域银行", "Miscellaneous Commercial Services": "商业服务（杂项）", "Industrial Machinery": "工业机械",
      "Semiconductors": "半导体", "Major Banks": "大型银行", "Information Technology Services": "IT 服务", "Electric Utilities": "电力公用事业",
      "Finance/Rental/Leasing": "金融 / 租赁", "Aerospace & Defense": "航天国防", "Specialty Stores": "专卖店", "Investment Managers": "资产管理",
      "Precious Metals": "贵金属", "Internet Software/Services": "互联网软件 / 服务", "Investment Banks/Brokers": "投行 / 券商", "Electrical Products": "电气设备",
      "Medical/Nursing Services": "医疗 / 护理服务", "Integrated Oil": "综合石油", "Engineering & Construction": "工程建筑", "Restaurants": "餐饮",
      "Multi-Line Insurance": "综合保险", "Property/Casualty Insurance": "财产保险", "Marine Shipping": "海运", "Other Metals/Minerals": "其他金属 / 矿产",
      "Chemicals: Specialty": "特种化学", "Data Processing Services": "数据处理服务", "Apparel/Footwear": "服装鞋类", "Food: Specialty/Candy": "特色食品",
      "Wholesale Distributors": "批发分销", "Electronic Equipment/Instruments": "电子设备 / 仪器", "Auto Parts: OEM": "汽车零件", "Other Consumer Services": "其他消费服务",
      "Oil & Gas Pipelines": "油气管道", "Oilfield Services/Equipment": "油田服务", "Trucks/Construction/Farm Machinery": "卡车 / 工程 / 农业机械",
      "Hotels/Resorts/Cruise lines": "酒店 / 邮轮", "Electronic Production Equipment": "电子生产设备", "Oil & Gas Production": "油气开采", "Gas Distributors": "燃气",
      "Movies/Entertainment": "影视娱乐", "Homebuilding": "住宅建筑", "Apparel/Footwear Retail": "服装零售", "Telecommunications Equipment": "通讯设备",
      "Financial Conglomerates": "金融集团", "Containers/Packaging": "包装", "Real Estate Development": "房地产开发", "Building Products": "建材产品",
      "Electronic Components": "电子元件", "Household/Personal Care": "家庭 / 个人护理", "Air Freight/Couriers": "空运快递", "Life/Health Insurance": "人寿 / 健康保险",
      "Agricultural Commodities/Milling": "农产品", "Motor Vehicles": "汽车", "Internet Retail": "网络零售", "Airlines": "航空", "Casinos/Gaming": "博彩",
      "Industrial Specialties": "工业特种材料", "Recreational Products": "休闲用品", "Trucking": "卡车运输", "Computer Peripherals": "电脑周边",
      "Contract Drilling": "钻井承包", "Wireless Telecommunications": "无线通讯", "Beverages: Non-Alcoholic": "非酒精饮料", "Insurance Brokers/Services": "保险经纪",
      "Construction Materials": "建筑材料", "Oil Refining/Marketing": "炼油", "Major Telecommunications": "大型电信", "Investment Trusts/Mutual Funds": "投资信托",
      "Computer Processing Hardware": "电脑硬件", "Hospital/Nursing Management": "医院管理", "Managed Health Care": "管理式医保", "Environmental Services": "环保服务",
      "Steel": "钢铁", "Financial Publishing/Services": "金融信息服务", "Specialty Insurance": "专业保险", "Savings Banks": "储蓄银行",
      "Chemicals: Major Diversified": "综合化工", "Miscellaneous Manufacturing": "制造（杂项）", "Railroads": "铁路", "Food Retail": "食品零售", "Personnel Services": "人力服务",
      "Chemicals: Agricultural": "农业化工", "Other Transportation": "其他运输", "Home Furnishings": "家居用品", "Metal Fabrication": "金属加工", "Coal": "煤炭",
      "Electronics Distributors": "电子分销", "Alternative Power Generation": "替代能源发电", "Food Distributors": "食品分销", "Publishing: Newspapers": "报纸出版",
      "Food: Major Diversified": "综合食品", "Electronics/Appliances": "电子 / 家电", "Water Utilities": "水务"}

TD = 'style="padding:6px 8px;border-bottom:1px solid #eee;vertical-align:top;"'
TH = 'style="padding:6px 8px;background:#f5f5f5;text-align:left;font-weight:600;border-bottom:1px solid #ddd;vertical-align:bottom;"'
esc = html.escape


def g(name):
    return f'{CN[name]}<br><span style="color:#999;font-size:11px;">{esc(name)}</span>' if name in CN else esc(name)


def pct(x, d=1):
    if x is None:
        return "—"
    return f'<span style="color:{"#2E7D32" if x >= 0 else "#C62828"};">{x*100:+.{d}f}%</span>'


def plain(x, d=0):
    return "—" if x is None else f"{x*100:.{d}f}%"


def money(ex):
    """每投入 $1 万，和对比对象相差多少美元。"""
    if ex is None:
        return "—"
    return f'{"多" if ex >= 0 else "少"} ${abs(ex)*10000:,.0f}'


def table(head, rows, small=False):
    h = "".join(f"<th {TH}>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td {TD}>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:{12 if small else 13}px;">{h and "<tr>" + h + "</tr>"}{b}</table></div>'


def tk(s, ex):
    return tv_link(s, ex=ex.get(s) or EXTRA_EX.get(s) or "")


def verdict(x):
    """规则：比全部股票平均 ≥ +2%、t ≥ 2、≥60% 的年份为正 = 有；≤ −2% 且 t ≤ −2 = 反而更差；其余 = 没有。"""
    if x is None:
        return "—"
    t = x["t_uni"] or 0
    if x["ex_uni"] >= 0.02 and t >= 2 and x["years_pos"] / x["years"] >= 0.6:
        return '<b style="color:#2E7D32;">有（小）</b>'
    if x["ex_uni"] <= -0.02 and t <= -2:
        return '<b style="color:#C62828;">反而更差</b>'
    return '<span style="color:#777;">没有</span>'


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    R = json.load(open(os.path.join(D, "results.json"), encoding="utf-8"))
    S = json.load(open(os.path.join(D, "sources.json"), encoding="utf-8"))
    X = json.load(open(os.path.join(D, "crosscheck.json"), encoding="utf-8"))
    M = json.load(open(os.path.join(D, "meta.json"), encoding="utf-8"))
    ex = M["exchange"]
    meas, sig, top = R["meas"], R["signals"], R["in_top"]
    W, cl, base = R["winners"], R["classify"], R["base"]
    bias = R["bias"]
    P = []
    add = P.append
    sec = lambda t, i: add(f'<h2 id="{i}" style="margin:34px 0 10px;padding:8px 12px;background:#1F4E78;color:#fff;font-size:17px;border-radius:4px;">{t}</h2>')
    note = lambda t: add(f'<p style="margin:6px 0;font-size:13px;color:#555;line-height:1.7;">{t}</p>')
    para = lambda t: add(f'<p style="margin:8px 0;line-height:1.8;">{t}</p>')

    c24, b24 = cl["p_comp"], cl["base"]
    themes = R["themes"]
    comp_sigs = [(n, t["sig"]["p_comp"]) for n, t in themes.items() if t["sig"]["p_comp"]]
    lo = min(s["months_from_low"] for _, s in comp_sigs); hi = max(s["months_from_low"] for _, s in comp_sigs)
    sl_lo = min(s["share_left"] for _, s in comp_sigs); sl_hi = max(s["share_left"] for _, s in comp_sigs)
    rs90, rk = sig["p_rs90"], top["p_score"]

    # ---------- 结论 ----------
    add(f'''<div style="background:#FFF8E1;border-left:5px solid #F9A825;padding:14px 18px;margin:14px 0;line-height:1.85;">
<div style="font-size:17px;font-weight:700;margin-bottom:6px;">先说结论（白话）</div>
<ol style="margin:0;padding-left:20px;">
<li><b>没有找到能提前 2–3 年看到下一个主题的价格数据。</b>把 20 年里「之后 24 个月涨得最多的 5% 行业组」找出来（共 {W["n"]} 个组·月，之后 24 个月至少比全部股票平均多涨 {plain(W["cut"])}），
它们起涨当时的四项综合分平均只排在第 {W["mean_comp"]*100:.0f} 百分位——就是中间，和随便挑没有分别；当时已在前 10% 的只有 {plain(W["top10"])}（随便挑也有 10%），在后半段的反而有 {plain(W["bottom50"])}。
<b>大主题起涨前，价格上看不出来。</b></li>
<li><b>用现成的行业分类做「第一次进前 10%」的信号，基本没有用。</b>四项综合第一次进前 10% 之后 24 个月：平均{pct(sig["p_comp"]["24"]["ret"])}，同期 SPY {pct(sig["p_comp"]["24"]["spy"])}，看起来赢 SPY {pct(sig["p_comp"]["24"]["ex_spy"])}；
但同期「全部股票平均」是 {pct(sig["p_comp"]["24"]["uni"])}——<b>比全部股票平均反而 {pct(sig["p_comp"]["24"]["ex_uni"])}（每 $1 万约{money(sig["p_comp"]["24"]["ex_uni"])}）</b>。赢 SPY 的部分来自幸存者偏差（见第 1 节），不是信号的功劳。</li>
<li><b>误报很多。</b>综合信号 20 年共 {sig["p_comp"]["n"]} 次（平均每年约 {sig["p_comp"]["per_year"]:.0f} 次）。看得到 24 个月结果的 {c24["n"]} 次里：之后 24 个月赢 SPY 50 个百分点以上（算「真的大主题」）的只有 {c24["big_spy"]} 次（{c24["big_spy"]/c24["n"]*100:.0f}%），
输给 SPY 的有 {c24["lose_spy"]} 次（{c24["lose_spy"]/c24["n"]*100:.0f}%）。而<b>任何一个组、任何一个月随便买</b>，赢 SPY 50 个百分点以上的也有 {b24["big_spy"]/b24["n"]*100:.0f}%。信号没有把大主题挑出来。</li>
<li><b>唯一有一点用的：RS 类指标，而且只管 6–12 个月。</b>「RS ≥ 90 成员比例」第一次进前 10% 之后 6 个月比全部股票平均 {pct(rs90["6"]["ex_uni"])}（每 $1 万约{money(rs90["6"]["ex_uni"])}，{rs90["6"]["years_pos"]}/{rs90["6"]["years"]} 个年份为正）、
12 个月 {pct(rs90["12"]["ex_uni"])}；到 24 个月是 {pct(rs90["24"]["ex_uni"])}，但一半以上的信号是输的（中位数 {pct(rs90["24"]["med_ex_uni"])}），靠少数大赢家拉高，统计上不可靠。
「组 RS 排名在前 10%」的组（不限第一次）之后 12 个月比全部股票平均 {pct(rk["12"]["ex_uni"])}，24 个月剩 {pct(rk["24"]["ex_uni"])}。<b>52 周新高比例、Stage 2 比例进前 10% 之后 24 个月反而输</b>（{pct(top["p_nh"]["24"]["ex_uni"])}、{pct(top["p_s2"]["24"]["ex_uni"])}）——全组都在创新高时，通常已经涨到后段。</li>
<li><b>过去 7 个大主题：如果事先就有对的股票篮子，价格信号来得很早；问题是「事先」不知道篮子。</b>用事后挑的代表股当篮子，综合信号在篮子低点之后 {lo:.1f}–{hi:.1f} 个月出现，当时整段涨幅还剩 {sl_lo*100:.0f}%–{sl_hi*100:.0f}%。
但同一段时间，现成的行业分类大多没有信号或晚很多（半导体整个行业 54 只，AI 只是其中十几只；减肥药只有 2–3 只股票）。所以这部分数字<b>只能说明「主题一旦开始，篮子的强度会很快显示出来」，不能当成可以赚到的回报</b>（事后挑股 = 高估）。</li>
<li><b>价格以外的数据</b>（第 6 节，逐个实际抓取验证）：SEC 的资本开支、上市申请数量、联邦法规 / 法案、政府支出、SPDR 行业 ETF 份额都可以免费用程序取得；分析师预估修正只有「今天的值」，要从现在开始每天存；
Google Trends、FRED 这次取不到。这些数据<b>没有足够长的免费历史，没办法像价格那样回测</b>，所以只能列为「可以追踪」，不能说「已证明领先」。</li>
</ol>
<div style="margin-top:8px;"><b>一句话：</b>数据做不到「提前 2–3 年预测」；做得到的是「主题开始后几个月内确认它是真的」，而且要自己先定好主题篮子。这份报告只是回测结果，不是投资建议，也不建议买卖任何股票。</div>
</div>''')

    # ---------- 1 ----------
    sec("1. 先看懂：这些 % 是跟什么比", "s1")
    para(f'数据：{M["n_stocks"]:,} 只<b>今天还在交易</b>的美股，{M["first"]} 至 {M["last"]} 的日线（Yahoo，价格不含股息；SPY 也不含股息，两边一致）。'
         f'行业 = TradingView 的 industry（{M["n_industries"]} 个，其中成员 ≥{M["min_n"]} 只的才算一组，每个月约 {min(M["groups_by_year"].values())}–{max(M["groups_by_year"].values())} 组）。每个月最后一个交易日算一次。')
    add(table(["写法", "意思"], [
        ["组的涨跌", "信号当天，这个行业组当时的成员每只买一样多的钱，一直拿到 6 / 12 / 24 个月后（126 / 252 / 504 个交易日）的平均涨跌"],
        ["比 SPY", "上面的涨跌 − 同一段时间 SPY 的涨跌。例：组 +30%、SPY +20% → 比 SPY +10%，每 $1 万约多 $1,000"],
        ["<b>比全部股票平均</b>", "上面的涨跌 − 同一段时间「股票池里全部股票各买一样多」的涨跌。<b>判断信号有没有用，看这一栏</b>"],
        ["前 10%", "这个指标在当月全部行业组里排在最高的 10%（约 8–9 个组）"],
        ["第一次进前 10%", "这个月在前 10%，而且之前 12 个月都不在"],
        ["多少年份为正", "把信号按发生的年份分开，各年平均「比全部股票平均」是正数的年份数。年份越多越不像运气"],
        ["t", "统计上有多可靠（同一个月的信号先平均再算）。大约 ≥2 才算不像运气；持有期互相重叠，实际可靠度比 t 显示的还低"],
    ]))
    add(f'''<div style="background:#FDECEA;border-left:5px solid #C62828;padding:12px 16px;margin:12px 0;line-height:1.8;">
<b>幸存者偏差（很重要）：</b>股票池只有今天还活着的公司，过去倒闭、被收购、下市的都不在。结果是：<b>什么都不挑、全部股票各买一样多</b>，过去 20 年平均每 12 个月就涨 {plain(bias["12"]["uni"],1)}，同期 SPY 只有 {plain(bias["12"]["spy"],1)}
（24 个月：{plain(bias["24"]["uni"],1)} vs {plain(bias["24"]["spy"],1)}）。也就是说，这份数据里<b>随便买都「赢」SPY 约 {(bias["12"]["uni"]-bias["12"]["spy"])*100:.0f} 个百分点一年</b>，这是假的优势。
所以下面每张表都同时列「比 SPY」和「比全部股票平均」，后者才是信号本身的效果。真实世界里，热门主题的输家（例如 2008 年倒闭的太阳能公司、2021 年后下市的电动车公司）都不在数据里，实际结果只会比表里差。</div>''')
    add(table(["年份"] + [y for y in M["stocks_by_year"] if int(y) % 2 == 0], [["当时已有 1 年以上K线的股票"] + [f'{v:,}' for y, v in M["stocks_by_year"].items() if int(y) % 2 == 0],
                                                                         ["行业组数"] + [str(v) for y, v in M["groups_by_year"].items() if int(y) % 2 == 0]], small=True))
    note("越早的年份股票越少（当时还没上市的公司不算），偏差也越大。")

    # ---------- 2 ----------
    sec("2. 回测一：行业组「第一次进前 10%」之后 6 / 12 / 24 个月", "s2")
    para("4 个指标 + 3 种组合，各自第一次进前 10% 当作信号。结论栏的规则：比全部股票平均 ≥ +2%、t ≥ 2、而且 ≥60% 的年份为正 = 有；≤ −2% 且 t ≤ −2 = 反而更差；其余 = 没有。")
    DESC = {"p_score": "组内成员等权指数，用 RS Rating 同一条公式算分，在全部行业组里排名", "p_nh": "近 21 个交易日里创过 52 周新高的成员比例", "p_s2": "处于 Stage 2 的成员比例（同网站 Stage 2 名单的条件，不含成交额门槛）",
            "p_rs90": "个股 RS Rating ≥ 90 的成员比例（同 tools/rs_rating.py）", "p_comp": "上面 4 项百分位的平均", "k3": "4 项里至少 3 项同时在前 10%", "p_dcomp": "综合分比 6 个月前上升最多的 10%（想抓「刚开始转强」）"}
    for h in HZ:
        add(f'<h3 style="margin:18px 0 6px;font-size:15px;">之后 {h} 个月</h3>')
        rows = []
        for k, nm in meas.items():
            x = sig[k][h]
            rows.append([f'<b>{nm}</b><br><span style="color:#888;font-size:11px;">{DESC[k]}</span>', x["n"], pct(x["ret"]), pct(x["spy"]), pct(x["uni"]), pct(x["ex_spy"]),
                         f'<b>{pct(x["ex_uni"])}</b>', money(x["ex_uni"]), pct(x["med_ex_uni"]), plain(x["win_uni"]), f'{x["years_pos"]}/{x["years"]}', f'{x["t_uni"]:+.1f}', verdict(x)])
        b = base[h]
        rows.append(['<span style="color:#777;">对照：任何组、任何月</span>', b["n"], pct(b["ret"]), pct(b["spy"]), pct(b["uni"]), pct(b["ex_spy"]), pct(b["ex_uni"]), money(b["ex_uni"]), pct(b["med_ex_uni"]), plain(b["win_uni"]), "—", "—", "—"])
        add(table(["信号（第一次进前 10%）", "次数", "组的涨跌", "同期 SPY", "同期全部股票平均", "比 SPY", "比全部股票平均", "每 $1 万（比全部平均）", "中位数（比全部平均）", "赢全部平均的比例", "正的年份", "t", "有没有领先？"], rows, small=True))
    note("「对照」那一行说明：什么信号都没有，随便一个组也「比 SPY」多几个百分点——这就是幸存者偏差。信号要比这一行好才算数。")
    add('<h3 style="margin:18px 0 6px;font-size:15px;">不限第一次：只要这个月在前 10%，之后的表现（比全部股票平均）</h3>')
    rows = []
    for k, nm in meas.items():
        r = [f"<b>{nm}</b>", top[k]["n"]]
        for h in HZ:
            x = top[k][h]
            r += [f'{pct(x["ex_uni"])}<br><span style="color:#888;font-size:11px;">每 $1 万{money(x["ex_uni"])}；t {x["t_uni"]:+.1f}；{x["years_pos"]}/{x["years"]} 年</span>', verdict(x)]
        r.append(f'{pct(top[k]["12"]["ex_uni_0615"])} / {pct(top[k]["12"]["ex_uni_1626"])}')
        rows.append(r)
    add(table(["这个月在前 10%", "组·月数", "6 个月", "", "12 个月", "", "24 个月", "", "12 个月分两段：2006–2015 / 2016–2026"], rows, small=True))
    q = R["quint"]["p_score"]
    para(f'<b>白话：</b>组 RS 排名和 RS≥90 比例有一点「强者续强」，但只到 6–12 个月，幅度是每 $1 万多几百美元，而且 2006–2015 那一段明显较弱。到 24 个月就没有了。'
         f'52 周新高比例、Stage 2 比例是「已经涨了很久」的指标，进前 10% 后 24 个月反而输全部股票平均。'
         f'另外，组 RS 排名<b>最弱 20%</b> 的组之后 24 个月比全部股票平均 {pct(q["最弱 20%"]["24"]["ex_uni"])}、最强 20% 是 {pct(q["最强 20%"]["24"]["ex_uni"])}——'
         f'最弱的反弹看起来更多，但这一项受幸存者偏差影响最大（跌到倒闭的公司不在数据里），不要当成「买最弱的」的证据。')

    # ---------- 3 ----------
    sec("3. 强的组能强多久？（2–3 年的问题）", "s3")
    pe = R["persist"]
    rows = [[f"{m} 个月后", plain(pe["p_comp"][m]["top10"]), plain(pe["p_comp"][m]["top25"]), plain(pe["p_comp"][m]["bottom50"]), plain(pe["p_score"][m]["top10"]), plain(pe["p_score"][m]["top25"]), plain(pe["p_score"][m]["bottom50"])]
            for m in ("3", "6", "12", "24", "36")]
    rows.append(['<span style="color:#777;">如果完全随机</span>', "10%", "25%", "50%", "10%", "25%", "50%"])
    add(table(["这个月在前 10% 的组", "综合分：还在前 10%", "在前 25%", "掉到后半段", "组 RS：还在前 10%", "在前 25%", "掉到后半段"], rows))
    st = R["stay24"]
    para(f'<b>白话：</b>今天综合分前 10% 的组，12 个月后还在前 10% 的只有 {plain(pe["p_comp"]["12"]["top10"])}（随机是 10%），{plain(pe["p_comp"]["12"]["bottom50"])} 已经掉到后半段；24 个月后和随机一样。'
         f'第一次进前 10% 之后的 24 个月里，还待在前 10% 的月数中位数只有 {st["median"]:.0f} 个月；{plain(st["le3"])} 的信号待不到 4 个月，能待满 12 个月以上的只有 {plain(st["ge12"])}。'
         f'<b>行业层面的强势平均只维持几个月，不是 2–3 年。</b>能持续 2–3 年的主题是少数例外（第 5 节），而且事先分不出来哪一个是例外。')
    add(f'''<div style="background:#E3F2FD;border-left:5px solid #1565C0;padding:12px 16px;margin:12px 0;line-height:1.8;">
<b>倒过来看：</b>之后 24 个月最强的 5%（{W["n"]} 个组·月）起涨当时——综合分平均第 {W["mean_comp"]*100:.0f} 百分位；在前 10% 的 {plain(W["top10"])}、前 25% 的 {plain(W["top25"])}、后半段的 {plain(W["bottom50"])}、最后 10% 的 {plain(W["bottom10"])}；
它们之前 12 个月平均涨 {plain(W["mean_r12"])}，全部组平均是 {plain(W["mean_r12_all"])}（起涨前反而涨得比别人少）。反过来，今天在综合分前 10% 的组，之后成为那最强 5% 的机会是 {plain(W["p_top_given_sig"],1)}（随机 5%）。</div>''')

    # ---------- 4 ----------
    sec("4. 误报有多少", "s4")
    rows = []
    for k in ("p_score", "p_rs90", "p_nh", "p_s2", "p_comp", "k3", "p_dcomp", "base"):
        c = cl[k]
        rows.append([meas.get(k, '<span style="color:#777;">对照：任何组、任何月</span>'), c["n"], f'{c["big_spy"]}（{c["big_spy"]/c["n"]*100:.0f}%）', f'{c["win_spy"]}（{c["win_spy"]/c["n"]*100:.0f}%）', f'{c["lose_spy"]}（{c["lose_spy"]/c["n"]*100:.0f}%）',
                     f'{c["big_uni"]}（{c["big_uni"]/c["n"]*100:.0f}%）', f'{c["lose_uni"]}（{c["lose_uni"]/c["n"]*100:.0f}%）'])
    add(table(["信号（第一次进前 10%）", "有 24 个月结果的次数", "大主题：赢 SPY ≥50 个百分点", "小赢：赢 SPY 0–50", "输给 SPY", "赢全部股票平均 ≥50 个百分点", "输给全部股票平均"], rows))
    para("<b>白话：</b>每 100 次信号，大约 10–16 次之后变成大主题，40–50 次输给 SPY，过半输给全部股票平均。和「对照」那一行几乎一样——信号没有提高命中率。")
    add('<h3 style="margin:18px 0 6px;font-size:15px;">综合信号：之后 24 个月最好和最差的各 12 次</h3>')

    def ex_rows(lst):
        return [[x["date"], g(x["group"]), x["n"], pct(x["r12"], 0), pct(x["f24"], 0), pct(x["spy24"], 0), pct(x["f24"] - x["spy24"], 0), money(x["f24"] - x["spy24"]), pct(x["f24"] - x["uni24"], 0)] for x in lst]
    hd = ["信号日", "行业组", "成员数", "信号前 12 个月组已涨", "之后 24 个月组的涨跌", "同期 SPY", "比 SPY", "每 $1 万（比 SPY）", "比全部股票平均"]
    add('<details open><summary style="cursor:pointer;font-weight:600;margin:6px 0;">最好的 12 次</summary>' + table(hd, ex_rows(R["best"]), small=True) + "</details>")
    add('<details open><summary style="cursor:pointer;font-weight:600;margin:6px 0;">最差的 12 次</summary>' + table(hd, ex_rows(R["worst"]), small=True) + "</details>")
    from collections import Counter
    yb, yw = Counter(x["date"][:4] for x in R["best"]), Counter(x["date"][:4] for x in R["worst"])
    note("最好的 12 次按年份：" + "、".join(f"{y} 年 {n} 次" for y, n in sorted(yb.items())) + "；最差的 12 次：" + "、".join(f"{y} 年 {n} 次" for y, n in sorted(yw.items()))
         + "。2009 年那几次「比 SPY」很高，但「比全部股票平均」少很多——当时什么都在大涨。最差的 12 次里能源类（油气开采、油田服务、钻井）占 5 次。")
    rows = [[y["year"], y["n"], pct(y["ex_spy"], 0) if y["done"] else "还没满 24 个月", pct(y["ex_uni"], 0) if y["done"] else "—",
             "、".join(CN.get(x, x) for x in y["groups"])] for y in R["by_year"]]
    add('<details><summary style="cursor:pointer;font-weight:600;margin:6px 0;">每年的综合信号（展开）</summary>' + table(["年份", "信号次数", "之后 24 个月平均比 SPY", "比全部股票平均", "哪些组"], rows, small=True) + "</details>")

    # ---------- 5 ----------
    sec("5. 过去 7 个大主题：指标有没有提早出现？", "s5")
    add(f'''<div style="background:#FDECEA;border-left:5px solid #C62828;padding:12px 16px;margin:12px 0;line-height:1.8;">
<b>读这一节前要知道：</b>这里的「篮子」是<b>事后</b>知道主题是什么之后挑的代表股（而且只挑今天还查得到的），当时没有人能事先知道该放哪几只。所以这一节的涨幅是<b>看不到未来的人赚不到的</b>，只用来回答一个问题：
「主题真的开始之后，这 4 个指标要多久才亮？」另外，篮子只有几只股票时，一两只暴涨股就会把平均拉得很高。每个篮子当成多出来的一个「组」，和当月全部行业组的门槛比。</div>''')
    ML = {"p_score": "组 RS 排名", "p_nh": "52 周新高比例", "p_s2": "Stage 2 比例", "p_rs90": "RS≥90 比例", "p_comp": "四项综合"}
    summ = []
    for name, t in themes.items():
        s = t["sig"]["p_comp"]
        summ.append([f"<b>{name}</b>", t["low"], t["peak"] + ("（数据最后还在高点附近）" if t["still_high"] else ""), f'{pct(t["run"],0)}<br><span style="color:#888;font-size:11px;">同期 SPY {pct(t["run_spy"],0)}</span>',
                     "没有" if not s else f'{s["date"]}<br><span style="color:#888;font-size:11px;">低点后 {s["months_from_low"]:.1f} 个月，当时 {s["n"]} 只</span>',
                     "—" if not s else pct(s["gain_before"], 0), "—" if not s else f'{pct(s["gain_after"],0)}<br><span style="color:#888;font-size:11px;">{s["months_to_peak"]:.0f} 个月；同期 SPY {pct(s["spy_after"],0)}</span>',
                     "—" if not s else plain(s["share_left"]),
                     "—" if not s else f'{pct(s["f12"],0)} vs SPY {pct(s["spy12"],0)}', "—" if not s else (f'{pct(s["f24"],0)} vs SPY {pct(s["spy24"],0)}' if s["f24"] is not None else "还没满"),
                     f'{t["pre_months_top"]} 个月'])
    add(table(["主题（事后挑的篮子）", "篮子低点", "篮子高点", "低点到高点涨幅", "四项综合第一次进前 10%", "信号前已涨（从低点）", "信号后到高点", "整段涨幅还剩多少（按倍数的对数算）", "信号后 12 个月", "信号后 24 个月", "窗口前 36 个月已在前 10% 的月数"], summ, small=True))
    note("「涨幅」是篮子成员每天等权的指数（每天重新平均），「信号后 12 / 24 个月」是信号当天各买一份拿着不动的平均；两种算法不同，数字不会一样。最后一栏：同一个篮子在这一波之前也亮过多少个月——亮过不代表之后就大涨。")
    for name, t in themes.items():
        add(f'<h3 style="margin:20px 0 6px;font-size:15px;">{name}</h3>')
        para("篮子：" + "　".join(tk(s, ex) for s in t["tickers"]) + f'　｜观察窗口 {t["win"][0]} 至 {t["win"][1]}')
        rows = []
        for k, nm in ML.items():
            s = t["sig"][k]
            rows.append([nm] + (["窗口内没有进过前 10%"] + [""] * 5 if not s else
                                [s["date"], f'{s["months_from_low"]:.1f} 个月', pct(s["gain_before"], 0), f'{pct(s["gain_after"],0)}（{s["months_to_peak"]:.0f} 个月）', plain(s["share_left"]),
                                 f'{pct(s["f12"],0)} vs SPY {pct(s["spy12"],0)}（每 $1 万{money(s["f12"]-s["spy12"])}）' if s["f12"] is not None else "还没满 12 个月"]))
        add(table(["指标", "第一次进前 10%", "离篮子低点", "当时已涨", "之后到高点", "涨幅还剩", "之后 12 个月：篮子 vs SPY"], rows, small=True))
        rows = []
        for i, o in t["industries"].items():
            if not o["months"]:
                rows.append([g(i), "当时成员不足 5 只，没有这个组", "", "", ""])
                continue
            rows.append([g(i), o["n"], o["comp_first"] or '<span style="color:#C62828;">整段都没有进过</span>', f'{o["comp_months"]} / {o["months"]} 个月', o["rs_first"] or '<span style="color:#C62828;">整段都没有进过</span>'])
        add('<div style="margin-top:6px;font-size:13px;font-weight:600;">不事后挑股：TradingView 现成的行业组在同一段时间（篮子低点到高点）</div>')
        add(table(["行业组", "成员数", "四项综合第一次进前 10%", "在前 10% 的月数", "组 RS 排名第一次进前 10%"], rows, small=True))
        if t["etf"]:
            rows = []
            for e, o in t["etf"].items():
                s = o["sig"]
                rows.append([tk(e, ex), f'{o["first"]} 起 {pct(o["run"],0)}', "整段都没有进过前 10%" if not s else s["date"], "—" if not s else pct(s["gain_before"], 0), "—" if not s else pct(s["gain_after"], 0)])
            add('<div style="margin-top:6px;font-size:13px;font-weight:600;">第二来源核对：主题 ETF（ETF 当时持有的股票包括后来下市的，没有幸存者偏差；只能算「组 RS 排名」一项）</div>')
            add(table(["ETF", "同一段时间 ETF 涨跌", "RS 分数第一次赢过 90% 的行业组", "当时 ETF 已涨", "之后到篮子高点 ETF 涨跌"], rows, small=True))
    add('''<div style="background:#F5F5F5;border-left:5px solid #777;padding:12px 16px;margin:14px 0;line-height:1.8;"><b>这一节照数字读到的：</b>
<ul style="margin:4px 0;padding-left:20px;">
<li>7 个主题的篮子，四项综合都在低点后 1 年内进前 10%，当时大部分涨幅还在后面。指标的<b>反应速度</b>够快。</li>
<li>但现成的行业组常常<b>看不到</b>：智能手机那几年「通讯设备」组从没进前 10%；电动车那一波「汽车」组从没进；减肥药靠 2–3 只股票，行业组有 80 多只；AI 那一波「半导体」整组的综合分 2023 年 3 月进过前 10%、但 4 年里只待了 5 个月，组 RS 排名到 2025 年底才进前 10%。<b>主题比行业窄，行业分类会把它稀释掉。</b></li>
<li>ETF 核对有好有坏：半导体（SMH、SOXX）、太阳能（TAN、ICLN）、核能（URA、NLR）的 ETF 和篮子差不多同时亮；云端（IGV、SKYY）、公用事业（XLU）的 ETF 整段都没亮；<b>大麻 ETF（MJ）到 2018 年 9 月才亮，之后到高点是跌的</b>——篮子里 2016 年就亮的那两只当时还是加拿大小型股，说明大麻这一行的「提早信号」主要是事后挑股挑出来的。</li>
<li>减肥药篮子只有 3 只，平均被其中一只（VKTX）拉得很高，不代表整个主题。</li>
<li>篮子在这一波之前也亮过（最后一栏）：AI / 半导体篮子在这一波之前的 36 个月里有 ''' + str(themes['AI / 半导体']['pre_months_top']) + f''' 个月在前 10%，之后从 {themes["AI / 半导体"]["pre_high"]} 的高点跌到 {themes["AI / 半导体"]["low"]} 的低点，跌了 {plain(-themes["AI / 半导体"]["pre_dd"])}。<b>亮了不等于接下来 2 年会涨。</b></li>
</ul></div>''')

    # ---------- 6 ----------
    sec("6. 价格以外、可能更早的数据：哪些真的能免费用程序取得", "s6")
    ok = sum(1 for s in S["sources"] if s["ok"])
    para(f'下面每一项都在 {S["checked"]}（本机时间）用程序实际抓了一次（<code>check_sources.py</code>），「结果」栏是当场取到的内容。{len(S["sources"])} 项里 {ok} 项取到。'
         '<b>这些数据都没有回测</b>——免费来源没有按行业整理好的 20 年历史，无法证明它们领先多久；「可能看到什么」只是数据的性质，不是已验证的结论。')
    INFO = {
        "sec_capex": ("资本开支（已发生的）", "公司每季 / 每年实际花了多少钱买设备、盖厂房。10-Q / 10-K 申报后当天可取，2009 年起", "✔ 免费、不用 key、有历史。要带 User-Agent、每秒 ≤10 次。<b>限制：</b>是「已经花的」，不是「指引」；季度数字是年初至今累计，要自己相减"),
        "sec_frames": ("资本开支（全市场）", "一次取全部公司同一年 / 同一季的资本开支，可按行业加总，看哪个行业的投资在加速", "✔ 免费、不用 key。<b>限制：</b>各公司用的科目名不完全一样（例如亚马逊用另一个科目），要处理；财年不同步"),
        "sec_sic": ("行业代码", "把上面的公司归到 SIC 行业", "✔ 免费。<b>限制：</b>SIC 分类很旧（例如没有「云端」「AI」），每家公司要查一次"),
        "sec_ipo": ("上市申请数量", "每季有多少 S-1 / F-1（申请上市）和 424B4（定价）。某个行业上市突然变多，常是主题过热的迹象", "✔ 免费、1993 年起。<b>限制：</b>S-1 也包括 SPAC 和老股东转售，要再筛；按行业分要逐家查 SIC；IPO 潮通常出现在主题的<b>后段</b>而不是开始"),
        "nasdaq_ipo": ("IPO 日历", "每月已定价 / 即将上市的名单和集资金额", "△ 取得到，但这是 Nasdaq 网页自己用的接口，不是正式 API，随时可能改或挡；没有行业栏位"),
        "yahoo_rev": ("分析师预估修正", "每只股票：EPS 预估现在 vs 30 / 90 天前，近 30 天多少分析师上调 / 下调。按行业算「上调比例」就是修正广度", "△ 取得到（网站已在用 crumb）。<b>限制：只有今天的值、没有历史</b>，要从现在开始每天存，过几年才有东西可以回测；约 2,250 只每天抓一次要注意限流"),
        "tv_est": ("预估 EPS / 营收", "TradingView 选股器的预估值，一次可取全部股票", "△ 取得到当下值，没有「修正」栏位；同样要自己每天存下来比较"),
        "congress": ("国会法案", "法案标题、进度、最新动作。例：芯片法案、通胀削减法案（清洁能源补贴）都是在这里走完流程", "△ 免费，但正式使用要申请免费 key（DEMO_KEY 有次数限制）。<b>限制：</b>每年上万条法案，绝大多数不会通过；要靠关键词，关键词本身就是事先要猜的主题"),
        "fedreg": ("联邦法规 / 行政命令", "各部门的最终规则、提案、总统行政命令，可按机构（例如核管会、能源部）或关键词数数量", "✔ 免费、不用 key、1994 年起。<b>限制：</b>同样要先定关键词 / 机构"),
        "usaspending": ("联邦政府实际支出", "合同和拨款按关键词 / 机构 / 财年加总，看钱实际流向哪里", "✔ 免费、不用 key、2008 财年起。<b>限制：</b>关键词搜索很粗（芯片法案的大额补贴不一定搜得到），金额要人工核对"),
        "ssga": ("行业 ETF 资金流", "SPDR 行业 ETF（XLK、XLU、XLE…）每天的净值和流通份额，份额变化 × 净值 ≈ 净流入", "✔ 免费、官网 Excel、有完整历史（XLU 从 2003 年）。<b>限制：</b>只有道富自己的 ETF；主题 ETF（SMH、TAN、URA 等）是别家的，各家格式不同或不提供历史"),
        "yahoo_etf": ("ETF 总资产", "任何 ETF 当下的总资产", "△ 只有当下值，要每天存；资产变化 − 价格涨跌 ≈ 净流入（估算，不是官方流量）"),
        "census": ("建筑支出", "每月各类建筑（制造业厂房、电力、数据中心）花了多少钱", "✘ 这次没验证到：现在不带 key 会被转到「缺少 key」页面，要先免费申请 key"),
        "arxiv": ("论文数量", "按关键词数每年论文，看技术热度", "✘ 这次被限流（HTTP 429），没验证到。就算取得到，论文热度到股价之间隔很远"),
        "fred": ("FRED 经济数据", "企业投资、利率、利差等", "✘ 连不上（超时）。和网站大盘报告遇到的情况一样（CLAUDE.md 已记录）"),
        "ritter": ("历年 IPO 统计", "Jay Ritter 教授整理的每年 IPO 数量、首日涨幅、科技股比例（1980 年起）", "△ 页面取得到，但数据是 PDF / Excel、人工更新，适合人看，不适合每天自动抓"),
        "gtrends": ("Google 搜索热度", "关键词搜索量", "✘ 没有正式免费 API，这次网页接口返回 404"),
    }
    rows = []
    for s in S["sources"]:
        a, b, c = INFO[s["key"]]
        rows.append([f"<b>{a}</b>", f'{esc(s["name"])}<br><span style="color:#999;font-size:11px;word-break:break-all;">{esc(s["url"])}</span>', b,
                     ('<b style="color:#2E7D32;">取到</b>：' if s["ok"] else '<b style="color:#C62828;">没取到</b>：') + esc(str(s["sample"])), c])
    add(table(["数据", "来源", "可能看到什么", "这次实际抓取的结果", "能不能用、限制"], rows, small=True))

    cap = S["capex"]
    ys = [y for y in S["capex_years"] if int(y) >= 2016]
    big4 = ["MSFT", "GOOGL", "AMZN", "META"]
    rows = []
    for s in big4 + ["ORCL"]:
        rows.append([tk(s, ex)] + [f'${cap[s][y]["val"]/1e9:.0f}B' if y in cap[s] else "—" for y in ys])
    tot = {y: sum(cap[s][y]["val"] for s in big4) for y in S["capex_years"] if all(y in cap[s] for s in big4)}
    rows.append(["<b>前 4 家合计</b>"] + [f'<b>${tot[y]/1e9:.0f}B</b>' if y in tot else "—" for y in ys])
    rows.append(["比上一年"] + [pct(tot[y] / tot[str(int(y) - 1)] - 1, 0) if y in tot and str(int(y) - 1) in tot else "—" for y in ys])
    rows.append(["年报申报日（最晚一家）"] + [max(cap[s][y]["filed"] for s in big4) if y in tot else "—" for y in ys])
    add('<h3 style="margin:18px 0 6px;font-size:15px;">例子：5 家大公司每年的资本开支（SEC 年报原始数字）</h3>')
    add(table(["公司 / 财年结束的年份"] + ys, rows, small=True))
    ai = themes["AI / 半导体"]["sig"]["p_comp"]
    y23, y24 = tot["2023"] / tot["2022"] - 1, tot["2024"] / tot["2023"] - 1
    para(f'这是「年报里已经花掉的钱」，比上一年是直接相除（没有调整财年：微软财年到 6 月、甲骨文到 5 月，其余到 12 月）。照数字看：前 4 家合计 2023 年比上一年 {pct(y23,0)}、2024 年 {pct(y24,0)}，而 2024 年的年报要到 {max(cap[s]["2024"]["filed"] for s in big4)} 才申报完；'
         f'AI / 半导体篮子的价格信号是 {ai["date"]}（第 5 节）。<b>在这一个例子里，年报的资本开支数字比价格信号晚，不是早。</b>季度数字（10-Q）会快一些，公司口头给的「明年资本开支指引」更早，但指引只出现在业绩新闻稿和电话会的文字里，没有结构化栏位，'
         f'要用规则从文字里抓数字（容易抓错）或人工输入。只有一个例子，不能当成规律。')

    # ---------- 7 ----------
    sec(f"7. 现在的读数（{R['asof']} 收盘）", "s7")
    para(f'只是把同一套指标套在最新一天，让你看「雷达」会长什么样。<b>不是建议</b>：第 2–4 节已经说明，行业组进前 10% 之后的表现和随便挑差不多。同期 SPY 过去 12 个月 {pct(R["spy_r12_now"],0)}。')
    rows = [[g(x["group"]), x["n"], plain(x["p_score"]), plain(x["nh"]), plain(x["s2"]), f'{plain(x["rs90"])}（{x["n_rs90"]} 只）', pct(x["r12"], 0), f'{x["streak"]} 个月', f'{x["months12"]} / 12'] for x in R["now"]]
    add(table(["综合分前 10% 的行业组", "成员数", "组 RS 排名（赢过多少组）", "近 21 天创 52 周新高的成员", "Stage 2 成员", "RS≥90 成员", "组过去 12 个月涨跌", "已连续在前 10%", "近 12 个月在前 10% 的月数"], rows, small=True))
    para(f'过去 12 个月，综合分「第一次进前 10%」的信号一共出现 {len(R["now_new"])} 次（约 {max(M["groups_by_year"].values())} 个组里）：' + "、".join(f'{CN.get(x["group"], x["group"])}（{x["date"][:7]}）' for x in R["now_new"]) + "。一年几十个信号，也说明它不能直接当「下一个主题」用。")

    # ---------- 8 ----------
    sec("8. 如果以后要在网站加「主题雷达」，回测支持做什么、不支持做什么", "s8")
    add(table(["做法", "回测怎么说", "判断"], [
        ["行业组「第一次进前 10%」当作新主题提示", f'之后 24 个月比全部股票平均 {pct(sig["p_comp"]["24"]["ex_uni"])}；大主题命中率 {c24["big_spy"]/c24["n"]*100:.0f}% vs 随便挑 {b24["big_spy"]/b24["n"]*100:.0f}%', '<b style="color:#C62828;">不支持</b>：误报太多'],
        ["行业组 52 周新高比例 / Stage 2 比例排行", f'在前 10% 之后 24 个月比全部股票平均 {pct(top["p_nh"]["24"]["ex_uni"])} / {pct(top["p_s2"]["24"]["ex_uni"])}', '<b style="color:#C62828;">不支持</b>当作买进理由；可当「已经很热」的提醒'],
        ["行业组 RS 排名、RS≥90 成员比例排行（网站已有类似的「热门产业组」）", f'在前 10% 之后 12 个月比全部股票平均 {pct(top["p_score"]["12"]["ex_uni"])} / {pct(top["p_rs90"]["12"]["ex_uni"])}，24 个月 {pct(top["p_score"]["24"]["ex_uni"])} / {pct(top["p_rs90"]["24"]["ex_uni"])}', '<b style="color:#2E7D32;">小幅支持</b>，只管 6–12 个月，不是 2–3 年'],
        ["自己定几个「主题篮子」（或直接用主题 ETF），每月算同样 4 项，对照行业组门槛", "7 个过去的主题，篮子都在低点后 1 年内亮；但篮子是事后挑的，命中率和误报没法公平回测", '<b style="color:#F57C00;">可以做成「确认」工具</b>，要写明没有回测支持、篮子是人定的'],
        ["资本开支、上市申请数、法规 / 法案数、ETF 份额", "数据取得到（第 6 节），没有足够历史可回测；资本开支在 AI 这个例子里比价格晚", '<b style="color:#F57C00;">只能当背景资料</b>，不能写成「领先指标」'],
        ["分析师预估修正广度", "没有免费历史", '要先每天存数据，至少一两年后才能验证'],
    ]))
    note("以上是研究结论。2026-11-13 之后网站「选股 → 主题雷达」分页照第 3、4 行的做法每天更新（tools/theme_radar.py）：主题 ETF 对照行业组的状态 + RS ≥ 90 且 Stage 2 的股票，页面写明没有回测证明会变成大主题。")

    # ---------- 9 ----------
    sec("9. 方法、局限、数据核对", "s9")
    add('<ul style="line-height:1.85;margin:6px 0;padding-left:20px;font-size:14px;">'
        f'<li><b>幸存者偏差</b>：只有今天还在交易的 {M["n_stocks"]:,} 只。热门主题里倒掉的公司（太阳能 2008–2012、大麻 2019 之后、电动车 SPAC 2021 之后）不在数据里，所以主题和强势组的真实回报比表里差。「比全部股票平均」只扣掉了平均的偏差，扣不掉「强势组里死掉的更多」这一部分。</li>'
        '<li><b>行业标签是今天的</b>：TradingView 现在的 industry 套用到 20 年历史。公司转型（例如以前做显卡、现在算 AI）会让过去的分组不准。</li>'
        '<li><b>股票池偏大型</b>：市值 ≥3 亿美元、成交额 ≥1,000 万美元（按今天），没有 ADR（台积电、诺和诺德等是另外补进主题篮子的）。小型主题股（例如早期大麻股）基本不在。</li>'
        '<li><b>主题篮子是事后挑的</b>：第 5 节的涨幅不能当成可实现的回报。</li>'
        '<li><b>价格不含股息</b>：个股和 SPY 都不含，高股息行业（公用事业、REIT）会被低估一点。</li>'
        '<li><b>没有算交易成本和税</b>；回报是「信号当天收盘各买一份、拿着不动」。</li>'
        '<li><b>持有期重叠</b>：每月都算一次、每次看未来 24 个月，样本互相重叠，实际独立的样本比次数少得多，t 值偏乐观。真正独立的 24 个月区间 20 年里只有约 10 段。</li>'
        '<li><b>RS Rating</b> 公式同 tools/rs_rating.py（2×c/c[63] + c/c[126] + c/c[189] + c/c[252]），这里按交易日对齐后每月底在全股票池排百分位。Stage 2 条件同 tools/jlaw_daily_screen.py 的 stage_check（没有用成交额门槛）。</li>'
        '</ul>')
    add('<h3 style="margin:14px 0 6px;font-size:15px;">数据核对</h3>')
    rows = [[("✔ " if c["ok"] else "⚠ ") + c["name"], esc(c["detail"])] for c in X]
    smh = themes["AI / 半导体"]["etf"].get("SMH", {}).get("sig")
    rows.append(["✔ / ⚠ 主题篮子 vs 主题 ETF（第二来源）", f'AI / 半导体：篮子组 RS 排名 {themes["AI / 半导体"]["sig"]["p_score"]["date"]} 进前 10%，SMH {smh["date"] if smh else "没有"}；其余见第 5 节各主题的 ETF 表（太阳能、核能一致；云端、公用事业、大麻不一致，已在正文写明）'])
    rows.append(["✔ 非价格数据来源", f'{len(S["sources"])} 项逐个实际抓取，{ok} 项取到、{len(S["sources"])-ok} 项没取到（第 6 节逐项列出）'])
    add(table(["项目", "结果"], rows, small=True))
    add('<h3 style="margin:14px 0 6px;font-size:15px;">程序（都在 回测/主题/）</h3>')
    add(table(["文件", "做什么"], [
        ["download_extra.py", "下载股票池以外的主题股（ADR）和主题 ETF 日线 → cache_extra/"],
        ["build_indicators.py", "每月算行业组、主题篮子、ETF 的 4 项指标和之后 6 / 12 / 24 个月涨跌 → data/panel.pkl 等"],
        ["analyze.py", "信号回测、持续性、误报、过去主题、现在读数 → data/results.json"],
        ["check_sources.py", "逐个实际抓取非价格数据来源 + 资本开支例子 → data/sources.json"],
        ["crosscheck.py", "数据核对 → data/crosscheck.json"],
        ["report.py", "生成这份报告"],
        ["now.py", "研究阶段的本机版「主题现况」（网站每天更新的版本是 tools/theme_radar.py）"],
    ], small=True))
    note("重跑：python 回测/主题/download_extra.py → build_indicators.py → analyze.py → check_sources.py → crosscheck.py → report.py（全部约 3 分钟；日线读仓库旁边的 回测/cache20）。")

    toc = [("s1", "1. 怎么读"), ("s2", "2. 信号回测"), ("s3", "3. 能强多久"), ("s4", "4. 误报"), ("s5", "5. 过去 7 个主题"), ("s6", "6. 价格以外的数据"), ("s7", "7. 现在的读数"), ("s8", "8. 对「主题雷达」的含义"), ("s9", "9. 方法和核对")]
    nav = " ".join(f'<a href="#{i}" style="display:inline-block;margin:3px 4px 3px 0;padding:4px 10px;background:#E3F2FD;color:#1565C0;border-radius:14px;text-decoration:none;font-size:13px;">{t}</a>' for i, t in toc)
    page = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>主题雷达研究：什么数据能提早看到下一个主题</title>
<style>body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;max-width:1180px;margin:0 auto;padding:18px;color:#222;font-size:14.5px;background:#fff;}}
code{{background:#f3f3f3;padding:1px 5px;border-radius:3px;font-size:12.5px;}} table tr:hover td{{background:#FAFAFA;}} h3{{color:#1F4E78;}}</style></head><body>
<h1 style="font-size:23px;margin:6px 0 4px;">主题雷达研究：什么数据能提早看到下一个市场主题？</h1>
<div style="color:#777;font-size:13px;">规则回测，不含 AI 生成内容 · 数据 {M["first"]} 至 {M["last"]} · {M["n_stocks"]:,} 只美股（今天还在交易的）· 对照 SPY 和全部股票平均 · 不是投资建议</div>
<div style="margin:10px 0;">{nav}</div>
{"".join(P)}
</body></html>'''
    assert "\x08" not in page
    open(OUT, "w", encoding="utf-8").write(page)
    print("写好", OUT, f"{len(page)/1024:.0f} KB")


if __name__ == "__main__":
    main()
