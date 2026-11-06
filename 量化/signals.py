"""进出场规则回测 + 今天的买卖信号。

问题：量化怎么帮我 选股 / 买 / 卖 / 什么时候拿现金，提高胜率？
做法：
  选股  = 每周五按「风险调整动量」排名，前 100 名进入候选（只看 200 日线上、6 月波动 >20%）
  进场  = 4 种触发（进名单就买 / 回踩 20 日线 / 52 周新高放量 / 收窄后突破），信号日收盘判断，次日开盘买
  出场  = 5 种规则，全部带初始止损 = 买价 − 2×ATR（定义 1R）
  拿现金 = 按进场当天的市场状态分 / 个股宽度分组，看胜率差多少
对照组：同样的进场触发，但不经过动量筛选（只要求 收盘 > 50 日线 > 200 日线）。
输出 signals.json，build_report.py 读它。
"""
import json, os, glob
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "stocks")
MAXH = 250

# ---------------------------------------------------------------- 数据
raw = {}
for f in glob.glob(os.path.join(CACHE, "*.json")):
    sym = os.path.basename(f)[:-5]
    if sym in ("SPY", "QQQ"):
        continue
    d = json.load(open(f))
    idx = pd.to_datetime(d["d"])
    df = pd.DataFrame({k: d[k] for k in "ohlcv"}, index=idx, dtype=float)
    raw[sym] = df[~df.index.duplicated()]
syms = sorted(raw)
dates = sorted(set().union(*[r.index for r in raw.values()]))
dates = pd.DatetimeIndex(dates)
dates = dates[dates.dayofweek < 5]
P = {k: pd.DataFrame({s: raw[s][k] for s in syms}).reindex(dates) for k in "ohlcv"}
O, H, L, C, V = (P[k] for k in "ohlcv")
# 数据清洗：开盘缺失用收盘
O = O.fillna(C)
T, N = C.shape

ma = lambda n: C.rolling(n, min_periods=n).mean()
MA10, MA20, MA50, MA200 = ma(10), ma(20), ma(50), ma(200)
prevC = C.shift(1)
TR = pd.concat([(H - L), (H - prevC).abs(), (L - prevC).abs()]).groupby(level=0).max().reindex(dates)
ATR = TR.rolling(14).mean()
HI252 = H.rolling(252, min_periods=200).max().shift(1)
AV50 = V.rolling(50).mean()
RNG10 = (H.rolling(10).max() - L.rolling(10).min()) / C
HI10 = H.rolling(10).max().shift(1)
ret = C.pct_change(fill_method=None)
VOL126 = ret.rolling(126).std() * np.sqrt(252)
MOM = C.shift(21) / C.shift(252) - 1
RADJ = MOM / VOL126
uptrend = (C > MA200) & (VOL126 > 0.20)
RANK = RADJ.where(uptrend).rank(axis=1, ascending=False)

# 每周五排名 → 下周的候选名单（Top100）
fri = pd.Series(dates.dayofweek == 4, index=dates)
ELIG = (RANK.loc[fri.values].fillna(9999).reindex(dates).ffill() <= 100)
CTRL = (C > MA50) & (MA50 > MA200)                      # 对照：普通上升趋势股

score = pd.read_pickle(os.path.join(DATA, "score.pkl")).reindex(dates).ffill()
breadth = (C > MA200).where(MA200.notna()).mean(axis=1)
spy = pd.read_pickle(os.path.join(DATA, "macro.pkl"))["SPY"].reindex(dates).ffill()

# ---------------------------------------------------------------- 进场触发（信号日 i 收盘）
pull = (L <= MA20 * 1.01) & (C > MA20) & (C > MA50) & ((C.rolling(10).max() / MA20) > 1.05)
brk = (C > HI252) & (V > 1.5 * AV50)
vcp = (RNG10.shift(1) < 0.10) & (C > HI10) & (C > MA50)
newin = ELIG & ~ELIG.shift(1, fill_value=False)
ENTRIES = {
    "E1": ("进名单就买", "股票刚进入动量 Top100，下一个交易日开盘买。", None),
    "E2": ("回踩 20 日线", "在名单内，股价从高于 20 日线 5% 以上回落，盘中碰到 20 日线、收盘守住。", pull),
    "E3": ("52 周新高 + 放量", "在名单内，收盘创 52 周新高，成交量 >1.5 倍 50 日均量。", brk),
    "E4": ("收窄后突破", "在名单内，前 10 天振幅 <10%（收窄），今天收盘突破 10 日高点。", vcp),
}
EXITS = {
    "X1": ("跌破 20 日线", "收盘跌破 20 日线，次日开盘卖。"),
    "X2": ("跌破 50 日线", "收盘跌破 50 日线，次日开盘卖。"),
    "X3": ("3×ATR 移动止损", "从持有期最高收盘价回落 3 倍 ATR 就卖（吊灯止损）。"),
    "X4": ("+3R 卖一半，余下破 20 日线", "涨到 +3R 先卖一半锁利润，剩下一半跌破 20 日线再卖。"),
    "X5": ("固定持有 20 天", "对照组：不管涨跌，持有 20 个交易日。"),
}

Oa, Ha, La, Ca = O.values, H.values, L.values, C.values
M20, M50, ATRa = MA20.values, MA50.values, ATR.values
spya = spy.values


def first(mask):
    k = np.argmax(mask)
    return k if mask.size and mask[k] else None


def simulate(e, j, xk):
    """e: 信号日行号, j: 股票列。返回 (出场行号, 收益%, R 倍数) 或 None。"""
    b = e + 1
    if b >= T:
        return None
    buy = Oa[b, j]
    atr = ATRa[e, j]
    if not np.isfinite(buy) or not np.isfinite(atr) or atr <= 0 or buy <= 0:
        return None
    stop = buy - 2 * atr
    R = buy - stop
    end = min(T, b + MAXH)
    lo, hi, cl, op = La[b:end, j], Ha[b:end, j], Ca[b:end, j], Oa[b:end, j]
    if np.isnan(cl).all():
        return None
    # 初始止损
    ks = first(lo <= stop)
    cand = []
    if ks is not None:
        cand.append((ks, min(op[ks], stop) if ks > 0 else stop))
    def close_rule(mask):
        k = first(mask)
        if k is not None and k + 1 < len(cl):
            cand.append((k + 1, op[k + 1]))
    half = None
    if xk == "X1":
        close_rule(cl < M20[b:end, j])
    elif xk == "X2":
        close_rule(cl < M50[b:end, j])
    elif xk == "X3":
        trail = np.fmax.accumulate(np.nan_to_num(cl, nan=-1)) - 3 * ATRa[b:end, j]
        close_rule(cl < trail)
    elif xk == "X4":
        close_rule(cl < M20[b:end, j])
        kh = first(hi >= buy + 3 * R)
        if kh is not None:
            half = kh
    elif xk == "X5":
        if 20 < len(cl):
            cand.append((20, op[20]))
    if cand:
        k, px_ = min(cand, key=lambda x: x[0])
    else:
        k, px_ = len(cl) - 1, cl[-1]          # 还没出场：按最后收盘价算（标记为持有中）
    if not np.isfinite(px_):
        return None
    r = px_ / buy - 1
    if xk == "X4" and half is not None and half <= k:
        r = 0.5 * (3 * R / buy) + 0.5 * r
    s_ret = spya[min(b + k, T - 1)] / spya[b] - 1 if np.isfinite(spya[b]) else 0
    return b + k, r, r * buy / R, k, r - s_ret, not cand


trades = []
for j, s in enumerate(syms):
    elig_j = ELIG[s].values
    ctrl_j = CTRL[s].values
    for ek, (en, ed, trig) in ENTRIES.items():
        for univ, mask_u in (("动量名单", elig_j), ("普通上升股", ctrl_j)):
            if ek == "E1":
                if univ != "动量名单":
                    continue
                sig = newin[s].values
            else:
                sig = trig[s].values & mask_u
            ev = np.flatnonzero(sig)
            ev = ev[ev >= 260]
            if ev.size == 0:
                continue
            for xk in EXITS:
                nxt = -1
                for e in ev:
                    if e <= nxt:
                        continue
                    out = simulate(e, j, xk)
                    if out is None:
                        continue
                    ex, r, rr, hold, exc, openpos = out
                    nxt = ex
                    trades.append((ek, xk, univ, s, e, r, rr, hold, exc, openpos))

tr = pd.DataFrame(trades, columns=["entry", "exit", "univ", "sym", "e", "ret", "R", "hold", "excess", "open"])
tr["date"] = dates[tr["e"].values]
tr["score"] = score.values[tr["e"].values]
tr["breadth"] = breadth.values[tr["e"].values]
tr["regime"] = pd.cut(tr["score"], [-1, 45, 75, 101], labels=["防守 <45", "中性 45–75", "进攻 ≥75"])
tr["bgrp"] = pd.cut(tr["breadth"], [-1, 0.4, 0.6, 1.01], labels=["宽度 <40%", "宽度 40–60%", "宽度 >60%"])
tr["rr_clip"] = tr["R"].clip(-3, 20)          # 防止极端值主导平均
# 进场当天的特征 → 找哪些条件提高胜率
jj = tr["sym"].map({s: i for i, s in enumerate(syms)}).values
ee = tr["e"].values
tr["ext50"] = Ca[ee, jj] / M50[ee, jj] - 1
tr["rank"] = RANK.values[ee, jj]
spy50 = (spy > spy.rolling(50).mean()).values
spy200 = (spy > spy.rolling(200).mean()).values
tr["spy50"] = spy50[ee]; tr["spy200"] = spy200[ee]
rngpos = ((C - L) / (H - L)).values
tr["clpos"] = rngpos[ee, jj]
vr = (V / AV50).values
tr["vratio"] = vr[ee, jj]


def summ(x):
    if len(x) == 0:
        return None
    w = x["ret"] > 0
    gains, losses = x.loc[w, "ret"].sum(), -x.loc[~w, "ret"].sum()
    return dict(n=int(len(x)), win=float(w.mean()), avg=float(x["ret"].mean()), med=float(x["ret"].median()),
                avgR=float(x["rr_clip"].mean()), avg_win=float(x.loc[w, "ret"].mean()) if w.any() else 0,
                avg_loss=float(x.loc[~w, "ret"].mean()) if (~w).any() else 0,
                pf=float(gains / losses) if losses > 0 else None, hold=float(x["hold"].mean()),
                excess=float(x["excess"].mean()), beat=float((x["excess"] > 0).mean()))


grid = {}
for (ek, xk, u), x in tr.groupby(["entry", "exit", "univ"]):
    grid[f"{ek}|{xk}|{u}"] = summ(x)
reg_tab = {}
for (ek, xk, rg), x in tr[tr["univ"] == "动量名单"].groupby(["entry", "exit", "regime"], observed=True):
    reg_tab[f"{ek}|{xk}|{rg}"] = summ(x)
br_tab = {}
for (ek, xk, bg), x in tr[tr["univ"] == "动量名单"].groupby(["entry", "exit", "bgrp"], observed=True):
    br_tab[f"{ek}|{xk}|{bg}"] = summ(x)
# 全部动量名单交易合计按状态（看「什么时候拿现金」）
allm = tr[(tr["univ"] == "动量名单") & (tr["exit"].isin(["X1", "X2", "X3", "X4"]))]
reg_all = {str(k): summ(x) for k, x in allm.groupby("regime", observed=True)}
br_all = {str(k): summ(x) for k, x in allm.groupby("bgrp", observed=True)}
# 状态 + 宽度 双过滤
both = allm[(allm["score"] >= 45) & (allm["breadth"] >= 0.4)]
gate = dict(all=summ(allm), gated=summ(both), cut=summ(allm.drop(both.index)))
yr_tab = {f"{k}": summ(x) for k, x in allm.groupby(allm["date"].dt.year)}

# 哪些条件提高胜率（动量名单，X2 跌破 50 日线出场，E1-E4 合并）
base = tr[(tr["univ"] == "动量名单") & (tr["exit"] == "X2")]
FILTERS = [
    ("全部（不加条件）", base.index == base.index),
    ("SPY 在 50 日线上", base["spy50"]), ("SPY 在 50 日线下", ~base["spy50"]),
    ("SPY 在 200 日线上", base["spy200"]), ("SPY 在 200 日线下", ~base["spy200"]),
    ("离 50 日线 <10%（不追高）", base["ext50"] < 0.10), ("离 50 日线 10–25%", base["ext50"].between(0.10, 0.25)),
    ("离 50 日线 >25%（追高）", base["ext50"] > 0.25),
    ("动量排名 1–20", base["rank"] <= 20), ("动量排名 21–100", base["rank"] > 20),
    ("收在当天振幅上 1/3", base["clpos"] > 0.67), ("收在当天振幅下 1/3", base["clpos"] < 0.33),
    ("成交量 >1.5 倍均量", base["vratio"] > 1.5), ("成交量 <1 倍均量", base["vratio"] < 1),
    ("市场宽度 <40%", base["breadth"] < 0.4), ("市场宽度 >60%", base["breadth"] > 0.6),
    ("组合：不追高 + 收在上 1/3", (base["ext50"] < 0.10) & (base["clpos"] > 0.67)),
    ("组合：不追高 + 排名前 20", (base["ext50"] < 0.10) & (base["rank"] <= 20)),
]
filt = [dict(name=n, **summ(base[np.asarray(m, dtype=bool)])) for n, m in FILTERS]

# ---------------------------------------------------------------- 今天的信号
last = T - 1
sc_now = float(score.iloc[-1]); br_now = float(breadth.iloc[-1])
gate_now = "进攻" if sc_now >= 75 and br_now >= 0.5 else ("谨慎" if sc_now >= 45 and br_now >= 0.4 else "现金")


def stock_view(s, why=""):
    j = syms.index(s)
    c, m20, m50, m200, atr = Ca[last, j], M20[last, j], M50[last, j], MA200[s].iloc[-1], ATRa[last, j]
    if not np.isfinite(c):
        return None
    hi_close = np.nanmax(Ca[max(0, last - 60):last + 1, j])
    chand = hi_close - 3 * atr
    ext = c / m20 - 1
    setup = []
    if pull[s].iloc[-1]: setup.append("回踩 20 日线 ✓")
    if brk[s].iloc[-1]: setup.append("52 周新高放量 ✓")
    if vcp[s].iloc[-1]: setup.append("收窄突破 ✓")
    if RNG10[s].iloc[-1] < 0.10 and c > m50: setup.append(f"正在收窄，突破价 {H[s].iloc[-10:].max():.2f}")
    if not setup:
        setup.append(f"离 20 日线 {ext:+.0%}，等回踩" if ext > 0.08 else ("在 20 日线附近，等转强" if ext > -0.02 else "在 20 日线下，不买"))
    # 出场状态（给持有者）
    if c < m50 or c < chand:
        exit_s, lvl = "卖出", 3
    elif c < m20:
        exit_s, lvl = "减仓/收紧", 2
    else:
        exit_s, lvl = "持有", 1
    rk = RANK[s].iloc[-1]
    def last_break(ma_arr):
        below = Ca[:, j] < ma_arr
        k = last
        if not below[k]:
            return None
        while k > 0 and below[k - 1]:
            k -= 1
        return dict(date=str(dates[k].date()), px=float(Ca[k, j]), chg=float(c / Ca[k, j] - 1))
    br20, br50 = last_break(M20[:, j]), last_break(M50[:, j])
    return dict(t=s, why=why, close=float(c), ma20=float(m20), ma50=float(m50), ma200=float(m200), atr=float(atr),
                stop=float(c - 2 * atr), chand=float(chand), ext=float(ext), rank=None if np.isnan(rk) else int(rk),
                above200=bool(c > m200), setup=setup, exit=exit_s, lvl=lvl, br20=br20, br50=br50,
                r1m=float(c / Ca[last - 21, j] - 1), mom=float(MOM[s].iloc[-1]) if np.isfinite(MOM[s].iloc[-1]) else None)


top = RANK.iloc[-1].dropna().sort_values().index[:40]
cands = [v for v in (stock_view(s, "动量名单") for s in top) if v]
# 用户持仓（杠杆 ETF → 正股）
hold_syms = []
try:
    snap = os.environ.get("QUANT_HOLDINGS")          # 私人持仓：只在本机设置，公开网站不显示
    if not snap:
        raise RuntimeError("公开版不读持仓")
    cfg = json.load(open(os.path.join(snap, "config.json")))
    lev = cfg.get("leveraged_etfs", {}); alias = cfg.get("symbol_alias", {})
    latest = {}
    for f in glob.glob(os.path.join(snap, "snapshots", "*.json")):
        acct, d = os.path.basename(f)[:-5].rsplit("_", 1)
        if d >= latest.get(acct, ("",))[0]:
            latest[acct] = (d, f)
    for acct, (d, f) in latest.items():
        for p in json.load(open(f)).get("positions", []):
            sy = p.get("symbol", "")
            if not sy or len(sy) > 6 or not (p.get("qty") or 0):
                continue
            sy = alias.get(sy, sy)
            u = lev.get(sy, {}).get("underlying", sy)
            hold_syms.append((u, sy if sy != u else ""))
except Exception as ex:
    print("持仓：", ex)
seen = set(); holds = []
for u, via in hold_syms:
    if u in seen or u not in syms:
        continue
    seen.add(u)
    v = stock_view(u, f"经 {via}" if via else "")
    if v:
        v["via"] = [b for a, b in hold_syms if a == u and b]
        holds.append(v)
holds.sort(key=lambda x: -x["lvl"])

out = dict(entries={k: v[:2] for k, v in ENTRIES.items()}, exits=EXITS, grid=grid, reg=reg_tab, br=br_tab,
           reg_all=reg_all, br_all=br_all, gate=gate, years=yr_tab, filters=filt,
           period=[str(dates[260].date()), str(dates[-1].date())], n_trades=int(len(tr)),
           now=dict(date=str(dates[-1].date()), score=sc_now, breadth=br_now, gate=gate_now,
                    cands=cands, holds=holds))
json.dump(out, open(os.path.join(DATA, "signals.json"), "w", encoding="utf-8"), ensure_ascii=False)

# ---------------------------------------------------------------- 控制台
print("期间", out["period"], "交易数", len(tr))
print(f"{'组合':<30}{'笔数':>6}{'胜率':>7}{'平均':>8}{'中位':>8}{'均R':>6}{'PF':>6}{'天数':>6}{'超SPY':>8}")
for k, v in sorted(grid.items()):
    if v: print(f"{k:<30}{v['n']:>6}{v['win']:>7.0%}{v['avg']:>8.1%}{v['med']:>8.1%}{v['avgR']:>6.2f}{(v['pf'] or 0):>6.2f}{v['hold']:>6.0f}{v['excess']:>8.1%}")
print("--- 按状态（动量名单，X1-X4）")
for k, v in reg_all.items(): print(k, v)
print("--- 按宽度")
for k, v in br_all.items(): print(k, v)
print("--- 门槛", {k: (v['n'], round(v['win'], 3), round(v['avg'], 4)) for k, v in gate.items() if v})
print("--- 年份", {k: (v['n'], round(v['win'], 2), round(v['avg'], 3)) for k, v in yr_tab.items()})
for f_ in filt: print(f"{f_['name']:<22}{f_['n']:>6}{f_['win']:>7.0%}{f_['avg']:>8.1%}{f_['avgR']:>6.2f}{(f_['pf'] or 0):>6.2f}")
print("今天", gate_now, sc_now, br_now)
for h in holds: print(h["t"], h["via"], h["exit"], h["br20"], h["br50"])
