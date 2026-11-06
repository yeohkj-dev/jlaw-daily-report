"""K线形态识别器（向量化）。输入 DataFrame: o,h,l,c,v（按日期升序）。
每个形态返回布尔 Series，信号在当天收盘时成立。
定义参考常见教科书 + Bulkowski 的识别规则，并加上"前置趋势"条件。
"""
import numpy as np
import pandas as pd

# 形态元数据：中文名, 方向(+1 看涨 / -1 看跌 / 0 中性), 类别
META = {
    # 单根
    "hammer": ("锤子线", 1, "单根反转"),
    "inv_hammer": ("倒锤子", 1, "单根反转"),
    "dragonfly": ("蜻蜓十字", 1, "单根反转"),
    "shooting_star": ("射击之星", -1, "单根反转"),
    "hanging_man": ("上吊线", -1, "单根反转"),
    "gravestone": ("墓碑十字", -1, "单根反转"),
    "doji_up": ("上涨中十字星", -1, "单根反转"),
    "doji_down": ("下跌中十字星", 1, "单根反转"),
    "bull_marubozu": ("光头光脚大阳线", 1, "单根力量"),
    "bear_marubozu": ("光头光脚大阴线", -1, "单根力量"),
    # 两根
    "bull_engulf": ("看涨吞没", 1, "两根反转"),
    "bear_engulf": ("看跌吞没", -1, "两根反转"),
    "piercing": ("刺透形态", 1, "两根反转"),
    "dark_cloud": ("乌云盖顶", -1, "两根反转"),
    "bull_harami": ("看涨孕线", 1, "两根反转"),
    "bear_harami": ("看跌孕线", -1, "两根反转"),
    "tweezer_bottom": ("平底", 1, "两根反转"),
    "tweezer_top": ("平顶", -1, "两根反转"),
    "bull_kr": ("看涨关键反转日", 1, "两根反转"),
    "bear_kr": ("看跌关键反转日", -1, "两根反转"),
    # 三根
    "morning_star": ("早晨之星", 1, "三根反转"),
    "evening_star": ("黄昏之星", -1, "三根反转"),
    "three_soldiers": ("红三兵", 1, "三根反转"),
    "three_crows": ("三只乌鸦", -1, "三根反转"),
    "three_inside_up": ("三内升", 1, "三根反转"),
    "three_inside_down": ("三内降", -1, "三根反转"),
    "rising_three": ("上升三法", 1, "持续"),
    "falling_three": ("下降三法", -1, "持续"),
    # 结构 / 量价
    "inside_bar_up": ("上升趋势内包线", 1, "整理"),
    "nr7_up": ("上升趋势 NR7", 1, "整理"),
    "gap_up": ("向上跳空缺口", 1, "缺口"),
    "gap_down": ("向下跳空缺口", -1, "缺口"),
    "gap_go": ("放量跳空突破（≥4%、量≥2倍）", 1, "缺口"),
    "gap_crash": ("放量跳空下跌（≥4%、量≥2倍）", -1, "缺口"),
    "vol_breakout": ("放量突破 50 日高点（量≥2倍）", 1, "量价"),
    "novol_breakout": ("无量突破 50 日高点（量<1倍）", 1, "量价"),
    "failed_breakout": ("假突破（3 天内跌回）", -1, "量价"),
    "vol_breakdown": ("放量跌破 50 日低点（量≥2倍）", -1, "量价"),
    "pocket_pivot": ("口袋支点", 1, "量价"),
    "ma_pullback": ("回踩 20MA 反弹", 1, "量价"),
    "churning": ("高位放量滞涨", -1, "量价"),
    "stopping_vol": ("低位放量长下影", 1, "量价"),
    "dry_up": ("地量（50 日最低量）", 1, "量价"),
}


def detect(df: pd.DataFrame) -> dict:
    o, h, l, c, v = (df[k].astype(float) for k in "ohlcv")
    o1, h1, l1, c1, v1 = o.shift(1), h.shift(1), l.shift(1), c.shift(1), v.shift(1)
    o2, h2, l2, c2 = o.shift(2), h.shift(2), l.shift(2), c.shift(2)
    body = (c - o).abs(); rng = (h - l).replace(0, np.nan)
    upper = h - np.maximum(o, c); lower = np.minimum(o, c) - l
    body1, body2 = body.shift(1), body.shift(2)
    avgbody = body.rolling(10).mean().shift(1)
    tr = pd.concat([h - l, (h - c1).abs(), (l - c1).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().shift(1)
    sma20, sma50, sma200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    avgv = v.rolling(20).mean().shift(1)
    vrel = v / avgv
    bull, bear = c > o, c < o
    bull1, bear1, bear2, bull2 = bull.shift(1, fill_value=False), bear.shift(1, fill_value=False), bear.shift(2, fill_value=False), bull.shift(2, fill_value=False)
    # 前置趋势：前一天收盘低于 20MA 且低于 5 天前 = 下跌中；反之上涨中
    sma20_1 = sma20.shift(1)
    pre_down = (c1 < sma20_1) & (c1 < c.shift(6))
    pre_up = (c1 > sma20_1) & (c1 > c.shift(6))
    pre_down3 = (c.shift(3) < sma20.shift(3)) & (c.shift(3) < c.shift(8))
    pre_up3 = (c.shift(3) > sma20.shift(3)) & (c.shift(3) > c.shift(8))
    sized = rng > 0.6 * atr          # 排除波幅太小的K线
    long1 = body1 > avgbody          # 前一根是"长"实体
    hh50 = h.rolling(50).max().shift(1); ll50 = l.rolling(50).min().shift(1)
    hh20 = h.rolling(20).max().shift(1); ll20 = l.rolling(20).min().shift(1)
    uptrend = (c > sma50) & (sma50 > sma200) & (sma50 > sma50.shift(10))

    hammer_shape = (lower >= 2 * body) & (upper <= 0.1 * rng) & sized
    inv_shape = (upper >= 2 * body) & (lower <= 0.1 * rng) & sized
    doji = (body <= 0.1 * rng) & sized

    P = {}
    P["hammer"] = hammer_shape & pre_down
    P["hanging_man"] = hammer_shape & pre_up
    P["inv_hammer"] = inv_shape & pre_down
    P["shooting_star"] = inv_shape & pre_up
    P["dragonfly"] = doji & (upper <= 0.1 * rng) & (lower >= 0.6 * rng) & pre_down
    P["gravestone"] = doji & (lower <= 0.1 * rng) & (upper >= 0.6 * rng) & pre_up
    P["doji_up"] = doji & pre_up
    P["doji_down"] = doji & pre_down
    maru = (body >= 2 * avgbody) & (upper <= 0.05 * rng) & (lower <= 0.05 * rng)
    P["bull_marubozu"] = maru & bull
    P["bear_marubozu"] = maru & bear

    P["bull_engulf"] = pre_down & bear1 & bull & (o <= c1) & (c >= o1) & (body > body1)
    P["bear_engulf"] = pre_up & bull1 & bear & (o >= c1) & (c <= o1) & (body > body1)
    P["piercing"] = pre_down & bear1 & long1 & bull & (o < c1) & (c > (o1 + c1) / 2) & (c < o1)
    P["dark_cloud"] = pre_up & bull1 & long1 & bear & (o > c1) & (c < (o1 + c1) / 2) & (c > o1)
    P["bull_harami"] = pre_down & bear1 & long1 & bull & (o > c1) & (c < o1) & (body < 0.6 * body1)
    P["bear_harami"] = pre_up & bull1 & long1 & bear & (o < c1) & (c > o1) & (body < 0.6 * body1)
    tol = 0.05 * atr
    P["tweezer_bottom"] = pre_down & bear1 & bull & ((l - l1).abs() <= tol)
    P["tweezer_top"] = pre_up & bull1 & bear & ((h - h1).abs() <= tol)
    P["bull_kr"] = (l <= ll20) & (c > c1) & (c > h1)        # 创 20 日新低后收在前日最高价之上
    P["bear_kr"] = (h >= hh20) & (c < c1) & (c < l1)        # 创 20 日新高后收在前日最低价之下

    long2 = body2 > avgbody
    star_small = body1 < 0.3 * body2
    P["morning_star"] = pre_down3 & bear2 & long2 & star_small & (np.maximum(o1, c1) < c2) & bull & (c > (o2 + c2) / 2)
    P["evening_star"] = pre_up3 & bull2 & long2 & star_small & (np.minimum(o1, c1) > c2) & bear & (c < (o2 + c2) / 2)
    solid = lambda k: (body.shift(k) > 0.6 * avgbody.shift(k)) & (upper.shift(k) < 0.3 * body.shift(k))
    P["three_soldiers"] = pre_down3 & bull & bull1 & bull2 & solid(0) & solid(1) & solid(2) & (c > c1) & (c1 > c2) & \
        (o > o1) & (o <= c1) & (o1 > o2) & (o1 <= c2)
    solidb = lambda k: (body.shift(k) > 0.6 * avgbody.shift(k)) & (lower.shift(k) < 0.3 * body.shift(k))
    P["three_crows"] = pre_up3 & bear & bear1 & bear2 & solidb(0) & solidb(1) & solidb(2) & (c < c1) & (c1 < c2) & \
        (o < o1) & (o >= c1) & (o1 < o2) & (o1 >= c2)
    harami_b1 = P["bull_harami"].shift(1, fill_value=False)
    harami_s1 = P["bear_harami"].shift(1, fill_value=False)
    P["three_inside_up"] = harami_b1 & bull & (c > o2)
    P["three_inside_down"] = harami_s1 & bear & (c < o2)

    o4, h4, l4, c4 = o.shift(4), h.shift(4), l.shift(4), c.shift(4)
    long4 = body.shift(4) > avgbody.shift(4)
    inside3 = pd.Series(True, index=df.index)
    for k in (1, 2, 3):
        inside3 &= (h.shift(k) <= h4) & (l.shift(k) >= l4) & (body.shift(k) < 0.6 * body.shift(4))
    P["rising_three"] = (c4 > o4) & long4 & inside3 & bull & (c > c4) & (body > avgbody)
    P["falling_three"] = (c4 < o4) & long4 & inside3 & bear & (c < c4) & (body > avgbody)

    P["inside_bar_up"] = (h < h1) & (l > l1) & uptrend
    P["nr7_up"] = (rng == rng.rolling(7).min()) & uptrend
    gap_pct = o / c1 - 1
    P["gap_up"] = (l > h1) & (gap_pct > 0.01)
    P["gap_down"] = (h < l1) & (gap_pct < -0.01)
    P["gap_go"] = (gap_pct >= 0.04) & (vrel >= 2) & (l > h1)
    P["gap_crash"] = (gap_pct <= -0.04) & (vrel >= 2) & (h < l1)
    brk = (c > hh50) & (c.shift(1) <= hh50.shift(1))
    P["vol_breakout"] = brk & (vrel >= 2)
    P["novol_breakout"] = brk & (vrel < 1)
    brk_lvl = hh50.where(brk)
    lvl_recent = brk_lvl.shift(1).combine_first(brk_lvl.shift(2)).combine_first(brk_lvl.shift(3))
    P["failed_breakout"] = lvl_recent.notna() & (c < lvl_recent) & ~brk
    P["vol_breakdown"] = (c < ll50) & (c.shift(1) >= ll50.shift(1)) & (vrel >= 2)
    downv = v.where(c < c1, 0).rolling(10).max().shift(1)
    P["pocket_pivot"] = bull & (c > c1) & (v > downv) & (c > sma50) & ((c / sma20 - 1).abs() < 0.05)
    P["ma_pullback"] = uptrend & (l <= sma20 * 1.005) & (c > sma20) & bull & (c1 > sma20_1) & (c.shift(5) > sma20.shift(5) * 1.02)
    ret20 = c1 / c.shift(21) - 1
    P["churning"] = (c > sma50) & (ret20 > 0.10) & (vrel >= 2) & (body < 0.3 * rng) & ((c / c1 - 1).abs() < 0.01) & (h >= hh20 * 0.98)
    ret10 = c1 / c.shift(11) - 1
    P["stopping_vol"] = (ret10 < -0.08) & (vrel >= 2) & (lower >= 0.5 * rng) & (c > l + 0.5 * rng) & sized
    P["dry_up"] = (v == v.rolling(50).min()) & (c > sma50)

    ctx = pd.DataFrame({"vrel": vrel, "atr": atr, "sma20": sma20, "sma50": sma50, "sma200": sma200,
                        "uptrend": uptrend, "above200": c > sma200})
    return {k: s.fillna(False).astype(bool) for k, s in P.items()}, ctx
