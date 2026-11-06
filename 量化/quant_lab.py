"""量化实验室：市场状态模型 + 多个量化策略回测 + 当前读数。

规则：
- 所有信号用 t 日收盘计算，t+1 日才生效（shift(1)），没有偷看未来。
- 参数全部用学术/业界常用值（200 日线、12-1 月动量、20 日波动、15% 目标波动），没有为这段数据去优化。
- 交易成本：每 100% 换手扣 0.05%（ETF），个股 0.10%。
- 现金收益：BIL（2007 起），之前用 SHY。
输出 results.json，build_report.py 读它生成 HTML。
"""
import json, os, glob
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "stocks")
START = "2003-01-01"

px = pd.read_pickle(os.path.join(DATA, "macro.pkl"))
px = px[px["SPY"].notna()].ffill()          # 去掉盘中未收盘的那一行
px = px[px.index >= "1998-01-01"]
ret = px.pct_change()

cash = ret["BIL"].fillna(ret["SHY"]).fillna(0.0001)
cash = cash.clip(-0.01, 0.01)
SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB"]


# ---------------------------------------------------------------- 市场状态模型
def sma(s, n):
    return s.rolling(n, min_periods=n).mean()


spy = px["SPY"]
sig = pd.DataFrame(index=px.index)
sig["趋势：SPY 在 200 日线上"] = (spy > sma(spy, 200)).astype(float)
sig["趋势：50 日线 > 200 日线"] = (sma(spy, 50) > sma(spy, 200)).astype(float)
sig["动量：SPY 12 个月涨幅 > 现金"] = ((spy / spy.shift(252) - 1) > (1 + cash).rolling(252).apply(np.prod, raw=True) - 1).astype(float)
sec_above = pd.concat([(px[s] > sma(px[s], 200)) for s in SECTORS], axis=1).mean(axis=1)
sig["宽度：≥6/9 板块在 200 日线上"] = (sec_above >= 6 / 9).astype(float)
credit = (px["HYG"] / px["IEF"]).where(px["HYG"].notna(), px["LQD"] / px["IEF"])
sig["信用：高收益债/国债 在 100 日线上"] = (credit > sma(credit, 100)).astype(float)
vix = px["^VIX"]
sig["波动：VIX < 20"] = (vix < 20).astype(float)
ts = vix / px["^VIX3M"]
sig["波动：VIX 期限结构正常（VIX<VIX3M）"] = (ts < 1).astype(float).where(px["^VIX3M"].notna(), (vix < sma(vix, 50)).astype(float))
risk = px["XLY"] / px["XLP"]
sig["风险偏好：可选消费/必需消费 在 100 日线上"] = (risk > sma(risk, 100)).astype(float)
# 早期部分数据缺失时，用当日可用信号的平均
valid = sig.copy()
valid.loc[sma(credit, 100).isna(), "信用：高收益债/国债 在 100 日线上"] = np.nan
valid.loc[sma(spy, 200).isna(), ["趋势：SPY 在 200 日线上", "趋势：50 日线 > 200 日线"]] = np.nan
valid.loc[spy.shift(252).isna(), "动量：SPY 12 个月涨幅 > 现金"] = np.nan
valid.loc[sma(risk, 100).isna(), "风险偏好：可选消费/必需消费 在 100 日线上"] = np.nan
score = valid.mean(axis=1) * 100
score = score[score.index >= "1999-06-01"]


def regime_of(x):
    return "进攻" if x >= 75 else ("中性" if x >= 45 else "防守")


score.to_pickle(os.path.join(DATA, "score.pkl"))

# ---------------------------------------------------------------- 回测工具
def run(weights, rets, cost=0.0005, cash_r=cash):
    """weights: DataFrame（t 日收盘决定的仓位），自动 shift(1)。剩余仓位拿现金。"""
    w = weights.reindex(rets.index).ffill().fillna(0)
    w_live = w.shift(1).fillna(0)
    gross = (w_live * rets.reindex(columns=w.columns).fillna(0)).sum(axis=1)
    cash_w = (1 - w_live.sum(axis=1)).clip(lower=-5)
    turn = w.diff().abs().sum(axis=1).shift(1).fillna(0)
    borrow = (-cash_w).clip(lower=0) * 0.01 / 252        # 借钱加杠杆：现金利率 + 1%/年
    r = gross + cash_w * cash_r.reindex(rets.index).fillna(0) - borrow - turn * cost
    return r, w_live.sum(axis=1), turn


def stats(r, expo=None, turn=None):
    r = r.dropna()
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(252)
    rf = cash.reindex(r.index).fillna(0)
    sharpe = (r - rf).mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0
    dd = eq / eq.cummax() - 1
    mdd = dd.min()
    yearly = (1 + r).groupby(r.index.year).prod() - 1
    out = dict(cagr=cagr, vol=vol, sharpe=sharpe, mdd=mdd, calmar=cagr / abs(mdd) if mdd else 0,
               worst_year=yearly.min(), best_year=yearly.max(), total=eq.iloc[-1] - 1,
               pos_years=float((yearly > 0).mean()))
    if expo is not None:
        out["avg_expo"] = float(expo.reindex(r.index).mean())
    if turn is not None:
        out["turn_per_year"] = float(turn.reindex(r.index).sum() / yrs)
    return {k: float(v) for k, v in out.items()}, eq, dd, yearly


def monthly_mask(idx):
    s = pd.Series(idx, index=idx)
    return s.groupby([idx.year, idx.month]).transform("max") == s


# ---------------------------------------------------------------- 策略
R = ret.copy()
R["CASH"] = cash
idx = R.index[R.index >= START]
strategies = {}


def add(key, name, desc, w, rets=R, cost=0.0005, group="大盘择时"):
    r, e, t = run(w, rets, cost)
    r = r[r.index >= START]
    strategies[key] = dict(name=name, desc=desc, group=group, r=r, expo=e, turn=t)


one = lambda col, s: pd.DataFrame({col: s})

add("bh", "SPY 买入持有", "基准：一直 100% 持有标普 500。", one("SPY", pd.Series(1.0, index=R.index)))
add("qqq", "QQQ 买入持有", "参考：一直 100% 持有纳指 100。", one("QQQ", pd.Series(1.0, index=R.index)))
add("ma200", "200 日线择时", "SPY 收盘在 200 日线上 → 100% SPY；跌破 → 全部现金（BIL）。Faber (2007)。",
    one("SPY", sig["趋势：SPY 在 200 日线上"]))
expo_regime = score.reindex(R.index).ffill().apply(lambda x: 1.0 if x >= 75 else (0.6 if x >= 45 else 0.2) if pd.notna(x) else 1.0)
add("regime", "市场状态仓位", "8 个信号打分：≥75 分 100% 仓位，45–75 分 60%，<45 分 20%。剩余拿现金。",
    one("SPY", expo_regime))
rv = R["SPY"].rolling(20).std() * np.sqrt(252)
vt = (0.15 / rv).clip(upper=1.0)
add("voltarget", "波动率目标 15%", "仓位 = 15% ÷ 过去 20 日实际波动，最多 100%。市场越乱仓位越小。Moreira & Muir (2017)。",
    one("SPY", vt))
add("regime_vt", "状态 + 波动目标", "两者取较小值：状态分决定上限，波动率再压一层。",
    one("SPY", np.minimum(expo_regime, vt)))

# ---- 智能杠杆：趋势向上 + 波动低时才放大（最多 1.5 倍），趋势向下拿现金
for base, tv, nm in [("SPY", 0.15, "标普"), ("QQQ", 0.20, "纳指")]:
    rvb = R[base].rolling(20).std() * np.sqrt(252)
    trend_b = (px[base] > sma(px[base], 200)).astype(float)
    add("smart_" + base, f"{nm}智能杠杆（≤1.5x）", f"{base} 在 200 日线上时，仓位 = {int(tv*100)}% ÷ 20 日波动，最高 1.5 倍；跌破 200 日线 → 现金。借钱成本 = 现金利率 + 1%。",
        one(base, trend_b * (tv / rvb).clip(upper=1.5)), group="智能杠杆")

# ---- 2 倍杠杆（模拟 2x QQQ / 2x SPY 日度再平衡，含 0.95% 费率 + 融资成本）
fee = 0.0095 / 252
for base, nm in [("QQQ", "2x 纳指"), ("SPY", "2x 标普")]:
    lev = 2 * R[base] - cash - fee
    R["L2" + base] = lev
    add("l2bh_" + base, f"{nm} 买入持有", f"模拟 2 倍日度杠杆 {base}（类似 QLD/SSO），一直持有。", one("L2" + base, pd.Series(1.0, index=R.index)), group="杠杆 ETF")
    add("l2ma_" + base, f"{nm} + 200 日线", f"{base} 在 200 日线上才持有 2 倍杠杆，否则现金。",
        one("L2" + base, (px[base] > sma(px[base], 200)).astype(float)), group="杠杆 ETF")
    add("l2rg_" + base, f"{nm} + 状态 + 波动", f"状态分 ≥75 且 {base} 20 日波动 <25% → 100% 杠杆；状态 ≥45 → 50%；否则现金。",
        one("L2" + base, ((score.reindex(R.index).ffill() >= 75) & (R[base].rolling(20).std() * np.sqrt(252) < 0.25)).astype(float)
            .where(lambda x: x > 0, (score.reindex(R.index).ffill() >= 45).astype(float) * 0.5)), group="杠杆 ETF")

# ---- 板块动量轮动（双动量）
mm = monthly_mask(R.index)
mom_sec = px[SECTORS].pct_change(126) * 0.5 + px[SECTORS].pct_change(252) * 0.5
cash12 = (1 + cash).rolling(252).apply(np.prod, raw=True) - 1


def rotation(top=3, absolute=True, filt=None):
    W = pd.DataFrame(np.nan, index=R.index, columns=SECTORS + ["IEF"])
    for d in R.index[mm]:
        m = mom_sec.loc[d].dropna()
        if len(m) < 5:
            continue
        picks = m.sort_values(ascending=False).index[:top]
        row = pd.Series(0.0, index=W.columns)
        for p in picks:
            ok = (m[p] > cash12.loc[d]) if absolute else True
            if filt is not None and not filt.loc[d]:
                ok = False
            if ok:
                row[p] += 1 / top
            else:
                row["IEF"] += 1 / top
        W.loc[d] = row
    return W.ffill().fillna(0)


add("rot3", "板块动量轮动 Top3", "每月底选 6+12 月动量最强的 3 个板块 ETF 等权持有；动量不如现金的那份改放 IEF 国债。Antonacci 双动量。",
    rotation(3), group="轮动")
add("rot3_rg", "板块轮动 + 状态过滤", "同上，但市场状态 <45 分（防守）时全部改放 IEF。",
    rotation(3, filt=(score.reindex(R.index).ffill() >= 45)), group="轮动")
# 股债金三资产风险平价 + 趋势
assets = ["SPY", "TLT", "GLD", "EFA", "DBC"]
W = pd.DataFrame(np.nan, index=R.index, columns=assets)
vol60 = R[assets].rolling(60).std()
for d in R.index[mm]:
    v = vol60.loc[d]
    if v.isna().any():
        continue
    iv = (1 / v)
    iv = iv / iv.sum()
    trend = px.loc[:d, assets].iloc[-1] > sma(px[assets], 200).loc[d]
    W.loc[d] = iv * trend.astype(float)
add("aa_trend", "多资产风险平价 + 趋势", "SPY/TLT/GLD/EFA/DBC 按波动倒数配权，每类资产在 200 日线下就换现金。分散 + 趋势跟随。",
    W.ffill().fillna(0), group="轮动")

# ---- 组合方案（每日按固定比例混合各策略收益）
def blend(key, name, desc, parts):
    r = sum(strategies[k]["r"] * w for k, w in parts.items())
    e = sum(strategies[k]["expo"] * w for k, w in parts.items())
    t = sum(strategies[k]["turn"] * w for k, w in parts.items())
    strategies[key] = dict(name=name, desc=desc, group="组合方案", r=r, expo=e, turn=t)


blend("combo_core", "稳健组合", "50% 板块轮动+状态过滤 / 50% 波动目标 SPY。不加杠杆。",
      {"rot3_rg": 0.5, "voltarget": 0.5})
blend("combo_growth", "进取组合", "40% 板块轮动+状态过滤 / 30% 2x 纳指+200 日线 / 30% 波动目标 SPY。",
      {"rot3_rg": 0.4, "l2ma_QQQ": 0.3, "voltarget": 0.3})

# ---------------------------------------------------------------- 稳健性：参数敏感 + 分段
robust = {}
for n in [100, 150, 200, 250]:
    r, e, t = run(one("SPY", (spy > sma(spy, n)).astype(float)), R)
    robust[f"MA{n}"] = stats(r[r.index >= START], e, t)[0]
for thr in [(70, 40), (75, 45), (80, 50)]:
    ex = score.reindex(R.index).ffill().apply(lambda x: 1.0 if x >= thr[0] else (0.6 if x >= thr[1] else 0.2) if pd.notna(x) else 1.0)
    r, e, t = run(one("SPY", ex), R)
    robust[f"状态阈值 {thr[0]}/{thr[1]}"] = stats(r[r.index >= START], e, t)[0]
for tv in [0.10, 0.15, 0.20]:
    r, e, t = run(one("SPY", (tv / rv).clip(upper=1.0)), R)
    robust[f"目标波动 {int(tv*100)}%"] = stats(r[r.index >= START], e, t)[0]

periods = {"2003–2014": ("2003-01-01", "2014-12-31"), "2015–2026": ("2015-01-01", "2026-12-31"),
           "2008 金融危机": ("2007-10-01", "2009-03-31"), "2020 疫情": ("2020-02-01", "2020-04-30"), "2022 熊市": ("2022-01-01", "2022-12-31")}
by_period = {}
for k, s in strategies.items():
    by_period[k] = {}
    for p, (a, b) in periods.items():
        rr = s["r"][(s["r"].index >= a) & (s["r"].index <= b)]
        by_period[k][p] = float((1 + rr).prod() - 1) if len(rr) else None

# ---------------------------------------------------------------- 状态模型的预测力
fwd = {}
spy_r = R["SPY"]
for h in [21, 63]:
    f = (1 + spy_r).rolling(h).apply(np.prod, raw=True).shift(-h) - 1
    fwd[h] = f
sc = score[score.index >= START]
buckets = pd.cut(sc, [-1, 25, 45, 60, 75, 101], labels=["0–25", "25–45", "45–60", "60–75", "75–100"])
fv = (spy_r.rolling(21).std().shift(-21) * np.sqrt(252))
dd_fwd = pd.Series(index=sc.index, dtype=float)
eqspy = (1 + spy_r).cumprod()
fmin = eqspy[::-1].rolling(63, min_periods=1).min()[::-1].shift(-1)
dd_fwd = (fmin / eqspy - 1).reindex(sc.index)
pred = []
for b in buckets.cat.categories:
    m = buckets == b
    pred.append(dict(bucket=str(b), days=int(m.sum()), share=float(m.mean()),
                     f21=float(fwd[21].reindex(sc.index)[m].mean()), f63=float(fwd[63].reindex(sc.index)[m].mean()),
                     win63=float((fwd[63].reindex(sc.index)[m] > 0).mean()),
                     vol21=float(fv.reindex(sc.index)[m].mean()),
                     dd63=float(dd_fwd[m].mean()), crash63=float((dd_fwd[m] < -0.10).mean())))

# ---------------------------------------------------------------- 个股动量（5 年缓存，有幸存者偏差）
stock_res = None
files = glob.glob(os.path.join(CACHE, "*.json"))
closes = {}
uni = {u["name"]: u for u in json.load(open(os.path.join(DATA, "universe.json"), encoding="utf-8"))}
for f in files:
    sym = os.path.basename(f)[:-5]
    if sym in ("SPY", "QQQ"):
        continue
    d = json.load(open(f))
    s = pd.Series(d["c"], index=pd.to_datetime(d["d"]), dtype=float)
    closes[sym] = s[~s.index.duplicated()]
C = pd.DataFrame(closes).sort_index()
C = C[C.index >= "2021-11-01"]
SR = C.pct_change(fill_method=None).clip(-0.6, 1.5)
mom = C.shift(21) / C.shift(252) - 1             # 12-1 月动量
vol_s = SR.rolling(126).std() * np.sqrt(252)
above200 = C > C.rolling(200).mean()
above50 = C > C.rolling(50).mean()
near_high = C / C.rolling(252).max()
breadth200 = above200.where(C.rolling(200).mean().notna()).mean(axis=1)
breadth50 = above50.where(C.rolling(50).mean().notna()).mean(axis=1)
mmS = monthly_mask(C.index)


def stock_strategy(n=20, kind="mom", regime_filter=False):
    W = pd.DataFrame(np.nan, index=C.index, columns=C.columns)
    for d in C.index[mmS]:
        m = mom.loc[d].dropna()
        if len(m) < 200:
            continue
        if kind == "mom":
            rank = m
        elif kind == "radj":             # 动量 ÷ 波动（Barroso & Santa-Clara 思路），且必须在 200 日线上
            rank = (m / vol_s.loc[d].reindex(m.index)).dropna()
            rank = rank[above200.loc[d].reindex(rank.index).fillna(False)]
        elif kind == "mom_lowvol":       # 动量 + 低波动 + 接近新高 综合
            z = lambda s: (s - s.mean()) / s.std()
            v = vol_s.loc[d].reindex(m.index)
            h = near_high.loc[d].reindex(m.index)
            rank = (z(m.rank()) + z(-v.rank()) * 0.5 + z(h.rank()) * 0.5).dropna()
            ok = above200.loc[d].reindex(rank.index).fillna(False)
            rank = rank[ok]
        picks = rank.sort_values(ascending=False).index[:n]
        row = pd.Series(0.0, index=W.columns)
        expo = 1.0
        if regime_filter:
            s_ = score.reindex([d], method="ffill").iloc[0]
            expo = 1.0 if s_ >= 75 else (0.6 if s_ >= 45 else 0.2)
        row[picks] = expo / n
        W.loc[d] = row
    W = W.ffill().fillna(0)
    rr = SR.copy()
    r, e, t = run(W, rr, cost=0.001, cash_r=cash.reindex(C.index).fillna(0))
    return r, e, t


stock_runs = {}
spy5 = R["SPY"].reindex(C.index)
start5 = C.index[260]
for key, nm, kw in [("s_mom", "12-1 月动量 Top20", dict(kind="mom")),
                    ("s_mom50", "12-1 月动量 Top50", dict(kind="mom", n=50)),
                    ("s_radj", "风险调整动量 Top20", dict(kind="radj")),
                    ("s_radj_rg", "风险调整动量 + 状态仓位", dict(kind="radj", regime_filter=True)),
                    ("s_combo", "动量+低波+近新高 Top20", dict(kind="mom_lowvol")),
                    ("s_combo_rg", "动量组合 + 状态仓位", dict(kind="mom_lowvol", regime_filter=True))]:
    r, e, t = stock_strategy(**kw)
    stock_runs[key] = dict(name=nm, r=r[r.index >= start5], expo=e, turn=t)
stock_runs["s_spy"] = dict(name="SPY 同期", r=spy5[spy5.index >= start5].fillna(0), expo=None, turn=None)
eqw = SR.where(above200.shift(0).notna()).mean(axis=1)
stock_runs["s_eq"] = dict(name="全股票池等权（幸存者偏差基准）", r=eqw[eqw.index >= start5].fillna(0), expo=None, turn=None)

# ---------------------------------------------------------------- 当前读数
last = score.index[-1]
now = dict(date=str(last.date()), score=float(score.iloc[-1]), regime=regime_of(score.iloc[-1]),
           signals={c: (None if pd.isna(valid[c].iloc[-1]) else bool(valid[c].iloc[-1])) for c in valid.columns},
           spy=float(spy.iloc[-1]), spy_ma200=float(sma(spy, 200).iloc[-1]), spy_ma50=float(sma(spy, 50).iloc[-1]),
           vix=float(vix.iloc[-1]), vix_ts=float(ts.iloc[-1]), rv20=float(rv.iloc[-1]),
           sector_above=float(sec_above.iloc[-1]),
           breadth200=float(breadth200.iloc[-1]), breadth50=float(breadth50.iloc[-1]), breadth_date=str(C.index[-1].date()),
           expo_regime=float(expo_regime.iloc[-1]), expo_vt=float(vt.iloc[-1]),
           qqq_rv20=float(R["QQQ"].rolling(20).std().iloc[-1] * np.sqrt(252)),
           qqq_above200=bool(px["QQQ"].iloc[-1] > sma(px["QQQ"], 200).iloc[-1]))
sec_now = mom_sec.iloc[-1].sort_values(ascending=False)
now["sectors"] = [dict(t=t, mom=float(v), r1m=float(px[t].pct_change(21).iloc[-1]), above200=bool(px[t].iloc[-1] > sma(px[t], 200).iloc[-1])) for t, v in sec_now.items()]
now["rot_picks"] = [t for t in sec_now.index[:3]]
# 当前个股排名：风险调整动量（回测里最好的个股方法），必须在 200 日线上；排除 6 月波动 <20% 的（多为被收购锁价）
d = C.index[-1]
m = mom.loc[d].dropna()
v = vol_s.loc[d].reindex(m.index)
h = near_high.loc[d].reindex(m.index)
rank = (m / v).dropna()
rank = rank[above200.loc[d].reindex(rank.index).fillna(False) & (v.reindex(rank.index) > 0.20)].sort_values(ascending=False)
now["stocks"] = [dict(t=t, score=float(rank[t]), mom=float(m[t]), vol=float(v[t]), near_high=float(h[t]),
                      r1m=float(C[t].iloc[-1] / C[t].iloc[-22] - 1),
                      sector=uni.get(t, {}).get("sector", ""), industry=uni.get(t, {}).get("industry", ""))
                 for t in rank.index[:30]]

# 历史分数序列（给图用，周采样）
hist = score.rolling(10).mean()[score.index >= "2005-01-01"].resample("W-FRI").last()   # 10 日平滑
spy_w = spy.reindex(hist.index, method="ffill")
breadth_w = breadth200.resample("W-FRI").last().dropna()

# ---------------------------------------------------------------- 输出
out = dict(now=now, pred=pred, robust=robust, periods=list(periods.keys()), by_period=by_period,
           strategies={}, stocks={}, score_hist=dict(d=[str(x.date()) for x in hist.index], s=[round(float(x), 1) for x in hist.values],
                                                    spy=[round(float(x), 2) for x in spy_w.values]),
           breadth_hist=dict(d=[str(x.date()) for x in breadth_w.index], b=[round(float(x) * 100, 1) for x in breadth_w.values]),
           start=START, end=str(R.index[-1].date()))
for k, s in strategies.items():
    st, eq, dd, yearly = stats(s["r"], s["expo"], s["turn"])
    eqw_ = eq.resample("W-FRI").last()
    out["strategies"][k] = dict(name=s["name"], desc=s["desc"], group=s["group"], stats=st,
                                eq=[round(float(x), 4) for x in eqw_.values], d=[str(x.date()) for x in eqw_.index],
                                dd=[round(float(x), 4) for x in dd.resample("W-FRI").min().values],
                                yearly={str(y): float(v) for y, v in yearly.items()})
for k, s in stock_runs.items():
    st, eq, dd, yearly = stats(s["r"], s["expo"], s["turn"])
    eqw_ = eq.resample("W-FRI").last()
    out["stocks"][k] = dict(name=s["name"], stats=st, eq=[round(float(x), 4) for x in eqw_.values],
                            d=[str(x.date()) for x in eqw_.index], yearly={str(y): float(v) for y, v in yearly.items()})
json.dump(out, open(os.path.join(DATA, "results.json"), "w", encoding="utf-8"), ensure_ascii=False)

# 控制台摘要
print("当前", now["date"], "状态分", round(now["score"]), now["regime"])
for k, v in now["signals"].items():
    print("  ", "✓" if v else "✗", k)
print(f"{'策略':<24}{'年化':>8}{'波动':>8}{'夏普':>7}{'最大回撤':>9}{'最差年':>8}{'平均仓位':>8}")
for k, s in out["strategies"].items():
    t = s["stats"]
    print(f"{s['name']:<24}{t['cagr']:>8.1%}{t['vol']:>8.1%}{t['sharpe']:>7.2f}{t['mdd']:>9.1%}{t['worst_year']:>8.1%}{t.get('avg_expo', 1):>8.0%}")
print("--- 个股（", str(start5.date()), "起）")
print("stock_n", len(C.columns))
for k, s in out["stocks"].items():
    t = s["stats"]
    print(f"{s['name']:<24}{t['cagr']:>8.1%}{t['vol']:>8.1%}{t['sharpe']:>7.2f}{t['mdd']:>9.1%}")
print("--- 预测力")
for p in pred:
    print(p)
print("--- 稳健性")
for k, v in robust.items():
    print(f"{k:<16}{v['cagr']:>8.1%}{v['sharpe']:>7.2f}{v['mdd']:>9.1%}")
print("板块", now["rot_picks"], "宽度200", round(now["breadth200"] * 100), "%")
