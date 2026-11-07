"""每天的 RS Rating（1–99），公式同 jlaw-daily-report/tools/rs_rating.py：
分数 = 2×c/c[63] + c/c[126] + c/c[189] + c/c[252]（按每只股票自己的交易日往回数），每天在所有有分数的股票里排百分位，
门槛 = 第 1..99 百分位（numpy 线性插值），评分 = 门槛 ≤ 分数的个数，夹在 1..99。
数据 BT_TAG=20 → cache20。输出 rs_hist{TAG}.pkl（日期 × 股票，int8，没有分数 = 0）。"""
import glob, json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = os.environ.get("BT_TAG", "20")
CACHE = os.path.join(HERE, "..", "cache" + TAG)
cols = {}
for f in sorted(glob.glob(os.path.join(CACHE, "*.json"))):
    s = os.path.basename(f)[:-5]
    if s in ("SPY", "QQQ"):
        continue
    d = pd.DataFrame(json.load(open(f))).dropna(subset=["c"])
    d = d[d.c > 0]
    c = d.c.astype(float).values
    if len(c) < 260:
        continue
    sc = np.full(len(c), np.nan)
    sc[252:] = 2 * c[252:] / c[189:-63] + c[252:] / c[126:-126] + c[252:] / c[63:-189] + c[252:] / c[:-252]
    cols[s] = pd.Series(sc, index=d.d.values)
S = pd.DataFrame(cols).sort_index()
S = S[~S.index.duplicated()]
R = np.zeros(S.shape, dtype=np.int8)
vals = S.values
for i in range(len(S)):
    x = vals[i]; m = ~np.isnan(x)
    if m.sum() < 100:
        continue
    th = np.percentile(x[m], np.arange(1, 100))
    r = np.searchsorted(th, x[m], side="right")
    R[i, m] = np.clip(r, 1, 99)
out = pd.DataFrame(R, index=S.index, columns=S.columns)
out.to_pickle(os.path.join(HERE, f"rs_hist{TAG}.pkl"))
print(out.shape, out.index[0], out.index[-1], "有评分的股票数（最后一天）", int((out.iloc[-1] > 0).sum()))
