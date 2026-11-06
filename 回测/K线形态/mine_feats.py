"""数据挖掘的特征定义（mine.py 与 build_data.py 共用）。原说明：数据挖掘：不预设形态名字，把每根K线拆成 10 个离散特征，穷举 2、3 个特征的组合，
找 20 天超额稳定的组合。防过拟合：2022-08→2024-12 为样本内（找），2025-01→2026-10 为样本外（验证）。
输出 mine.json。"""
import glob, itertools, json, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(HERE, "..", "cache")
bl = pd.read_pickle(os.path.join(HERE, "baseline.pkl"))
BIAS = json.load(open(os.path.join(HERE, "bias.json")))
spy = pd.DataFrame(json.load(open(os.path.join(CACHE, "SPY.json"))))
reg = dict(zip(spy.d, (spy.c > spy.c.rolling(200).mean()).astype(int)))

FEAT = {  # 名称: (中文, 分箱边界, 各箱标签)
    "clv": ("收盘在当日波幅的位置", [-.01, .2, .4, .6, .8, 1.01], ["最低 20%", "20–40%", "中间", "60–80%", "最高 20%"]),
    "rng": ("当日波幅/ATR", [0, .6, 1.2, 2, 99], ["很窄 <0.6", "正常", "偏大 1.2–2", "巨大 >2"]),
    "vol": ("量比（vs 20 日均量）", [0, .7, 1.3, 2, 3, 999], ["缩量 <0.7", "正常", "放量 1.3–2", "大量 2–3", "巨量 >3"]),
    "r1": ("当日涨跌", [-9, -.05, -.02, 0, .02, .05, 9], ["跌 >5%", "跌 2–5%", "跌 0–2%", "涨 0–2%", "涨 2–5%", "涨 >5%"]),
    "gap": ("开盘跳空", [-9, -.02, -.005, .005, .02, 9], ["低开 >2%", "低开 0.5–2%", "平开", "高开 0.5–2%", "高开 >2%"]),
    "tr": ("趋势位置", None, ["50MA 与 200MA 之上", "200MA 上、50MA 下", "200MA 下、50MA 上", "两线之下"]),
    "p52": ("距 52 周高点", [-9, -.30, -.15, -.05, 9], ["跌 >30%", "跌 15–30%", "跌 5–15%", "5% 以内"]),
    "m20": ("前 20 天涨跌", [-9, -.15, -.05, .05, .15, 9], ["跌 >15%", "跌 5–15%", "±5%", "涨 5–15%", "涨 >15%"]),
    "stk": ("连涨/连跌", None, ["连跌 ≥3", "连跌 2", "跌 1", "涨 1", "连涨 2", "连涨 ≥3"]),
    "mkt": ("大盘（SPY vs 200MA）", None, ["熊市", "牛市"]),
}


def feats(df):
    o, h, l, c, v = (df[k].astype(float) for k in "ohlcv")
    c1 = c.shift(1); rng = (h - l).replace(0, np.nan)
    tr_ = pd.concat([h - l, (h - c1).abs(), (l - c1).abs()], axis=1).max(axis=1); atr = tr_.rolling(14).mean().shift(1)
    s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
    cut = lambda x, b: pd.cut(x, b, labels=False)
    F = pd.DataFrame({
        "clv": cut((c - l) / rng, FEAT["clv"][1]), "rng": cut(rng / atr, FEAT["rng"][1]),
        "vol": cut(v / v.rolling(20).mean().shift(1), FEAT["vol"][1]), "r1": cut(c / c1 - 1, FEAT["r1"][1]),
        "gap": cut(o / c1 - 1, FEAT["gap"][1]),
        "tr": np.select([(c > s50) & (c > s200), (c <= s50) & (c > s200), (c > s50) & (c <= s200)], [0, 1, 2], 3),
        "p52": cut(c / h.rolling(252, min_periods=200).max() - 1, FEAT["p52"][1]),
        "m20": cut(c1 / c.shift(21) - 1, FEAT["m20"][1]),
    })
    up = (c > c1).astype(int) - (c < c1).astype(int)
    run = up.groupby((up != up.shift()).cumsum()).cumcount() + 1
    sk = (up * run).clip(-3, 3)
    F["stk"] = sk.map({-3: 0, -2: 1, -1: 2, 1: 3, 2: 4, 3: 5})
    F["mkt"] = df.d.map(reg)
    return F


