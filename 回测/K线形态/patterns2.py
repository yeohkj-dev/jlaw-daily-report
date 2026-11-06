"""第二批形态（上次没测到的）：Bulkowski 排名靠前的K线形态 + 交易者常用设置 + 用户在用的 Luk Inside Day。
接口同 patterns.detect：返回 ({名: 布尔Series}, ctx)。"""
import numpy as np
import pandas as pd

META2 = {
    # Bulkowski 排名靠前 / 常见但上次没测
    "tls_bear": ("看跌三线打击（3 阴后 1 根大阳全吞）", 1, "K线"),   # Bulkowski：实际是看涨反转 84%
    "tls_bull": ("看涨三线打击（3 阳后 1 根大阴全吞）", -1, "K线"),  # Bulkowski：实际是看跌反转 65%
    "kicker_bull": ("看涨踢脚线", 1, "K线"),
    "kicker_bear": ("看跌踢脚线", -1, "K线"),
    "belt_bull": ("看涨捉腰带线", 1, "K线"),
    "belt_bear": ("看跌捉腰带线", -1, "K线"),
    "tasuki_up": ("上升跳空并列阴阳线（Tasuki）", 1, "K线"),
    "two_black_gap": ("向下跳空两只乌鸦（Two Black Gapping）", -1, "K线"),
    "matching_low": ("平低收盘（Matching Low）", 1, "K线"),
    "on_neck": ("颈上线 / 颈内线 / 插入线", -1, "K线"),
    "advance_block": ("前方受阻（红三兵变弱）", -1, "K线"),
    "high_wave": ("高浪线（长上下影小实体）", 0, "K线"),
    "island_top": ("岛形顶", -1, "K线"),
    "island_bottom": ("岛形底", 1, "K线"),
    # 交易者常用设置
    "hi52_break": ("首次收盘创 52 周新高", 1, "设置"),
    "lo52_break": ("首次收盘创 52 周新低", -1, "设置"),
    "rsi2_os_up": ("RSI(2) < 5 且在 200MA 上（Connors 回调买）", 1, "设置"),
    "rsi2_ob_dn": ("RSI(2) > 95 且在 200MA 下", -1, "设置"),
    "three_down_up": ("上升趋势中连跌 3 天", 1, "设置"),
    "five_up": ("连涨 5 天", -1, "设置"),
    "power_day": ("大波幅收在最高位（波幅 ≥2 ATR、收在上 20%）", 1, "设置"),
    "flush_day": ("大波幅收在最低位（波幅 ≥2 ATR、收在下 20%）", -1, "设置"),
    "oops_bull": ("Oops 反转（低开破前低后收回）", 1, "设置"),
    "oops_bear": ("Oops 反转（高开破前高后跌回）", -1, "设置"),
    "tight_near_high": ("新高附近窄幅整理（10 日波幅 < 50 日的 35%）", 1, "设置"),
    "bb_squeeze_up": ("布林带收窄到半年最窄（上升趋势）", 1, "设置"),
    "power_gap": ("强力财报跳空（≥10%、量≥3倍、收在上半）", 1, "设置"),
    "luk_id": ("Luk Inside Day 设置（照用户 Pine 条件）", 1, "设置"),
}


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def detect2(df):
    o, h, l, c, v = (df[k].astype(float) for k in "ohlcv")
    sh = lambda s, k=1: s.shift(k)
    body = (c - o).abs(); rng = (h - l).replace(0, np.nan)
    upper = h - np.maximum(o, c); lower = np.minimum(o, c) - l
    avgbody = body.rolling(10).mean().shift(1)
    c1 = sh(c)
    tr = pd.concat([h - l, (h - c1).abs(), (l - c1).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().shift(1)
    sma20, sma50, sma200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    avgv = v.rolling(20).mean().shift(1); vrel = v / avgv
    bull, bear = c > o, c < o
    B = lambda k: bull.shift(k, fill_value=False); S = lambda k: bear.shift(k, fill_value=False)
    pre_down = (c1 < sma20.shift(1)) & (c1 < c.shift(6))
    pre_up = (c1 > sma20.shift(1)) & (c1 > c.shift(6))
    pre_down3 = (c.shift(3) < sma20.shift(3)) & (c.shift(3) < c.shift(8))
    pre_up3 = (c.shift(3) > sma20.shift(3)) & (c.shift(3) > c.shift(8))
    longb = body > avgbody
    uptrend = (c > sma50) & (sma50 > sma200) & (sma50 > sma50.shift(10))
    P = {}
    # 三线打击
    P["tls_bear"] = S(1) & S(2) & S(3) & (sh(c, 1) < sh(c, 2)) & (sh(c, 2) < sh(c, 3)) & bull & (o <= sh(c, 1)) & (c >= sh(o, 3)) & pre_down3
    P["tls_bull"] = B(1) & B(2) & B(3) & (sh(c, 1) > sh(c, 2)) & (sh(c, 2) > sh(c, 3)) & bear & (o >= sh(c, 1)) & (c <= sh(o, 3)) & pre_up3
    # 踢脚线：前一根长阴，今天跳空高于前一根开盘的长阳（反之亦然）
    P["kicker_bull"] = S(1) & (sh(body) > sh(avgbody)) & bull & longb & (o > sh(o)) & (l > sh(h))
    P["kicker_bear"] = B(1) & (sh(body) > sh(avgbody)) & bear & longb & (o < sh(o)) & (h < sh(l))
    # 捉腰带线：开在最低（最高），长实体
    P["belt_bull"] = pre_down & bull & (body > 1.5 * avgbody) & (lower <= 0.02 * rng) & (o < c1)
    P["belt_bear"] = pre_up & bear & (body > 1.5 * avgbody) & (upper <= 0.02 * rng) & (o > c1)
    # 上升跳空并列：阳、跳空阳、阴开在第二根实体内并收在缺口内但不补满
    P["tasuki_up"] = B(2) & B(1) & (sh(l, 1) > sh(h, 2)) & bear & (o < sh(c, 1)) & (o > sh(o, 1)) & (c < sh(o, 1)) & (c > sh(h, 2)) & pre_up3
    P["two_black_gap"] = (sh(h, 1) < sh(l, 2)) & S(1) & bear & (c < sh(c, 1)) & pre_up3
    P["matching_low"] = pre_down & S(1) & bear & (sh(body) > sh(avgbody)) & ((c - c1).abs() <= 0.002 * c)
    # 颈上/颈内/插入线：下跌中长阴，次日低开阳线收在前阴中点以下
    P["on_neck"] = pre_down & S(1) & (sh(body) > sh(avgbody)) & bull & (o < sh(l)) & (c >= sh(l)) & (c < (sh(o) + sh(c)) / 2)
    # 前方受阻：三连阳但实体缩小、上影变长
    P["advance_block"] = B(0) & B(1) & B(2) & (c > c1) & (c1 > sh(c, 2)) & (body < sh(body)) & (sh(body) < sh(body, 2)) & \
        (upper > sh(upper)) & (upper > 0.5 * body) & pre_up3
    P["high_wave"] = (body <= 0.15 * rng) & (upper >= 0.35 * rng) & (lower >= 0.35 * rng) & (rng > atr)
    # 岛形反转：k 天前跳空（2–10 天），今天反向跳空，中间的K线全部在两个缺口之外
    it = pd.Series(False, index=df.index); ib = pd.Series(False, index=df.index)
    for k in range(2, 11):
        mid_lo = l.shift(1).rolling(k).min(); mid_hi = h.shift(1).rolling(k).max()
        gap_up_k = sh(l, k) > sh(h, k + 1)          # k 天前跳空向上
        it |= gap_up_k & (h < mid_lo) & (sh(h, k + 1) < mid_lo) & (l.shift(k) > sh(h, k + 1))
        gap_dn_k = sh(h, k) < sh(l, k + 1)
        ib |= gap_dn_k & (l > mid_hi) & (sh(l, k + 1) > mid_hi)
    P["island_top"] = it; P["island_bottom"] = ib
    # 设置
    hi252 = c.rolling(252, min_periods=200).max(); lo252 = c.rolling(252, min_periods=200).min()
    P["hi52_break"] = (c >= hi252) & (c.shift(1).rolling(20).max() < hi252.shift(1))
    P["lo52_break"] = (c <= lo252) & (c.shift(1).rolling(20).min() > lo252.shift(1))
    d = c.diff(); up = d.clip(lower=0); dn = (-d).clip(lower=0)
    rs = up.ewm(alpha=1 / 2, adjust=False).mean() / dn.ewm(alpha=1 / 2, adjust=False).mean().replace(0, np.nan)
    rsi2 = 100 - 100 / (1 + rs)
    P["rsi2_os_up"] = (rsi2 < 5) & (c > sma200)
    P["rsi2_ob_dn"] = (rsi2 > 95) & (c < sma200)
    dd = c < c1
    P["three_down_up"] = dd & dd.shift(1, fill_value=False) & dd.shift(2, fill_value=False) & ~dd.shift(3, fill_value=True) & uptrend
    uu = c > c1
    P["five_up"] = uu & uu.shift(1, fill_value=False) & uu.shift(2, fill_value=False) & uu.shift(3, fill_value=False) & uu.shift(4, fill_value=False) & ~uu.shift(5, fill_value=True)
    clv = (c - l) / rng
    P["power_day"] = (rng >= 2 * atr) & (clv >= 0.8) & bull
    P["flush_day"] = (rng >= 2 * atr) & (clv <= 0.2) & bear
    P["oops_bull"] = (o < sh(l)) & (c > sh(l)) & pre_down
    P["oops_bear"] = (o > sh(h)) & (c < sh(h)) & pre_up
    r10 = h.rolling(10).max() - l.rolling(10).min(); r50 = h.rolling(50).max() - l.rolling(50).min()
    P["tight_near_high"] = (r10 < 0.35 * r50) & (c >= 0.9 * h.rolling(252, min_periods=200).max()) & uptrend & \
        ~((r10.shift(1) < 0.35 * r50.shift(1)))
    sd = c.rolling(20).std(); bw = 4 * sd / sma20
    P["bb_squeeze_up"] = (bw <= bw.rolling(126).min()) & uptrend & ~(bw.shift(1) <= bw.shift(1).rolling(126).min())
    gap = o / c1 - 1
    P["power_gap"] = (gap >= 0.10) & (vrel >= 3) & (clv >= 0.5)
    # Luk Inside Day（照 luk_inside_day_setup.pine 默认参数）
    e9, e21, e50 = ema(c, 9), ema(c, 21), ema(c, 50)
    adr = 100 * ((h / l).rolling(20).mean() - 1)
    dolv = (c * v).rolling(20).mean() / 1e6
    gain = lambda n: (c / l.rolling(n).min() - 1) * 100
    mom = np.maximum(np.maximum(gain(21), gain(63)), gain(126)) >= 30
    spread = (np.maximum(np.maximum(e9, e21), e50) - np.minimum(np.minimum(e9, e21), e50)) / c * 100
    stop = (h - l) / h * 100
    inside = (h < sh(h)) & (l > sh(l))
    P["luk_id"] = inside & (c > e21) & (e21 > e50) & (e50 > e50.shift(5)) & mom & (adr >= 5) & (dolv >= 20) & (spread <= 4) & \
        (stop <= 5) & (stop <= adr / 2)
    ctx = pd.DataFrame({"vrel": vrel, "atr": atr, "sma20": sma20, "sma50": sma50, "sma200": sma200,
                        "uptrend": uptrend, "above200": c > sma200})
    return {k: s.fillna(False).astype(bool) for k, s in P.items()}, ctx
