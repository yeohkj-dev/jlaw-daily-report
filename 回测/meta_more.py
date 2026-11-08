"""在 META + RS 交易（meta_trades20_rs.pkl，同一批进场）上再测几种卖法，并加上跟同期 QQQ 比。不改原来的文件。
进场 = 原来的 ed 开盘价（entry）。卖法（全部收盘后决定、第二天开盘卖，不用盯盘）：
  C8      收盘比买价跌 8% → 隔天开盘卖；否则拿 60 天（原版，用来核对）
  C8H90   同上，拿 90 天            C8H120  同上，拿 120 天
  C10 / C12  收盘跌 10% / 12% 才卖，拿 60 天
  C8T50   收盘跌 8% 卖；拿满 60 天后，只要收盘还在 50 天线上就继续拿，跌破 50 天线隔天卖（最多 250 天）
  C8BE    收盘跌 8% 卖；收盘曾经 ≥ +15% 之后，止损线提高到买价（不再亏钱），拿 60 天
  C8TR    收盘跌 8% 卖；收盘曾经 ≥ +20% 之后，收盘比最高收盘回落 15% 就卖；最多 120 天
输出 meta_more20.pkl：每种卖法的收益、出场日、持有天数、比 SPY / 比 QQQ 多赚。
"""
import json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache20")
MODES = ["C8", "C8H90", "C8H120", "C10", "C12", "C8T50", "C8BE", "C8TR"]


def load(sym):
    df = pd.DataFrame(json.load(open(os.path.join(CACHE, sym + ".json")))).dropna()
    return df[(df.h > df.l) & (df.v > 0) & (df.o > 0)].reset_index(drop=True)


def sim(o, c, s50, t, mode):
    """返回 (出场 index, 'open' 或 'close')：条件触发 = 隔天开盘卖；拿满天数 = 当天收盘卖（同 meta_exit.py）。"""
    N, e = len(c), o[t]
    stop = e * {"C10": 0.90, "C12": 0.88}.get(mode, 0.92)
    maxd = {"C8H90": 90, "C8H120": 120, "C8T50": 250, "C8TR": 120}.get(mode, 60)
    last = min(N, t + maxd) - 1
    pend, peak, armed = False, 0.0, False
    for k in range(t, last + 1):
        if pend:
            return k, "open"
        if k == last:
            return k, "close"
        if mode == "C8T50" and k - t + 1 == 60 and c[k] < s50[k]:
            return k, "close"                       # 第 60 天已在 50 天线下 = 跟原版一样收盘卖
        peak = max(peak, c[k])
        if mode == "C8BE" and c[k] >= e * 1.15:
            stop = max(stop, e)
        if mode == "C8TR" and c[k] >= e * 1.20:
            armed = True
        if c[k] < stop:
            pend = True
        if mode == "C8TR" and armed and c[k] < peak * 0.85:
            pend = True
        if mode == "C8T50" and k - t + 1 > 60 and c[k] < s50[k]:
            pend = True
    return N - 1, "close"


if __name__ == "__main__":
    M = pd.read_pickle(os.path.join(HERE, "meta_trades20_rs.pkl"))
    spy, qqq = load("SPY"), load("QQQ")
    so, sc = dict(zip(spy.d, spy.o)), dict(zip(spy.d, spy.c))
    qo, qc = dict(zip(qqq.d, qqq.o)), dict(zip(qqq.d, qqq.c))
    rows = []
    for sym, g in M.groupby("sym"):
        df = load(sym); d = df.d.values; o, c = df.o.values, df.c.values
        s50 = pd.Series(c).rolling(50).mean().values
        pos = {x: i for i, x in enumerate(d)}
        for r in g.itertuples():
            t = pos[r.ed]
            row = {"sym": sym, "d": r.d, "ed": r.ed, "entry": o[t], "rs": r.rs, "mkt": r.mkt, "n": r.n}
            for m in MODES:
                k, how = sim(o, c, s50, t, m)
                px, ps, pq = (c[k], sc[d[k]], qc[d[k]]) if how == "close" else (o[k], so[d[k]], qo[d[k]])
                ret = px / o[t] - 1
                row[m] = ret; row[m + "_xd"] = d[k]; row[m + "_h"] = k - t + 1
                row[m + "_x"] = ret - (ps / so[d[t]] - 1)
                row[m + "_xq"] = ret - (pq / qo[d[t]] - 1)
            rows.append(row)
    T = pd.DataFrame(rows)
    T.to_pickle(os.path.join(HERE, "meta_more20.pkl"))
    print(len(T))
