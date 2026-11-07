"""第三批：经典图形（多根K线组成的结构）——双底、双顶、头肩底、头肩顶、上升/下降三角形、杯柄、牛旗、熊旗。
用"转折点"（左右各 5 根K线的最高/最低点）找结构，信号在**收盘突破颈线/阻力（或跌破支撑）那一天**成立。
写成逐根K线的循环，好让 TradingView Pine 版逐行照抄（K线形态Top20 之后的 经典图形.pine）。
不加成交量条件（回测再按放量拆开看）。接口同 patterns.detect：返回 ({名: 布尔Series}, ctx)，
另外 detect3(df, spans=True) 会多返回每次信号的起点K线（画背景用）。"""
import numpy as np
import pandas as pd

META3 = {
    "dbl_bottom": ("双底（W 底）", 1, "经典图形"),
    "dbl_top": ("双顶（M 头）", -1, "经典图形"),
    "hs_bottom": ("头肩底", 1, "经典图形"),
    "hs_top": ("头肩顶", -1, "经典图形"),
    "asc_tri": ("上升三角形", 1, "经典图形"),
    "desc_tri": ("下降三角形", -1, "经典图形"),
    "cup_handle": ("杯柄形态", 1, "经典图形"),
    "bull_flag": ("牛旗", 1, "经典图形"),
    "bear_flag": ("熊旗", -1, "经典图形"),
}
R = 5  # 转折点左右各 R 根


def detect3(df, spans=False):
    o, h, l, c, v = (df[k].astype(float).values for k in "ohlcv")
    N = len(c)
    out = {k: np.zeros(N, bool) for k in META3}
    start = {k: np.full(N, -1) for k in META3}
    used = {k: -1 for k in META3}
    PH, PL = [], []                       # 已确认的转折高点 / 低点：(K线位置, 价格)

    def hx(a, b): return h[a:b + 1].max()      # a..b（含）最高价
    def lx(a, b): return l[a:b + 1].min()
    def cx(a, b): return c[a:b + 1].max()
    def cn(a, b): return c[a:b + 1].min()

    def fire(k, i, anchor, s):
        out[k][i] = True; start[k][i] = s; used[k] = anchor

    for i in range(1, N):
        p = i - R
        if p - R >= 0:
            if all(h[p] > h[p - k] for k in range(1, R + 1)) and all(h[p] >= h[p + k] for k in range(1, R + 1)):
                PH.append((p, h[p]))
            if all(l[p] < l[p - k] for k in range(1, R + 1)) and all(l[p] <= l[p + k] for k in range(1, R + 1)):
                PL.append((p, l[p]))
        ci, cp = c[i], c[i - 1]

        if len(PL) >= 2:
            (b1, p1), (b2, p2) = PL[-2], PL[-1]
            lo, hi = min(p1, p2), max(p1, p2)
            # 双底：两个低点相差 ≤4%，间隔 10–80 根，颈线 = 两低之间最高价，收盘上穿颈线
            if used["dbl_bottom"] != b2 and 10 <= b2 - b1 <= 80 and i - b2 <= 40 and hi - lo <= 0.04 * lo:
                nk = hx(b1, b2)
                if ci > nk and cp <= nk and (nk - hi) / nk >= 0.06 and lx(b2 + 1, i) > lo and hx(max(0, b1 - 40), b1 - 1) > nk:
                    fire("dbl_bottom", i, b2, b1)
            # 下降三角形：两个低点相差 ≤2.5%（水平支撑），高点一个比一个低，收盘跌破支撑
            if used["desc_tri"] != b2 and 10 <= b2 - b1 <= 80 and i - b2 <= 40 and hi - lo <= 0.025 * hi:
                if ci < lo and cp >= lo:
                    hm = hx(b1, b2)
                    if hx(b2, i) < hm and (hm - lo) / hm >= 0.05 and hm < hx(max(0, b1 - 20), b1 - 1) and cn(b2 + 1, i - 1) >= lo:
                        fire("desc_tri", i, b2, b1)

        if len(PH) >= 2:
            (b1, p1), (b2, p2) = PH[-2], PH[-1]
            lo, hi = min(p1, p2), max(p1, p2)
            # 双顶
            if used["dbl_top"] != b2 and 10 <= b2 - b1 <= 80 and i - b2 <= 40 and hi - lo <= 0.04 * lo:
                nk = lx(b1, b2)
                if ci < nk and cp >= nk and (lo - nk) / lo >= 0.06 and hx(b2 + 1, i) < hi and lx(max(0, b1 - 40), b1 - 1) < nk:
                    fire("dbl_top", i, b2, b1)
            # 上升三角形：两个高点相差 ≤2.5%（水平阻力），低点一个比一个高，收盘突破阻力
            if used["asc_tri"] != b2 and 10 <= b2 - b1 <= 80 and i - b2 <= 40 and hi - lo <= 0.025 * hi:
                if ci > hi and cp <= hi:
                    lm = lx(b1, b2)
                    if lx(b2, i) > lm and (hi - lm) / hi >= 0.05 and lm > lx(max(0, b1 - 20), b1 - 1) and cx(b2 + 1, i - 1) <= hi:
                        fire("asc_tri", i, b2, b1)

        if len(PL) >= 3:
            (bA, pA), (bB, pB), (bC, pC) = PL[-3], PL[-2], PL[-1]
            d1, d2 = bB - bA, bC - bB
            mn = min(pA, pC)
            # 头肩底：中间低点最低，两肩高度接近，颈线 = 整段最高价（水平、保守）
            if used["hs_bottom"] != bC and i - bC <= 30 and pB < pA and pB < pC and 15 <= bC - bA <= 120 and d2 <= 3 * d1 and d1 <= 3 * d2 \
                    and (mn - pB) / mn >= 0.03 and abs(pA - pC) <= 0.5 * (mn - pB):
                nk = hx(bA, bC)
                if ci > nk and cp <= nk and (nk - pB) / nk >= 0.08 and lx(bC + 1, i) > pB and hx(max(0, bA - 40), bA - 1) > nk:
                    fire("hs_bottom", i, bC, bA)

        if len(PH) >= 3:
            (bA, pA), (bB, pB), (bC, pC) = PH[-3], PH[-2], PH[-1]
            d1, d2 = bB - bA, bC - bB
            mx = max(pA, pC)
            if used["hs_top"] != bC and i - bC <= 30 and pB > pA and pB > pC and 15 <= bC - bA <= 120 and d2 <= 3 * d1 and d1 <= 3 * d2 \
                    and (pB - mx) / mx >= 0.03 and abs(pA - pC) <= 0.5 * (pB - mx):
                nk = lx(bA, bC)
                if ci < nk and cp >= nk and (pB - nk) / pB >= 0.08 and hx(bC + 1, i) < pB and lx(max(0, bA - 40), bA - 1) < nk:
                    fire("hs_top", i, bC, bA)

        if len(PH) >= 1:
            bB, pB = PH[-1]
            # 杯柄：右杯沿 = 最近转折高点；左杯沿 = 往回找第一个 ≥ 右沿 92% 的转折高点（30–150 根前）
            if used["cup_handle"] != bB and i - bB <= 30 and ci > pB and cp <= pB and hx(bB + 1, i - 1) <= pB:
                bA = -1; pA = 0.0
                for j in range(len(PH) - 2, -1, -1):
                    if bB - PH[j][0] > 150:
                        break
                    if PH[j][1] >= 0.92 * pB:
                        bA, pA = PH[j]
                        break
                if bA >= 0 and bB - bA >= 30 and pA <= 1.10 * pB:
                    seg = l[bA:bB + 1]
                    cb = seg.min(); kb = bA + int(np.argmin(seg))
                    m2 = min(pA, pB)
                    depth = (m2 - cb) / m2
                    frac = (kb - bA) / (bB - bA)
                    hl = lx(bB + 1, i)
                    if 0.12 <= depth <= 0.40 and 0.2 <= frac <= 0.8 and hl >= cb + 0.5 * (pB - cb) and (pB - hl) / pB <= 0.15 \
                            and lx(max(0, bA - 100), bA - 1) <= pA / 1.25:
                        fire("cup_handle", i, bB, bA)
            # 牛旗：10 根内涨 ≥15%（旗杆）到转折高点，之后 5–25 根回撤 ≤ 旗杆一半，收盘突破旗杆顶
            if used["bull_flag"] != bB and i - bB <= 25 and ci > pB and cp <= pB and hx(bB + 1, i - 1) <= pB:
                p0 = lx(max(0, bB - 10), bB)
                if pB / p0 - 1 >= 0.15 and (pB - lx(bB + 1, i)) / (pB - p0) <= 0.5:
                    s = max(0, bB - 10) + int(np.argmin(l[max(0, bB - 10):bB + 1]))
                    fire("bull_flag", i, bB, s)

        if len(PL) >= 1:
            bF, pF = PL[-1]
            if used["bear_flag"] != bF and i - bF <= 25 and ci < pF and cp >= pF and lx(bF + 1, i - 1) >= pF:
                p0 = hx(max(0, bF - 10), bF)
                if 1 - pF / p0 >= 0.15 and (hx(bF + 1, i) - pF) / (p0 - pF) <= 0.5:
                    s = max(0, bF - 10) + int(np.argmax(h[max(0, bF - 10):bF + 1]))
                    fire("bear_flag", i, bF, s)

    cs = pd.Series(c)
    c1 = cs.shift(1)
    hs, ls = pd.Series(h), pd.Series(l)
    tr = pd.concat([hs - ls, (hs - c1).abs(), (ls - c1).abs()], axis=1).max(axis=1)
    sma20, sma50, sma200 = cs.rolling(20).mean(), cs.rolling(50).mean(), cs.rolling(200).mean()
    vrel = pd.Series(v) / pd.Series(v).rolling(20).mean().shift(1)
    ctx = pd.DataFrame({"vrel": vrel, "atr": tr.rolling(14).mean().shift(1), "sma20": sma20, "sma50": sma50, "sma200": sma200,
                        "uptrend": (cs > sma50) & (sma50 > sma200) & (sma50 > sma50.shift(10)), "above200": cs > sma200})
    ctx.index = df.index
    P = {k: pd.Series(a, index=df.index) for k, a in out.items()}
    if spans:
        return P, ctx, start
    return P, ctx
