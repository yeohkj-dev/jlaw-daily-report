"""量价信号的「进场 / 止损 / 离场」规则回测（逐笔交易模拟）。
样本：../cache 约 2,250 只美股日线，流动性过滤与 backtest.py 相同（价 ≥ 5、20 日均成交额 ≥ 500 万）。

三种进场（都在信号日的下一天开盘买；开盘已低于止损价就放弃）：
  A 低位放量长下影：止损 = 长下影最低点 ×0.995
  B 放量突破 50 日高点（量 ≥ 2 倍），且 股票升势 + SPY 在 200MA 上；止损 = 突破K线最低点 ×0.995
    B0 = 不加过滤的放量突破（对照）；Bx = B 但开盘离突破点 > 5% 就不追
  C 突破后缩量回踩：B 发生后 3–25 天内，回踩到 20MA（最低价 ≤ 20MA×1.01）、回踩期间平均量 < 20 日均量，
    然后一根阳线收在 20MA 之上 → 下一天开盘买；止损 = 回踩最低点 ×0.995
    C0 = 普通回踩 20MA 反弹（不要求前面有突破、不要求缩量，对照）

离场方式（同一批进场，各跑一遍；参数见下面的 EX 字典）：
  E1/E15 不设止损拿 20/60 天；E2/E3 紧止损（盘中）20/60 天；E9/E10 收盘止损 20/60 天；
  E11/E12 宽止损（再往下 1 ATR）20/60 天；E20 宽收盘止损 60 天；E19 收盘跌 15% 才卖、60 天；
  E4/E5 紧止损 + 20MA 跟踪（E5 加 2R 卖 1/3）；E13/E14 收盘止损 + 先站上 20MA 再跟踪（E14 加 2R 卖 1/3）；
  E16/E17/E18 = E10 + 放量破 50MA 全卖 / 弱市射击之星卖一半 / 滞涨提高止损
止损成交：当天开盘已低于止损 → 按开盘价；否则按止损价。
同一只股票同一种进场，持仓期间不重复进场（按 E10 的持仓期判断）；止损距离 < 1% 或 > 25% 的不做。
输出 exit_bt.json + exit_trades.pkl。
"""
import glob, json, os, sys
from multiprocessing import Pool
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = os.environ.get("BT_TAG", "")   # "20" = 用 cache20（2005 起 20 年数据），输出文件名加 20
CACHE = os.path.join(HERE, "..", "cache" + TAG)
EXITS = ["E1", "E2", "E3", "E4", "E5", "E9", "E10", "E11", "E12", "E13", "E14", "E15", "E19", "E21", "E30", "E31", "E32", "E33", "E34", "E35", "E36", "E37", "E40", "E41", "E42", "E43", "E44", "E45", "E46", "E47", "E20", "E16", "E17", "E18"]


def load(path):
    df = pd.DataFrame(json.load(open(path))).dropna()
    return df[(df.h > df.l) & (df.v > 0) & (df.o > 0)].reset_index(drop=True)


SPY = load(os.path.join(CACHE, "SPY.json"))
SPY["a200"] = SPY.c > SPY.c.rolling(200).mean()
SPY_A200 = dict(zip(SPY.d, SPY.a200))
SPY_C = dict(zip(SPY.d, SPY.c)); SPY_O = dict(zip(SPY.d, SPY.o))


def indicators(df):
    o, h, l, c, v = (df[k].astype(float) for k in "ohlcv")
    c1 = c.shift(1)
    body = (c - o).abs(); rng = (h - l).replace(0, np.nan)
    upper = h - np.maximum(o, c); lower = np.minimum(o, c) - l
    tr = pd.concat([h - l, (h - c1).abs(), (l - c1).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().shift(1)
    sma20, sma50, sma200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    avgv = v.rolling(20).mean().shift(1); vrel = v / avgv
    sma20_1 = sma20.shift(1)
    pre_up = (c1 > sma20_1) & (c1 > c.shift(6))
    uptrend = (c > sma50) & (sma50 > sma200) & (sma50 > sma50.shift(10))
    hh50 = h.rolling(50).max().shift(1); hh20 = h.rolling(20).max().shift(1)
    sized = rng > 0.6 * atr
    brk = (c > hh50) & (c1 <= hh50.shift(1))
    ret10 = c1 / c.shift(11) - 1; ret20 = c1 / c.shift(21) - 1
    S = {}
    S["stopping_vol"] = (ret10 < -0.08) & (vrel >= 2) & (lower >= 0.5 * rng) & (c > l + 0.5 * rng) & sized
    S["vol_breakout"] = brk & (vrel >= 2)
    S["ma_pullback"] = uptrend & (l <= sma20 * 1.005) & (c > sma20) & (c > o) & (c1 > sma20_1) & (c.shift(5) > sma20.shift(5) * 1.02)
    S["churning"] = (c > sma50) & (ret20 > 0.10) & (vrel >= 2) & (body < 0.3 * rng) & ((c / c1 - 1).abs() < 0.01) & (h >= hh20 * 0.98)
    S["shooting"] = (upper >= 2 * body) & (lower <= 0.1 * rng) & sized & pre_up
    S["vol_below50"] = (c < sma50) & (vrel >= 1.5)
    liquid = (c >= 5) & ((v * c).rolling(20).mean() >= 5e6)
    S = {k: s.fillna(False).values.astype(bool) for k, s in S.items()}
    return S, dict(o=o.values, h=h.values, l=l.values, c=c.values, v=v.values, vrel=vrel.values,
                   sma20=sma20.values, sma50=sma50.values, hh50=hh50.values, atr=atr.values, uptrend=uptrend.fillna(False).values,
                   liquid=liquid.values, avgv=avgv.values)


# 离场方式参数：stop = none / intra（盘中触及止损价就卖）/ close（收盘低于止损价，隔天开盘卖）
#   wide = 止损再往下放 1 个 ATR；maxh = 最多持有天数；trail = none / ma20（收盘破 20MA 卖）/ armed（先收上 20MA 之后才启用）
#   part = 2R 卖 1/3；ov = 叠加的离场信号：b50 放量破 50MA 全卖 / ss 弱市射击之星卖一半 / ch 滞涨提高止损
EX = {
    "E1": dict(stop="none", maxh=20), "E2": dict(stop="intra", maxh=20), "E3": dict(stop="intra", maxh=60),
    "E4": dict(stop="intra", maxh=120, trail="ma20"), "E5": dict(stop="intra", maxh=120, trail="ma20", part=True),
    "E9": dict(stop="close", maxh=20), "E10": dict(stop="close", maxh=60),
    "E11": dict(stop="intra", wide=True, maxh=20), "E12": dict(stop="intra", wide=True, maxh=60),
    "E13": dict(stop="close", maxh=120, trail="armed"), "E14": dict(stop="close", maxh=120, trail="armed", part=True),
    "E15": dict(stop="none", maxh=60),
    "E19": dict(stop="close", cat=True, maxh=60), "E21": dict(stop="intra", cat=True, maxh=60),
    # 控制亏损 ≤ 8% 的几种做法（2026-11-07）
    "E30": dict(stop="intra", cat=0.08, maxh=60), "E31": dict(stop="close", cat=0.08, maxh=60),
    # 只看风险报酬比：止损单 + 目标价（k 倍止损距离），哪个先到就卖，最多 120 天（2026-11-07）
    "E40": dict(stop="intra", cat=0.08, maxh=120, tgt=2), "E41": dict(stop="intra", cat=0.08, maxh=120, tgt=3),
    "E42": dict(stop="intra", cat=0.15, maxh=120, tgt=2), "E43": dict(stop="intra", wide=True, maxh=120, tgt=2),
    "E44": dict(stop="intra", wide=True, maxh=120, tgt=3),
    "E45": dict(stop="close", cat=True, maxh=20),   # 收盘跌 15% 才卖，拿 20 天
    "E46": dict(stop="close", cat=True, maxh=60, hard=0.20),   # 收盘跌 15% 才卖 + 预挂 −20% 保护单，拿 60 天
    "E47": dict(stop="close", cat=0.08, maxh=60, hard=0.12),   # 收盘跌 8% 卖 + 预挂 −12% 保护单，拿 60 天
    "E32": dict(stop="intra", cat=0.08, maxh=20), "E33": dict(stop="close", cat=0.08, maxh=20),
    "E34": dict(stop="intra", atrk=2, maxh=60), "E35": dict(stop="intra", atrk=2, maxh=20),
    "E36": dict(stop="intra", wide=True, cap=0.08, maxh=60), "E37": dict(stop="intra", wide=True, cap=0.08, maxh=20), "E20": dict(stop="close", wide=True, maxh=60),
    "E16": dict(stop="close", maxh=60, ov="b50"), "E17": dict(stop="close", maxh=60, ov="ss"), "E18": dict(stop="close", maxh=60, ov="ch"),
}


def simulate(X, S, mkt_a200, i_entry, stop, mode):
    """返回 (加权收益, 出场 index, 持有天数)。i_entry = 买入那天（开盘买）。"""
    P = EX[mode]
    o, h, l, c, sma20, N = X["o"], X["h"], X["l"], X["c"], X["sma20"], len(X["c"])
    e = o[i_entry]
    if P.get("wide"):
        stop = stop - X["atr"][i_entry]
    if P.get("cat"):
        stop = e * (0.85 if P["cat"] is True else 1 - P["cat"])   # 只防大灾难：比买价跌 15%（或指定 %）才卖
    if P.get("atrk"):
        stop = e - P["atrk"] * X["atr"][i_entry]                    # 买价往下 k 个 ATR
    if P.get("cap"):
        stop = max(stop, e * (1 - P["cap"]))                        # 止损最远不超过买价 −cap
    R = e - stop; st = stop; stype = P["stop"]; maxh = P["maxh"]; trail = P.get("trail", "none"); ov = P.get("ov")
    pos, real = 1.0, 0.0
    took = False; armed = trail == "ma20"
    pend_sell = 0.0
    j = i_entry
    while j < N:
        if pend_sell > 0 and j > i_entry:
            q = min(pend_sell, pos); real += q * (o[j] / e - 1); pos -= q; pend_sell = 0
            if pos <= 1e-9:
                return real, j, j - i_entry
        if P.get("hard"):                                   # 另外预先挂的保护止损单（盘中），例如 −20%
            hs = e * (1 - P["hard"])
            if o[j] <= hs and j > i_entry:
                real += pos * (o[j] / e - 1); return real, j, j - i_entry
            if l[j] <= hs:
                real += pos * (hs / e - 1); return real, j, j - i_entry
        if stype == "intra":
            if o[j] <= st and j > i_entry:
                real += pos * (o[j] / e - 1); return real, j, j - i_entry
            if l[j] <= st:
                real += pos * (st / e - 1); return real, j, j - i_entry
        if P.get("tgt") and h[j] >= e + P["tgt"] * R:
            px = max(o[j], e + P["tgt"] * R) if j > i_entry else e + P["tgt"] * R
            real += pos * (px / e - 1); return real, j, j - i_entry + 1
        if P.get("part") and not took and h[j] >= e + 2 * R:
            px = max(o[j], e + 2 * R) if j > i_entry else e + 2 * R
            real += (1 / 3) * (px / e - 1); pos -= 1 / 3; took = True
        held = j - i_entry + 1
        if held >= maxh or j == N - 1:
            real += pos * (c[j] / e - 1); return real, j, held
        if stype == "close" and c[j] < st:
            pend_sell = pos
        if trail == "armed" and not armed and c[j] > sma20[j]:
            armed = True
        if armed and c[j] < sma20[j]:
            pend_sell = pos
        if ov == "b50" and S["vol_below50"][j]:
            pend_sell = pos
        if ov == "ss" and S["shooting"][j] and not mkt_a200[j]:
            pend_sell = max(pend_sell, pos / 2)
        if ov == "ch" and S["churning"][j]:
            st = max(st, l[j])
        j += 1
    return real, N - 1, N - 1 - i_entry


def run_sym(f):
    sym = os.path.basename(f)[:-5]
    if sym in ("SPY", "QQQ"):
        return []
    df = load(f)
    if len(df) < 260:
        return []
    S, X = indicators(df)
    d = df.d.values; N = len(d)
    mkt = np.array([bool(SPY_A200.get(x, True)) for x in d])
    o, h, l, c = X["o"], X["h"], X["l"], X["c"]
    entries = []   # (setup, signal i, stop)
    for i in range(200, N - 2):
        if not X["liquid"][i]:
            continue
        if S["stopping_vol"][i]:
            entries.append(("A", i, l[i] * 0.995))
        if S["vol_breakout"][i]:
            entries.append(("B0", i, l[i] * 0.995))
            if X["uptrend"][i] and mkt[i]:
                entries.append(("B", i, l[i] * 0.995))
                if o[i + 1] <= X["hh50"][i] * 1.05:
                    entries.append(("Bx", i, l[i] * 0.995))
        if S["ma_pullback"][i]:
            entries.append(("C0", i, l[i] * 0.995))
    # C：突破后缩量回踩 20MA，再阳线收回 20MA 之上
    bidx = [i for i in range(200, N - 2) if S["vol_breakout"][i] and X["uptrend"][i] and mkt[i] and X["liquid"][i]]
    used = set()
    for b in bidx:
        touched = None
        for j in range(b + 3, min(b + 26, N - 2)):
            if c[j] < X["sma50"][j]:
                break                                   # 跌破 50MA = 回调失败
            if touched is None and l[j] <= X["sma20"][j] * 1.01:
                touched = j
            if touched is not None and c[j] > X["sma20"][j] and c[j] > o[j] and j >= touched:
                seg = slice(b + 1, j)                   # 回踩期间（突破后到反弹前）
                vr = np.nanmean(X["v"][seg]) / X["avgv"][b]
                if vr < 1 and j not in used and X["liquid"][j]:
                    used.add(j)
                    entries.append(("C", j, np.min(l[b + 1:j + 1]) * 0.995))
                break
    out = []
    busy = {}
    for setup, i, stop in sorted(entries, key=lambda t: t[1]):
        ie = i + 1
        if busy.get(setup, -1) >= ie or o[ie] <= stop or stop <= 0:
            continue
        rpct = 1 - stop / o[ie]
        if rpct > 0.25 or rpct < 0.01:           # 止损距离 > 25% 或 < 1% 不做
            continue
        row = {"sym": sym, "setup": setup, "d": d[i], "year": d[i][:4], "mkt": bool(mkt[i]), "rpct": rpct,
               "brk_lvl": X["hh50"][i], "sig_close": c[i], "entry": o[ie],
               "gap": o[ie] / X["hh50"][i] - 1,   # 买价（隔天开盘）离突破点（前 50 天最高价）多远
               "ed": d[ie], "stop": stop, "atr": X["atr"][ie],
               "rpct_w": 1 - (stop - X["atr"][ie]) / o[ie]}   # 宽止损（再往下 1 ATR）的止损距离
        for m in EXITS:
            r, jx, held = simulate(X, S, mkt, ie, stop, m)
            sp = SPY_C.get(d[jx]); sp0 = SPY_O.get(d[ie])
            row[m] = r; row[m + "_h"] = held; row[m + "_xd"] = d[jx]
            row[m + "_x"] = r - ((sp / sp0 - 1) if sp and sp0 else 0)
            if m == "E10":
                busy[setup] = jx
        out.append(row)
    return out


def summ(t, m):
    r = t[m]; R = r / t["rpct"]
    g, b = r[r > 0].sum(), -r[r < 0].sum()
    return {"n": int(len(t)), "win": round(100 * (r > 0).mean(), 1), "avg": round(100 * r.mean(), 2),
            "med": round(100 * r.median(), 2), "avgR": round(R.mean(), 2), "pf": round(g / b, 2) if b else None,
            "ex": round(100 * t[m + "_x"].mean(), 2), "hold": round(t[m + "_h"].mean(), 1),
            "t": round(r.mean() / r.std() * np.sqrt(len(r)), 1) if len(r) > 2 else None,
            "loss_avg": round(100 * r[r < 0].mean(), 2), "worst5": round(100 * r.quantile(0.05), 2),
            "years_pos": int(sum(t.groupby("year")[m].mean() > 0)), "years": int(t.year.nunique()),
            "by_year": {y: round(100 * v, 2) for y, v in t.groupby("year")[m].mean().items()}}


def main():
    files = sorted(glob.glob(os.path.join(CACHE, "*.json")))
    with Pool(10) as p:
        rows = [r for rs in p.imap_unordered(run_sym, files, chunksize=20) for r in rs]
    T = pd.DataFrame(rows)
    T.to_pickle(os.path.join(HERE, f"exit_trades{TAG}.pkl"))
    res = {"info": {"start": str(T.d.min()), "end": str(T.d.max()), "n_trades": int(len(T))}, "res": {}}
    for s in ["A", "B0", "B", "Bx", "C", "C0"]:
        ts = T[T.setup == s]
        res["res"][s] = {m: summ(ts, m) for m in EXITS}
        res["res"][s]["rpct"] = round(100 * ts.rpct.median(), 2)
        res["res"][s]["bull"] = summ(ts[ts.mkt], "E10") if ts.mkt.sum() > 2 else None
        res["res"][s]["bear"] = summ(ts[~ts.mkt], "E10") if (~ts.mkt).sum() > 2 else None
        res["res"][s]["bull_E3"] = summ(ts[ts.mkt], "E3") if ts.mkt.sum() > 2 else None
        res["res"][s]["bear_E3"] = summ(ts[~ts.mkt], "E3") if (~ts.mkt).sum() > 2 else None
    # 长下影推荐卖法（E19）按大盘分；突破推荐卖法（E11）按「买价离突破点多远」分
    tA, tB = T[T.setup == "A"], T[T.setup == "B"]
    res["A_E19_bull"], res["A_E19_bear"] = summ(tA[tA.mkt], "E19"), summ(tA[~tA.mkt], "E19")
    res["B_gap_E11"] = {lab: summ(tB[(tB.gap > lo) & (tB.gap <= hi)], "E11") | {"gap_med": round(100 * tB[(tB.gap > lo) & (tB.gap <= hi)].gap.median(), 1)}
                        for lab, lo, hi in (("0-2%", -1, 0.02), ("2-5%", 0.02, 0.05), ("5-10%", 0.05, 0.10), (">10%", 0.10, 9), ("<=5%", -1, 0.05), (">5%", 0.05, 9))}
    json.dump(res, open(os.path.join(HERE, f"exit_bt{TAG}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for s, v in res["res"].items():
        print(f"== {s}  中位止损 {v['rpct']}%")
        for m in EXITS:
            x = v[m]
            print(f"  {m:3s} n={x['n']:6d} 胜{x['win']:5.1f} 均{x['avg']:6.2f} 中{x['med']:6.2f} R{x['avgR']:5.2f} PF{x['pf']} 超SPY{x['ex']:6.2f} 持{x['hold']:5.1f} t{x['t']} 年{x['years_pos']}/{x['years']} 亏均{x['loss_avg']} 最差5%{x['worst5']}")
        for k in ("bull", "bear"):
            if v[k]: print(f"  {k}: n={v[k]['n']} 均{v[k]['avg']} 超{v[k]['ex']} 胜{v[k]['win']}")


if __name__ == "__main__":
    main()
