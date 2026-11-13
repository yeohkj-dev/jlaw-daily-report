"""主题雷达研究 ①：按月算「行业组指标」。

数据：回测/cache20（约 2,250 只今天还在交易的美股，2005–2026 日线，价格不含股息）+ universe.json 的 TradingView industry。
行业标签是「今天」的分类，套用到全部历史（公司以前可能属于别的行业）。
每个月最后一个交易日，对每个行业组（当天至少 MIN_N 只成员有 ≥253 根K线）算 4 个指标：
  rs     组 RS：组内成员等权日报酬串成指数，用 RS Rating 同一条公式（2×c/c[63]+c/c[126]+c/c[189]+c/c[252]）算分数
  nh     52 周新高比例：最近 21 个交易日里，最高价创过 252 日新高的成员比例
  s2     Stage 2 比例：收盘 > 50 天线 > 200 天线、200 天线 21 日升 ≥1%、50 天线 10 日向上、
         收盘 ≥ 52 周高 ×0.75、≥ 52 周低 ×1.25（同 tools/jlaw_daily_screen.py stage_check，不含成交额门槛）
  rs90   RS ≥ 90 比例：成员的个股 RS Rating（同 tools/rs_rating.py，全股票池百分位）≥ 90 的比例
每个指标在当月全部行业组里排百分位（0–1）；comp = 4 个百分位的平均。
之后 6 / 12 / 24 个月（126 / 252 / 504 个交易日）的报酬 = 当天成员各买一份、一直拿着的平均涨跌；
对照：同期 SPY、同期「全部股票等权平均」（后者用来扣掉幸存者偏差）。

另外把「主题篮子」（事后挑的代表股，见 THEMES）和主题 ETF 当成额外的组，用同一套指标、对照当月行业组的门槛。
输出：回测/主题/data/panel.pkl、themes.pkl、etf.pkl、meta.json
用法：python 回测/主题/build_indicators.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BT = os.environ.get("BT_DIR") or os.path.join(os.path.dirname(REPO), "回测")       # 日线缓存在仓库旁边的 回测/
CACHE, EXTRA, OUT = os.path.join(BT, "cache20"), os.path.join(HERE, "cache_extra"), os.path.join(HERE, "data")
os.makedirs(OUT, exist_ok=True)
MIN_N = 5
HORIZ = {6: 126, 12: 252, 24: 504}

# 主题篮子：事后挑的代表股（今天还查得到日线的）。win = 观察窗口（找信号、找高点）
THEMES = {
    "智能手机 / 移动芯片": dict(t=["AAPL", "QCOM", "SWKS", "AVGO", "CRUS"], win=("2008-12-31", "2013-12-31"), etf=[]),
    "云端 / SaaS": dict(t=["CRM", "AMZN", "ADBE", "AKAM", "EQIX", "FFIV", "NOW", "WDAY"], win=("2008-12-31", "2014-12-31"), etf=["IGV", "SKYY"]),
    "大麻": dict(t=["CGC", "ACB", "CRON", "TLRY", "IIPR"], win=("2016-06-30", "2019-12-31"), etf=["MJ"]),
    "电动车 / 太阳能 / 清洁能源": dict(t=["TSLA", "NIO", "ENPH", "FSLR", "SEDG", "RUN", "PLUG"], win=("2018-12-31", "2021-12-31"), etf=["TAN", "ICLN", "QCLN", "LIT"]),
    "减肥药 GLP-1": dict(t=["LLY", "NVO", "VKTX"], win=("2021-06-30", "2025-06-30"), etf=[]),
    "AI / 半导体": dict(t=["NVDA", "AMD", "AVGO", "MRVL", "MU", "SMCI", "ANET", "VRT", "TSM", "ASML"], win=("2022-06-30", "2026-11-30"), etf=["SMH", "SOXX"]),
    "电力 / 公用事业 / 核能": dict(t=["VST", "CEG", "NRG", "TLN", "GEV", "ETN", "CCJ", "BWXT", "LEU", "OKLO", "SMR", "PWR"], win=("2022-12-31", "2026-11-30"), etf=["URA", "NLR", "XLU"]),
}


def load(path):
    d = json.load(open(path))
    return pd.DataFrame({"c": d["c"], "h": d["h"], "l": d["l"]}, index=pd.to_datetime(d["d"]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    uni = {r["name"]: r for r in json.load(open(os.path.join(BT, "universe.json"), encoding="utf-8"))}
    spy = load(os.path.join(CACHE, "SPY.json"))
    idx = spy.index
    syms = sorted(f[:-5] for f in os.listdir(CACHE) if f.endswith(".json"))
    stocks = [s for s in syms if s in uni and uni[s].get("industry") and uni[s]["industry"] != "ETF" and s not in ("SPY", "QQQ")]
    extra = sorted(f[:-5] for f in os.listdir(EXTRA) if f.endswith(".json"))
    theme_syms = sorted({t for v in THEMES.values() for t in v["t"]})
    etfs = sorted(set(extra) - set(theme_syms) - {"XPEV", "LI"})
    add = [s for s in theme_syms if s not in stocks]            # 股票池以外的主题股（ADR 等）
    cols = stocks + add + etfs
    C = np.full((len(idx), len(cols)), np.nan); H = C.copy(); L = C.copy()
    for j, s in enumerate(cols):
        p = os.path.join(CACHE, s + ".json") if s in stocks else os.path.join(EXTRA, s + ".json")
        d = load(p)
        d = d[~d.index.duplicated()].reindex(idx)
        C[:, j], H[:, j], L[:, j] = d["c"], d["h"], d["l"]
    C = pd.DataFrame(C, index=idx, columns=cols); H = pd.DataFrame(H, index=idx, columns=cols); L = pd.DataFrame(L, index=idx, columns=cols)
    C[C <= 0] = np.nan
    print("股票", len(stocks), "补充主题股", add, "ETF", len(etfs), "交易日", len(idx), idx[0].date(), idx[-1].date())

    def score(P):
        return 2 * P / P.shift(63) + P / P.shift(126) + P / P.shift(189) + P / P.shift(252)

    S = score(C)                                                # 个股 RS 分数（按交易日对齐）
    s50, s200 = C.rolling(50).mean(), C.rolling(200).mean()
    hi52, lo52 = H.rolling(252).max(), L.rolling(252).min()
    stage2 = ((C > s50) & (s50 > s200) & (s200 / s200.shift(21) - 1 >= 0.01) & (s50 / s50.shift(10) - 1 > 0)
              & (C >= 0.75 * hi52) & (C >= 1.25 * lo52))
    newhi = (H >= hi52).rolling(21).max() > 0                   # 近 21 天创过 52 周新高
    R = C.pct_change(fill_method=None).clip(-0.9, 3.0)

    me = pd.Series(idx, index=idx).groupby([idx.year, idx.month]).last().values     # 每月最后一个交易日
    me = pd.DatetimeIndex(me)
    pos = idx.get_indexer(me)
    valid = S.notna()                                           # 有 ≥253 根K线才算成员
    ust = np.array([c in set(stocks) for c in cols])            # 只有股票池的股票参与 RS 百分位

    # 个股 RS Rating（每月底，全股票池百分位 1–99）
    Sm = S.iloc[pos].values
    rating = np.full(Sm.shape, np.nan)
    for i in range(len(pos)):
        base = np.sort(Sm[i][ust & ~np.isnan(Sm[i])])
        if len(base) < 200:
            continue
        ok = ~np.isnan(Sm[i])
        rating[i, ok] = np.clip(np.searchsorted(base, Sm[i][ok], side="right") / len(base) * 100, 1, 99)
    rating = pd.DataFrame(rating, index=me, columns=cols)

    # 之后 N 个月：个股买入持有
    fwd = {}
    Cv = C.values
    for m, h in HORIZ.items():
        f = np.full((len(pos), len(cols)), np.nan)
        for i, p in enumerate(pos):
            if p + h < len(idx):
                f[i] = Cv[p + h] / Cv[p] - 1
        fwd[m] = pd.DataFrame(f, index=me, columns=cols)
    spyc = spy["c"].values
    spy_f = {m: pd.Series([spyc[p + h] / spyc[p] - 1 if p + h < len(idx) else np.nan for p in pos], index=me) for m, h in HORIZ.items()}
    vm = valid.iloc[pos].values
    uni_f = {m: pd.Series(np.nanmean(np.where(vm & ust, fwd[m].values, np.nan), axis=1), index=me) for m in HORIZ}
    spy_score = score(spy["c"]).iloc[pos]

    def group_rows(name, members, kind):
        """一个组在每个月底的原始指标。"""
        mem = [c for c in members if c in C.columns]
        r = R[mem].where(valid[mem].shift(1, fill_value=False)).mean(axis=1)       # 成员等权日报酬
        gi = (1 + r.fillna(0)).cumprod()
        gs = score(gi).iloc[pos]
        v = valid[mem].iloc[pos]
        n = v.sum(axis=1)
        rt = rating[mem]
        out = pd.DataFrame(dict(group=name, kind=kind, n=n.values, score=gs.values,
                                nh=(newhi[mem].iloc[pos] & v).sum(axis=1).values / n.replace(0, np.nan).values,
                                s2=(stage2[mem].iloc[pos] & v).sum(axis=1).values / n.replace(0, np.nan).values,
                                rs90=((rt >= 90) & v.values).sum(axis=1).values / n.replace(0, np.nan).values,
                                n_rs90=((rt >= 90) & v.values).sum(axis=1).values,
                                r12=(gi / gi.shift(252) - 1).iloc[pos].values, level=gi.iloc[pos].values), index=me)
        for m in HORIZ:
            out[f"f{m}"] = np.nanmean(np.where(v.values, fwd[m][mem].values, np.nan), axis=1) if len(mem) else np.nan
            out[f"spy{m}"] = spy_f[m].values
            out[f"uni{m}"] = uni_f[m].values
        out["spy_score"] = spy_score.values
        out.loc[out["n"] < 1, ["score", "nh", "s2", "rs90"]] = np.nan
        return out.rename_axis("date").reset_index()

    ind = {}
    for s in stocks:
        ind.setdefault(uni[s]["industry"], []).append(s)
    panel = pd.concat([group_rows(g, m, "industry") for g, m in sorted(ind.items()) if len(m) >= MIN_N], ignore_index=True)
    panel = panel[(panel["n"] >= MIN_N) & panel["score"].notna()].copy()
    MEAS = ["score", "nh", "s2", "rs90"]
    for k in MEAS:
        panel["p_" + k] = panel.groupby("date")[k].rank(pct=True)
    panel["comp"] = panel[["p_" + k for k in MEAS]].mean(axis=1)
    panel["p_comp"] = panel.groupby("date")["comp"].rank(pct=True)
    panel["n_groups"] = panel.groupby("date")["group"].transform("count")
    panel.to_pickle(os.path.join(OUT, "panel.pkl"))

    def vs_industries(rows):
        """额外的组（主题篮子、ETF）对照当月行业组：每个指标赢过多少比例的行业组。"""
        rows = rows[rows["score"].notna()].copy()
        by = {d: g for d, g in panel.groupby("date")}
        for k in MEAS:
            rows["p_" + k] = [np.nan if d not in by or pd.isna(x) else float((by[d][k] <= x).mean()) for d, x in zip(rows["date"], rows[k])]
        rows["comp"] = rows[["p_" + k for k in MEAS]].mean(axis=1)
        rows["p_comp"] = [np.nan if d not in by or pd.isna(x) else float((by[d]["comp"] <= x).mean()) for d, x in zip(rows["date"], rows["comp"])]
        return rows

    th = pd.concat([group_rows(g, v["t"], "theme") for g, v in THEMES.items()], ignore_index=True)
    vs_industries(th).to_pickle(os.path.join(OUT, "themes.pkl"))
    ef = pd.concat([group_rows(e, [e], "etf") for e in etfs], ignore_index=True)
    vs_industries(ef).to_pickle(os.path.join(OUT, "etf.pkl"))
    # 日线层面的篮子指数（画走势、找高低点用）
    lv = {}
    for g, v in THEMES.items():
        mem = [c for c in v["t"] if c in C.columns]
        r = R[mem].where(valid[mem].shift(1, fill_value=False)).mean(axis=1)
        lv[g] = (1 + r.fillna(0)).cumprod()
    for e in etfs:
        lv[e] = C[e]
    lv["SPY"] = spy["c"]
    pd.DataFrame(lv).to_pickle(os.path.join(OUT, "levels.pkl"))
    json.dump(dict(first=str(idx[0].date()), last=str(idx[-1].date()), n_stocks=len(stocks), n_groups_all=int(sum(len(m) >= MIN_N for m in ind.values())),
                   n_industries=len(ind), min_n=MIN_N, added=add, etfs=etfs,
                   members={g: sorted(m) for g, m in ind.items()},
                   exchange={s: uni[s].get("exchange") or "" for s in stocks},
                   themes={g: dict(t=[t for t in v["t"] if t in C.columns], win=v["win"], etf=v["etf"]) for g, v in THEMES.items()},
                   stocks_by_year={str(y): int(valid.loc[valid.index.year == y].iloc[-1][stocks].sum()) for y in range(2006, idx[-1].year + 1)},
                   groups_by_year={str(y): int(panel[panel["date"].dt.year == y].groupby("date")["group"].count().iloc[-1]) for y in range(2006, idx[-1].year + 1)}),
              open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("panel", panel.shape, panel["date"].min().date(), panel["date"].max().date(), "组/月", panel.groupby("date")["group"].count().describe()[["min", "50%", "max"]].to_dict())


if __name__ == "__main__":
    main()
