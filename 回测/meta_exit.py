"""J Law META 回调：用不同止损 / 卖法逐笔模拟，跟同期 SPY 比。信号来自 meta_sig.py（与网站同一份 analyse()）。
进场：信号日下一天开盘买（同 backtest.py）。同一只股票持仓期间不重复买。
卖法：
  J5R   META 止损（盘中）+ 5R 目标，最多 40 天（J Law 原版之一）
  JMA10 META 止损 + 收盘跌破 10 天线卖，最多 60 天
  JMA20 META 止损 + 收盘跌破 20 天线卖，最多 60 天
  S20   META 止损，否则拿 20 天        S60   META 止损，否则拿 60 天
  P8    挂 −8% 止损单，拿 60 天        C8    收盘跌破 −8% 隔天卖，拿 60 天
  C15   收盘跌 15% 才卖，拿 60 天      N60   不设止损，拿 60 天
输出 meta_trades{TAG}.pkl
"""
import json, os, pickle, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = os.environ.get("BT_TAG", "")
CACHE = os.path.join(HERE, "cache" + TAG)
MODES = ["J5R", "JMA10", "JMA20", "S20", "S60", "P8", "C8", "C15", "N60", "C8H12", "C15H20",
         "RR1_5M", "RR2M", "RR3M", "RR4M", "RR5M", "RR2P8", "RR3P8", "RR4P8"]   # RR = 只看风险报酬比（止损或目标先到，最多 120 天）


def load(sym):
    d = json.load(open(os.path.join(CACHE, sym + ".json")))
    df = pd.DataFrame(d).dropna()
    df = df[(df.h > df.l) & (df.v > 0) & (df.o > 0)].reset_index(drop=True)
    return df


def sim(o, h, l, c, s10, s20, t, stop_meta, mode):
    """t = 买进那天（开盘买）。返回 (收益, 出场 index)"""
    N = len(c); e = o[t]
    R = e - stop_meta
    if mode.startswith("RR"):          # 风险报酬比卖法：RR{k}M = META 止损 + k 倍 R 目标；RR{k}P8 = −8% 止损单 + k×8% 目标；最多 120 天
        k_ = float(mode[2:].rstrip("MP8").replace("_", "."))
        st = stop_meta if mode.endswith("M") else e * 0.92
        tgt = e + k_ * (e - st)
        for k in range(t, min(N, t + 120)):
            if k > t and o[k] <= st:
                return o[k] / e - 1, k
            if l[k] <= st:
                return st / e - 1, k
            if h[k] >= tgt:
                return (max(o[k], tgt) if k > t else tgt) / e - 1, k
        k = min(N, t + 120) - 1
        return c[k] / e - 1, k
    if mode in ("J5R", "JMA10", "JMA20", "S20", "S60"):
        st, kind = stop_meta, "intra"
    elif mode == "P8":
        st, kind = e * 0.92, "intra"
    elif mode == "C8":
        st, kind = e * 0.92, "close"
    elif mode == "C15":
        st, kind = e * 0.85, "close"
    elif mode in ("C8H12", "C15H20"):               # 收盘止损 + 预挂盘中保护单
        st, kind = (e * 0.92, "close") if mode == "C8H12" else (e * 0.85, "close")
        hard = e * (0.88 if mode == "C8H12" else 0.80)
    else:
        st, kind = None, None
    maxd = {"J5R": 40, "S20": 20}.get(mode, 60)
    pend = False
    hard = locals().get("hard")
    for k in range(t, min(N, t + maxd)):
        if pend:
            return o[k] / e - 1, k
        if hard is not None:
            if k > t and o[k] <= hard:
                return o[k] / e - 1, k
            if l[k] <= hard:
                return hard / e - 1, k
        if kind == "intra":
            if k > t and o[k] <= st:
                return o[k] / e - 1, k
            if l[k] <= st:
                return st / e - 1, k
        if mode == "J5R":
            tgt = e + 5 * R
            if h[k] >= tgt:
                return (max(o[k], tgt) if k > t else tgt) / e - 1, k
        if k == min(N, t + maxd) - 1:
            return c[k] / e - 1, k
        if kind == "close" and c[k] < st:
            pend = True
        if mode == "JMA10" and k > t and c[k] < s10[k]:
            pend = True
        if mode == "JMA20" and k > t and c[k] < s20[k]:
            pend = True
    k = N - 1
    return c[k] / e - 1, k


def main():
    sig = pickle.load(open(os.path.join(HERE, f"jlaw_sig{TAG}.pkl"), "rb"))
    sig = sig[sig.kind == "META"].copy()
    sig["d"] = pd.to_datetime(sig.d).dt.strftime("%Y-%m-%d")
    spy = load("SPY"); spo = dict(zip(spy.d, spy.o)); spc = dict(zip(spy.d, spy.c))
    spy["a200"] = spy.c > spy.c.rolling(200).mean(); A = dict(zip(spy.d, spy.a200))
    rows = []
    for sym, g in sig.groupby("sym"):
        df = load(sym); d = df.d.values
        o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
        s10 = pd.Series(c).rolling(10).mean().values; s20 = pd.Series(c).rolling(20).mean().values
        pos = {x: i for i, x in enumerate(d)}
        busy = -1
        for r in g.sort_values("d").itertuples():
            i = pos.get(r.d)
            if i is None or i + 61 >= len(c):          # 要有完整 60 天
                continue
            t = i + 1
            if t <= busy or o[t] <= r.stop:
                continue
            row = {"sym": sym, "d": r.d, "ed": d[t], "entry": o[t], "stop": r.stop, "risk": 1 - r.stop / o[t], "n": r.n, "mkt": bool(A.get(r.d, True))}
            far = t
            for m in MODES:
                ret, k = sim(o, h, l, c, s10, s20, t, r.stop, m)
                row[m] = ret; row[m + "_xd"] = d[k]; row[m + "_h"] = k - t + 1
                row[m + "_x"] = ret - (spc[d[k]] / spo[d[t]] - 1)
                if not m.startswith("RR"):      # 持仓期按原来 9 种卖法算，加 RR 不改变交易名单
                    far = max(far, k)
            busy = far
            rows.append(row)
    T = pd.DataFrame(rows)
    T.to_pickle(os.path.join(HERE, f"meta_trades{TAG}.pkl"))
    print("META 交易", len(T), T.d.min(), T.d.max())
    ap = T.d.str[:7] == "2025-04"
    for m in MODES:
        r, x = T[m], T[m + "_x"]; yr = T.groupby(T.d.str[:4])[m + "_x"].mean()
        print(f"{m:6s} 胜{100*(r>0).mean():4.0f}% 均{100*r.mean():6.2f} 超SPY{100*x.mean():6.2f} 年正{(yr>0).sum()}/{len(yr)} 去25年4月{100*x[~ap].mean():6.2f} "
              f"亏均{100*r[r<0].mean():6.1f} 最差5%{100*r.quantile(.05):6.1f} 最差1%{100*r.quantile(.01):6.1f} 持{T[m+'_h'].mean():4.0f} "
              f"| 大盘好{100*T[T.mkt][m+'_x'].mean():6.2f}({T.mkt.sum()}) 大盘弱{100*T[~T.mkt][m+'_x'].mean():6.2f}({(~T.mkt).sum()})")
    print("止损距离中位", round(100 * T.risk.median(), 2), "%")


if __name__ == "__main__":
    main()
