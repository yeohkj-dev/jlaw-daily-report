"""完整研究（21 年，2005–2026，日线 / 周线）：每个系统 × 买进方法 × 卖出方法。

系统（信号都在日线上找，「大周期确认」）：
  A0       J Law META 回调 + RS ≥ 90 + SPY 在 200 天线上（网站「A0. 回测最佳」）
  META     J Law META 回调就绪（全部）
  BRK      放量突破 50 日高点（量 ≥ 20 日均量 2 倍）+ 个股升势（收盘 > 50 天线 > 200 天线、50 天线向上）+ SPY 在 200 天线上
  C9       C9 方法（规则见 c9_signals()）
买进（信号日之后）：
  D0 次日开盘买（现在的做法）
  D1 5 天内收盘高于信号日最高价 → 当天收盘买（日线确认）
  D2 5 天内盘中碰到信号日最高价就买（开盘已高 3% 以上不追）
  +W 只在周线上升趋势时买（周收盘 > 10 周线 > 40 周线、10 周线向上，用上一周的数据）
卖出（全部先有「系统本身的止损」：A0 / META 收盘跌 8% 次日开盘卖 + 盘中 −12% 保护；C9 收盘跌 10% + 盘中 −15%；BRK 收盘跌 15% 次日开盘卖）：
  X0   系统原本的卖法：止损或拿满 60 个交易日
  XM20 日线收盘跌破 20 天线 → 次日开盘卖（最多 250 天）
  XM50 日线收盘跌破 50 天线 → 次日开盘卖（最多 250 天）
  XW10 周线收盘跌破 10 周线 → 下周一开盘卖（最多 250 天）
比较：每笔报酬、比同一时间买卖 SPY 多赚多少、胜率、平均持有天数、两个十年（2005–2015、2016–2026）分开看。
用法：python 回测/mtf/research21.py → research21_trades.pkl、research21_stats.json
"""
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BT = next((p for p in (os.environ.get("BT_DATA"), os.path.join(REPO, "回测"), os.path.join(os.path.dirname(REPO), "回测"))
           if p and os.path.exists(os.path.join(p, "cache20"))), os.path.join(REPO, "回测"))
MAX_WAIT = 5
STOPS = {"A0": ("pct", 0.08, 0.12), "META": ("pct", 0.08, 0.12), "BRK": ("pct", 0.15, None), "C9": ("pct", 0.10, 0.15)}
EXITS = {"X0": (None, 60), "XM20": ("m20", 250), "XM50": ("m50", 250), "XW10": ("w10", 250)}


def daily(sym):
    d = json.load(open(os.path.join(BT, "cache20", sym + ".json")))
    df = pd.DataFrame({k: d[k] for k in "ohlcv"}, index=pd.to_datetime(d["d"]))
    return df[~df.index.duplicated()].dropna()


def prep(D):
    c = D["c"]
    X = {k: D[k].values for k in "ohlcv"}
    X["m20"] = c.rolling(20).mean().values
    X["m50"] = c.rolling(50).mean().values
    X["m200"] = c.rolling(200).mean().values
    w = c.resample("W-FRI").last().dropna()
    m10, m40 = w.rolling(10).mean(), w.rolling(40).mean()
    wup = ((w > m10) & (m10 > m40) & (m10 > m10.shift(2))).shift(1)            # 上一周的周线趋势
    X["wup"] = wup.reindex(D.index, method="ffill").fillna(False).astype(bool).values
    # 周线卖出：每周最后一个交易日，周收盘 < 10 周线
    below = (w < m10)
    last_day = pd.Series(D.index, index=D.index).groupby(D.index.to_period("W-FRI")).transform("max")
    wk_below = below.reindex(D.index, method="ffill").fillna(False).astype(bool).values
    X["w10x"] = wk_below & (D.index.values == last_day.values)
    return X


def c9_signals(D, X, spy_up):
    """C9 方法的买进信号（规则由 c9_rules 填入；没有规则时返回空）。"""
    try:
        import c9_rules
    except ImportError:
        return []
    return c9_rules.signals(D, X, spy_up)


def brk_signals(D, X, spy_up):
    c, h, v = D["c"], D["h"], D["v"]
    hh50 = h.rolling(50).max().shift(1)
    vrel = v / v.rolling(20).mean().shift(1)
    m50, m200 = c.rolling(50).mean(), c.rolling(200).mean()
    up = (c > m50) & (m50 > m200) & (m50 > m50.shift(10))
    liquid = (c >= 5) & ((v * c).rolling(20).mean() >= 5e6)
    brk = (c > hh50) & (c.shift(1) <= hh50.shift(1)) & (vrel >= 2) & up & liquid & spy_up.reindex(D.index).fillna(False)
    return [i for i in np.where(brk.values)[0] if i >= 200]


def trade(X, i0, kind, entry_m, exit_m):
    """模拟一笔。返回 dict 或 None。"""
    o, h, l, c = X["o"], X["h"], X["l"], X["c"]
    n = len(c)
    if i0 + 1 >= n:
        return None
    hi = h[i0]
    if entry_m == "D0":
        k, px, at_close = i0 + 1, o[i0 + 1], False
    else:
        k = None
        for j in range(i0 + 1, min(n, i0 + 1 + MAX_WAIT)):
            if entry_m == "D1" and c[j] > hi:
                k, px, at_close = j, c[j], True
                break
            if entry_m == "D2" and h[j] >= hi and o[j] <= hi * 1.03:
                k, px, at_close = j, max(o[j], hi), False
                break
        if k is None:
            return None
    _, soft, hard = STOPS[kind]
    s_px, h_px = px * (1 - soft), (px * (1 - hard) if hard else None)
    rule, maxh = EXITS[exit_m]
    if not at_close:
        if h_px and l[k] <= h_px:
            return dict(k=k, j=k, px=px, xp=h_px, why="hard", x_at="intra", e_at="open")
    if c[k] <= s_px and not at_close:
        return dict(k=k, j=k + 1, px=px, xp=o[k + 1], why="stop", x_at="open", e_at="open") if k + 1 < n else None
    for j in range(k + 1, min(n, k + maxh)):
        if h_px and o[j] <= h_px:
            return dict(k=k, j=j, px=px, xp=o[j], why="hard", x_at="open", e_at="close" if at_close else "open")
        if h_px and l[j] <= h_px:
            return dict(k=k, j=j, px=px, xp=h_px, why="hard", x_at="intra", e_at="close" if at_close else "open")
        sig = c[j] <= s_px
        if not sig and rule:
            sig = (rule == "m20" and c[j] < X["m20"][j]) or (rule == "m50" and c[j] < X["m50"][j]) or (rule == "w10" and X["w10x"][j])
        if sig:
            return dict(k=k, j=j + 1, px=px, xp=o[j + 1], why="stop" if c[j] <= s_px else "trail", x_at="open",
                        e_at="close" if at_close else "open") if j + 1 < n else None
    j = k + maxh - 1
    if j >= n:
        return None
    return dict(k=k, j=j, px=px, xp=c[j], why="time", x_at="close", e_at="close" if at_close else "open")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, HERE)
    SPY = daily("SPY")
    spy_up = SPY["c"] > SPY["c"].rolling(200).mean()
    mt = pickle.load(open(os.path.join(BT, "meta_trades20_rs.pkl"), "rb"))
    js = pickle.load(open(os.path.join(BT, "jlaw_sig20.pkl"), "rb"))
    pre = {}
    for r in mt[(mt.rs >= 90) & mt.mkt].itertuples():
        pre.setdefault(r.sym, []).append(("A0", pd.Timestamp(r.d)))
    for r in js[js.kind == "META"].itertuples():
        pre.setdefault(r.sym, []).append(("META", pd.Timestamp(r.d)))
    syms = sorted(set(pre) | {f[:-5] for f in os.listdir(os.path.join(BT, "cache20")) if f.endswith(".json")})
    rows, counts = [], {}
    for n_, sym in enumerate(syms, 1):
        if sym == "SPY":
            continue
        try:
            D = daily(sym)
        except Exception:
            continue
        if len(D) < 260:
            continue
        X = prep(D)
        idx = {d: i for i, d in enumerate(D.index)}
        sigs = [(k, idx[d]) for k, d in pre.get(sym, []) if d in idx]
        sigs += [("BRK", i) for i in brk_signals(D, X, spy_up)]
        sigs += [("C9", i) for i in c9_signals(D, X, spy_up)]
        for kind, i0 in sigs:
            counts[kind] = counts.get(kind, 0) + 1
            for em in ("D0", "D1", "D2"):
                for xm in EXITS:
                    t = trade(X, i0, kind, em, xm)
                    if not t:
                        continue
                    dk, dj = D.index[t["k"]], D.index[t["j"]]
                    if dk not in SPY.index or dj not in SPY.index:
                        continue
                    s0 = SPY.at[dk, "c"] if t["e_at"] == "close" else SPY.at[dk, "o"]
                    s1 = SPY.at[dj, "o"] if t["x_at"] == "open" else SPY.at[dj, "c"]
                    rows.append((kind, sym, D.index[i0], em, xm, bool(X["wup"][i0]), t["px"], t["xp"] / t["px"] - 1, s1 / s0 - 1,
                                 t["j"] - t["k"], t["why"]))
        if n_ % 300 == 0:
            print(f"  {n_}/{len(syms)}", counts, flush=True)
    T = pd.DataFrame(rows, columns=["kind", "sym", "sig", "entry", "exit", "wup", "px", "ret", "spy", "hold", "why"])
    T["ex"] = T.ret - T.spy
    T["year"] = T.sig.dt.year
    pickle.dump(T, open(os.path.join(HERE, "research21_trades.pkl"), "wb"))
    print("信号", counts, "交易", len(T), flush=True)
    stats = {}
    for (kind, em, xm), g in T.groupby(["kind", "entry", "exit"]):
        for wf in (False, True):
            x = g[g.wup] if wf else g
            if len(x) < 30:
                continue
            key = f"{kind}|{em}{'+W' if wf else ''}|{xm}"
            yrs = x.groupby("year").ex.mean()
            stats[key] = dict(n=len(x), take=len(x) / counts[kind] * 100, avg=x.ret.mean() * 100, med=x.ret.median() * 100,
                              win=(x.ret > 0).mean() * 100, ex=x.ex.mean() * 100, t=x.ex.mean() / (x.ex.std() / np.sqrt(len(x))),
                              hold=x.hold.mean(), yrs_pos=(yrs > 0).mean() * 100,
                              h1=x[x.year <= 2015].ex.mean() * 100, h2=x[x.year >= 2016].ex.mean() * 100,
                              per_day=x.ex.mean() * 100 / max(1, x.hold.mean()), worst=x.ret.quantile(0.05) * 100)
    json.dump(dict(counts=counts, stats=stats), open(os.path.join(HERE, "research21_stats.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=float)
    for k, v in stats.items():
        print(k.ljust(22), " ".join(f"{a}={b:.2f}" if isinstance(b, float) else f"{a}={b}" for a, b in v.items()))


if __name__ == "__main__":
    main()
