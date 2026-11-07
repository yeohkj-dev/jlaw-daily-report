"""第四批：Smart Money 的 Order Block（订单块）——蓝色 = 看涨 OB，红色 = 看跌 OB。
按 SMC 通用定义自己写（不是 LuxAlgo 源码），逐根K线循环，好让 Pine 版逐行照抄：
  1. 转折点：左右各 5 根K线的最高 / 最低点（同 patterns3.py）。
  2. 结构突破：收盘第一次站上「最近一个转折高点」→ 在转折高点到今天之间找最低价那根K线，
     它的 [最低, 最高] 就是看涨 OB。跌破「最近一个转折低点」反之，取最高价那根K线 = 看跌 OB。
  3. 失效：收盘跌破看涨 OB 底部（或站上看跌 OB 顶部）就删掉。每边最多保留最近 5 个。
  4. 回测信号 = 价格**第一次回到** OB（看涨：最低价 ≤ OB 顶部且收盘没跌破底部），收盘成立、次日开盘进场。
接口同 patterns.detect：返回 ({名: 布尔Series}, ctx)；detect_ob(df, zones=True) 另外返回每个 OB 的建立记录。"""
import numpy as np
import pandas as pd

META_OB = {
    "ob_bull": ("看涨 Order Block（第一次回踩）", 1, "Smart Money"),
    "ob_bear": ("看跌 Order Block（第一次反抽）", -1, "Smart Money"),
}
R = 5
MAXN = 5


def detect_ob(df, zones=False):
    o, h, l, c, v = (df[k].astype(float).values for k in "ohlcv")
    N = len(c)
    out = {k: np.zeros(N, bool) for k in META_OB}
    made = []                                # (建立当天, 方向, 起点K线, 顶, 底)
    bull, bear = [], []                      # 活跃 OB：[起点, 顶, 底, 已碰过]
    lastPH = lastPL = None; phBar = plBar = -1; phBroken = plBroken = True
    for i in range(1, N):
        p = i - R
        if p - R >= 0:
            if all(h[p] > h[p - k] for k in range(1, R + 1)) and all(h[p] >= h[p + k] for k in range(1, R + 1)):
                lastPH, phBar, phBroken = h[p], p, False
            if all(l[p] < l[p - k] for k in range(1, R + 1)) and all(l[p] <= l[p + k] for k in range(1, R + 1)):
                lastPL, plBar, plBroken = l[p], p, False
        # 旧 OB：先看失效，再看第一次回踩
        keep = []
        for z in bull:
            if c[i] < z[2]:
                continue
            if not z[3] and l[i] <= z[1]:
                z[3] = True; out["ob_bull"][i] = True
            keep.append(z)
        bull = keep
        keep = []
        for z in bear:
            if c[i] > z[1]:
                continue
            if not z[3] and h[i] >= z[2]:
                z[3] = True; out["ob_bear"][i] = True
            keep.append(z)
        bear = keep
        # 结构突破 → 新 OB
        if not phBroken and c[i] > lastPH:
            phBroken = True
            k = phBar + 1 + int(np.argmin(l[phBar + 1:i + 1]))
            bull.append([k, h[k], l[k], False]); made.append((i, 1, k, h[k], l[k]))
            if len(bull) > MAXN:
                bull.pop(0)
        if not plBroken and c[i] < lastPL:
            plBroken = True
            k = plBar + 1 + int(np.argmax(h[plBar + 1:i + 1]))
            bear.append([k, h[k], l[k], False]); made.append((i, -1, k, h[k], l[k]))
            if len(bear) > MAXN:
                bear.pop(0)

    cs = pd.Series(c); c1 = cs.shift(1); hs, ls = pd.Series(h), pd.Series(l)
    tr = pd.concat([hs - ls, (hs - c1).abs(), (ls - c1).abs()], axis=1).max(axis=1)
    sma20, sma50, sma200 = cs.rolling(20).mean(), cs.rolling(50).mean(), cs.rolling(200).mean()
    vrel = pd.Series(v) / pd.Series(v).rolling(20).mean().shift(1)
    ctx = pd.DataFrame({"vrel": vrel, "atr": tr.rolling(14).mean().shift(1), "sma20": sma20, "sma50": sma50, "sma200": sma200,
                        "uptrend": (cs > sma50) & (sma50 > sma200) & (sma50 > sma50.shift(10)), "above200": cs > sma200})
    ctx.index = df.index
    P = {k: pd.Series(a, index=df.index) for k, a in out.items()}
    return (P, ctx, made) if zones else (P, ctx)
