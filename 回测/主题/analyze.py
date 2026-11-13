"""主题雷达研究 ②：回测。读 data/panel.pkl、themes.pkl、etf.pkl、levels.pkl，写 data/results.json。

信号 =「第一次进前 10%」：某行业组这个月某指标排在全部行业组的前 10%（百分位 ≥ 0.9），而且之前 12 个月都不在前 10%
（并且这个组之前至少已有 12 个月的记录）。
之后 6 / 12 / 24 个月：组内成员各买一份一直拿着的平均涨跌，对比 ① 同期 SPY ② 同期全部股票等权平均（扣掉幸存者偏差）。
用法：python 回测/主题/analyze.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
TOP, LOOKBACK = 0.9, 12
HZ = (6, 12, 24)
MEAS = {"p_score": "组 RS 排名", "p_nh": "52 周新高比例", "p_s2": "Stage 2 比例", "p_rs90": "RS≥90 成员比例",
        "p_comp": "四项综合", "k3": "四项里 ≥3 项同时前 10%", "p_dcomp": "综合分 6 个月升幅（加速）"}


def first_entries(p, col, top=TOP, lookback=LOOKBACK):
    """每个组：这个月在前 10%、之前 lookback 个月都不在。返回信号行。"""
    out = []
    for g, x in p.groupby("group"):
        x = x.sort_values("date")
        on = (x[col] >= top).values
        dates = x["date"].values
        for i in range(lookback, len(x)):
            # 之前 12 个月都有记录（月份连续）且都不在前 10%
            if on[i] and not on[i - lookback:i].any() and (dates[i] - dates[i - lookback]) <= np.timedelta64(400, "D"):
                out.append(x.index[i])
    return p.loc[out]


def stats(s, base=None):
    """一批信号在各期限的表现。"""
    r = {"n": int(len(s))}
    for h in HZ:
        x = s.dropna(subset=[f"f{h}"])
        if len(x) < 5:
            r[str(h)] = None
            continue
        es, eu = x[f"f{h}"] - x[f"spy{h}"], x[f"f{h}"] - x[f"uni{h}"]
        yr = eu.groupby(x["date"].dt.year).mean()
        mo = eu.groupby(x["date"]).mean()                       # 同一个月的信号先平均，再算 t（信号扎堆时不重复计）
        t = float(mo.mean() / (mo.std(ddof=1) / np.sqrt(len(mo)))) if len(mo) > 2 and mo.std(ddof=1) > 0 else None
        h1, h2 = eu[x["date"] < "2016-01-01"], eu[x["date"] >= "2016-01-01"]
        r[str(h)] = dict(n=int(len(x)), ret=float(x[f"f{h}"].mean()), spy=float(x[f"spy{h}"].mean()), uni=float(x[f"uni{h}"].mean()),
                         ex_spy=float(es.mean()), ex_uni=float(eu.mean()), med_ex_spy=float(es.median()), med_ex_uni=float(eu.median()),
                         win_spy=float((es > 0).mean()), win_uni=float((eu > 0).mean()),
                         years=int(len(yr)), years_pos=int((yr > 0).sum()), t_uni=t,
                         ex_uni_0615=float(h1.mean()) if len(h1) else None, n_0615=int(len(h1)),
                         ex_uni_1626=float(h2.mean()) if len(h2) else None, n_1626=int(len(h2)),
                         big=float((es >= 0.5).mean()), lose=float((es < 0).mean()))
    return r


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = pd.read_pickle(os.path.join(D, "panel.pkl")).sort_values(["group", "date"]).reset_index(drop=True)
    th = pd.read_pickle(os.path.join(D, "themes.pkl"))
    ef = pd.read_pickle(os.path.join(D, "etf.pkl"))
    lv = pd.read_pickle(os.path.join(D, "levels.pkl"))
    meta = json.load(open(os.path.join(D, "meta.json"), encoding="utf-8"))
    last = p["date"].max()
    p["k3"] = ((p[["p_score", "p_nh", "p_s2", "p_rs90"]] >= TOP).sum(axis=1) >= 3).astype(float)     # 1 = 成立（≥0.9 判定照用）
    p["dcomp"] = p["comp"] - p.groupby("group")["comp"].shift(6)
    p["p_dcomp"] = p.groupby("date")["dcomp"].rank(pct=True)
    res = dict(asof=str(last.date()), top=TOP, lookback=LOOKBACK, meas=MEAS, meta={k: meta[k] for k in ("first", "last", "n_stocks", "n_industries", "min_n", "stocks_by_year", "groups_by_year")})

    # 0. 基准：任何一个组、任何一个月
    res["base"] = stats(p)
    res["bias"] = {str(h): dict(uni=float(p.drop_duplicates("date")[f"uni{h}"].mean()), spy=float(p.drop_duplicates("date")[f"spy{h}"].mean())) for h in HZ}

    # A. 第一次进前 10%
    sig = {}
    res["signals"] = {}
    for col in MEAS:
        s = first_entries(p, col)
        sig[col] = s
        res["signals"][col] = stats(s)
        res["signals"][col]["per_year"] = float(len(s) / ((last - p["date"].min()).days / 365.25))
    # 「一直在前 10%」（不只第一次）
    res["in_top"] = {col: stats(p[p[col] >= TOP]) for col in MEAS}
    # 反过来：最弱的 10%
    res["bottom"] = {col: stats(p[p[col] <= 0.1]) for col in ("p_score", "p_comp")}

    # B. 按综合分分 5 档
    res["quint"] = {}
    for col in ("p_comp", "p_score"):
        b = pd.cut(p[col], [0, .2, .4, .6, .8, 1.0], labels=["最弱 20%", "20–40%", "40–60%", "60–80%", "最强 20%"], include_lowest=True)
        res["quint"][col] = {str(k): stats(v) for k, v in p.groupby(b, observed=True)}

    # 持续性：这个月在前 10% → N 个月后还在前 10% / 前 25% 的比例
    res["persist"] = {}
    for col in ("p_comp", "p_score"):
        w = p.pivot(index="date", columns="group", values=col)
        o = {}
        for m in (3, 6, 12, 24, 36):
            now, fut = w.iloc[:-m], w.shift(-m).iloc[:-m]
            mk = (now >= TOP) & fut.notna()
            o[str(m)] = dict(top10=float((fut[mk] >= 0.9).sum().sum() / mk.sum().sum()), top25=float((fut[mk] >= 0.75).sum().sum() / mk.sum().sum()),
                             bottom50=float((fut[mk] < 0.5).sum().sum() / mk.sum().sum()))
        res["persist"][col] = o
    # 第一次进前 10% 之后 24 个月里，有几个月还在前 10%
    w = p.pivot(index="date", columns="group", values="p_comp")
    stay = []
    for _, r in sig["p_comp"].iterrows():
        x = w[r["group"]].loc[r["date"]:].iloc[1:25]
        if len(x) == 24:
            stay.append(int((x >= TOP).sum()))
    res["stay24"] = dict(n=len(stay), median=float(np.median(stay)), mean=float(np.mean(stay)), le3=float(np.mean(np.array(stay) <= 3)), ge12=float(np.mean(np.array(stay) >= 12)))

    # C. 误报：综合信号 24 个月后的结果分类（对 SPY 和对全部股票平均）
    def classify(s, h=24):
        x = s.dropna(subset=[f"f{h}"])
        es, eu = x[f"f{h}"] - x[f"spy{h}"], x[f"f{h}"] - x[f"uni{h}"]
        return dict(n=int(len(x)), big_spy=int((es >= .5).sum()), win_spy=int(((es >= 0) & (es < .5)).sum()), lose_spy=int((es < 0).sum()),
                    big_uni=int((eu >= .5).sum()), win_uni=int(((eu >= 0) & (eu < .5)).sum()), lose_uni=int((eu < 0).sum()))
    res["classify"] = {col: classify(sig[col]) for col in MEAS}
    res["classify"]["base"] = classify(p)

    def rows(s, n=12, asc=False):
        x = s.dropna(subset=["f24"]).assign(ex=lambda d: d["f24"] - d["spy24"], exu=lambda d: d["f24"] - d["uni24"]).sort_values("ex", ascending=asc).head(n)
        return [dict(date=str(r["date"].date()), group=r["group"], n=int(r["n"]), f24=float(r["f24"]), spy24=float(r["spy24"]), uni24=float(r["uni24"]),
                     f12=float(r["f12"]), spy12=float(r["spy12"]), r12=float(r["r12"])) for _, r in x.iterrows()]
    res["best"] = rows(sig["p_comp"]); res["worst"] = rows(sig["p_comp"], asc=True)
    # 每年综合信号数量和结果
    s = sig["p_comp"].assign(ex=lambda d: d["f24"] - d["spy24"], exu=lambda d: d["f24"] - d["uni24"], y=lambda d: d["date"].dt.year)
    res["by_year"] = [dict(year=int(y), n=int(len(g)), done=int(g["ex"].notna().sum()),
                           ex_spy=None if g["ex"].notna().sum() == 0 else float(g["ex"].mean()), ex_uni=None if g["exu"].notna().sum() == 0 else float(g["exu"].mean()),
                           groups=sorted(g["group"])) for y, g in s.groupby("y")]

    # G. 倒过来看：之后 24 个月最强的 5%（对全部股票平均），起涨当时综合分在哪里
    x = p.dropna(subset=["f24"]).assign(exu=lambda d: d["f24"] - d["uni24"])
    cut = x["exu"].quantile(0.95)
    win = x[x["exu"] >= cut]
    res["winners"] = dict(cut=float(cut), n=int(len(win)), mean_comp=float(win["p_comp"].mean()), top10=float((win["p_comp"] >= .9).mean()),
                          top25=float((win["p_comp"] >= .75).mean()), bottom50=float((win["p_comp"] < .5).mean()), bottom10=float((win["p_comp"] <= .1).mean()),
                          p_top_given_sig=float((x[x["p_comp"] >= .9]["exu"] >= cut).mean()), mean_r12=float(win["r12"].mean()), mean_r12_all=float(x["r12"].mean()))

    # E. 过去的大主题
    themes = {}
    for g, v in meta["themes"].items():
        t = th[th["group"] == g].set_index("date").sort_index()
        a, b = pd.Timestamp(v["win"][0]), min(pd.Timestamp(v["win"][1]), last)
        L = lv[g].loc[a:b]
        peak = L.idxmax()
        low = L.loc[:peak].idxmin()
        spyL = lv["SPY"]
        o = dict(tickers=v["t"], win=[str(a.date()), str(b.date())], low=str(low.date()), peak=str(peak.date()), still_high=bool((b - peak).days < 45 and b >= last - pd.Timedelta(days=40)),
                 run=float(L[peak] / L[low] - 1), run_spy=float(spyL[peak] / spyL[low] - 1), sig={})
        for col in ("p_score", "p_nh", "p_s2", "p_rs90", "p_comp"):
            x = t.loc[low:peak]                                   # 从低点到高点之间，第一次进前 10%
            x = x[(x[col] >= TOP) & (x["n"] >= 2)]
            if not len(x):
                o["sig"][col] = None
                continue
            d = x.index[0]
            r = x.iloc[0]
            lvl = lv[g]
            o["sig"][col] = dict(date=str(d.date()), n=int(r["n"]), months_from_low=round((d - low).days / 30.44, 1), months_to_peak=round((peak - d).days / 30.44, 1),
                                 gain_before=float(lvl[d] / lvl[low] - 1), gain_after=float(lvl[peak] / lvl[d] - 1),
                                 share_left=float(np.log(lvl[peak] / lvl[d]) / np.log(lvl[peak] / lvl[low])),
                                 spy_after=float(spyL[peak] / spyL[d] - 1),
                                 **{f"f{h}": None if pd.isna(r[f"f{h}"]) else float(r[f"f{h}"]) for h in HZ}, **{f"spy{h}": None if pd.isna(r[f"spy{h}"]) else float(r[f"spy{h}"]) for h in HZ})
        # 窗口开始前 36 个月里，综合分进过前 10% 几个月（早到的假信号 / 更早的一波）
        pre = t.loc[a - pd.DateOffset(months=36):low]
        o["pre_months_top"] = int((pre["p_comp"] >= TOP).sum())
        pl = lv[g].loc[a - pd.DateOffset(months=36):low]              # 这一波之前 36 个月的高点 → 这一波低点，篮子跌了多少
        o["pre_dd"] = float(pl.iloc[-1] / pl.max() - 1) if len(pl) > 20 else None
        o["pre_high"] = str(pl.idxmax().date()) if len(pl) > 20 else None
        # 月度轨迹（画表用）：低点前 6 个月到高点后 6 个月
        tr = t.loc[low - pd.DateOffset(months=6):peak + pd.DateOffset(months=6)]
        o["track"] = [dict(d=str(i.date())[:7], comp=None if pd.isna(r["p_comp"]) else round(float(r["p_comp"]), 2), rs=None if pd.isna(r["p_score"]) else round(float(r["p_score"]), 2),
                           lvl=round(float(lv[g].loc[:i].iloc[-1] / lv[g][low]), 2)) for i, r in tr.iterrows()]
        # 主题 ETF：组 RS 排名第一次赢过 90% 的行业组
        o["etf"] = {}
        for e in v["etf"]:
            x = ef[ef["group"] == e].set_index("date").sort_index().loc[low:peak]
            x = x[x["p_score"] >= TOP]
            if e in lv and lv[e].loc[low:peak].notna().sum() > 20:
                el = lv[e]
                e0 = el.loc[low:peak].dropna()
                o["etf"][e] = dict(run=float(e0.iloc[-1] / e0.iloc[0] - 1), first=str(e0.index[0].date()),
                                   sig=None if not len(x) else dict(date=str(x.index[0].date()), gain_before=float(el.loc[:x.index[0]].dropna().iloc[-1] / e0.iloc[0] - 1),
                                                                    gain_after=float(e0.iloc[-1] / el.loc[:x.index[0]].dropna().iloc[-1] - 1)))
        themes[g] = o
    # 对应的 TradingView 行业组在同一段时间的综合信号
    IND = {"智能手机 / 移动芯片": ["Telecommunications Equipment", "Semiconductors"], "云端 / SaaS": ["Packaged Software", "Internet Software/Services", "Information Technology Services"],
           "大麻": ["Agricultural Commodities/Milling", "Pharmaceuticals: Other"], "电动车 / 太阳能 / 清洁能源": ["Motor Vehicles", "Electrical Products", "Alternative Power Generation"],
           "减肥药 GLP-1": ["Pharmaceuticals: Major", "Biotechnology"], "AI / 半导体": ["Semiconductors", "Computer Processing Hardware", "Electronic Production Equipment", "Computer Peripherals"],
           "电力 / 公用事业 / 核能": ["Electric Utilities", "Electrical Products", "Alternative Power Generation", "Engineering & Construction"]}
    for g, inds in IND.items():
        o = themes[g]
        o["industries"] = {}
        for i in inds:
            x = p[(p["group"] == i) & (p["date"] >= o["low"]) & (p["date"] <= o["peak"])]
            n_all = len(x)
            hit = x[x["p_comp"] >= TOP]
            hit_rs = x[x["p_score"] >= TOP]
            o["industries"][i] = dict(months=int(n_all), n=None if not n_all else int(x["n"].iloc[-1]), comp_first=None if not len(hit) else str(hit["date"].iloc[0].date()), comp_months=int(len(hit)),
                                      rs_first=None if not len(hit_rs) else str(hit_rs["date"].iloc[0].date()), rs_months=int(len(hit_rs)),
                                      best_comp=None if not n_all else float(x["p_comp"].max()))
    res["themes"] = themes

    # F. 现在：综合分前 10% 的行业组
    cur = p[p["date"] == last].sort_values("comp", ascending=False)
    now = []
    for _, r in cur[cur["p_comp"] >= TOP].iterrows():
        h = p[(p["group"] == r["group"])].set_index("date")["p_comp"]
        streak = 0
        for v in h.iloc[::-1]:
            if v >= TOP:
                streak += 1
            else:
                break
        fe = sig["p_comp"][sig["p_comp"]["group"] == r["group"]]["date"]
        now.append(dict(group=r["group"], n=int(r["n"]), p_score=float(r["p_score"]), nh=float(r["nh"]), s2=float(r["s2"]), rs90=float(r["rs90"]), n_rs90=int(r["n_rs90"]),
                        r12=float(r["r12"]), streak=streak, last_first=None if not len(fe) else str(fe.iloc[-1].date()), months12=int((h.iloc[-12:] >= TOP).sum())))
    res["now"] = now
    res["now_new"] = [dict(group=r["group"], date=str(r["date"].date())) for _, r in sig["p_comp"][sig["p_comp"]["date"] >= last - pd.DateOffset(months=12)].iterrows()]
    spy12 = float(lv["SPY"].iloc[-1] / lv["SPY"].iloc[-253] - 1)
    res["spy_r12_now"] = spy12

    json.dump(res, open(os.path.join(D, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 给人看的摘要
    pc = lambda v: "  --  " if v is None else f"{v*100:+6.1f}%"
    print("基准（任何组任何月）", {h: pc(res["base"][str(h)]["ex_spy"]) + " vs SPY / " + pc(res["base"][str(h)]["ex_uni"]) + " vs 全部" for h in HZ})
    for col, nm in MEAS.items():
        r = res["signals"][col]
        print(f"{nm:<22} n={r['n']:<4}", " | ".join(f"{h}m SPY{pc(r[str(h)]['ex_spy'])} 全{pc(r[str(h)]['ex_uni'])} 中位{pc(r[str(h)]['med_ex_uni'])} 胜{r[str(h)]['win_uni']*100:3.0f}% 年{r[str(h)]['years_pos']}/{r[str(h)]['years']} t{r[str(h)]['t_uni']:+.1f}" for h in HZ))
    print("一直在前10%:")
    for col, nm in MEAS.items():
        r = res["in_top"][col]
        print(f"  {nm:<22} n={r['n']:<5}", " | ".join(f"{h}m 全{pc(r[str(h)]['ex_uni'])} t{r[str(h)]['t_uni']:+.1f}" for h in HZ))
    for col in res["quint"]:
        print(col, {k: [pc(v[str(h)]["ex_uni"]) for h in HZ] for k, v in res["quint"][col].items()})
    print("bottom", {c: [pc(v[str(h)]["ex_uni"]) for h in HZ] for c, v in res["bottom"].items()})
    print("persist", res["persist"]); print("stay24", res["stay24"]); print("classify", res["classify"]); print("winners", res["winners"])
    for g, o in themes.items():
        print("\n", g, o["tickers"], "低", o["low"], "高", o["peak"], f"涨 {o['run']*100:.0f}% (SPY {o['run_spy']*100:.0f}%)", "之前36月在前10%:", o["pre_months_top"])
        for col, s in o["sig"].items():
            print("   ", MEAS[col], "无" if s is None else f"{s['date']} 低点后 {s['months_from_low']} 月，已涨 {s['gain_before']*100:.0f}%，之后到高点还涨 {s['gain_after']*100:.0f}%（{s['months_to_peak']} 月），剩 {s['share_left']*100:.0f}%；之后 12m {pc(s['f12'])} vs SPY {pc(s['spy12'])}；24m {pc(s['f24'])} vs {pc(s['spy24'])}")
        print("    行业组:", o["industries"]); print("    ETF:", o["etf"])
    print("\n现在:", [(x["group"], x["streak"]) for x in now])


if __name__ == "__main__":
    main()
