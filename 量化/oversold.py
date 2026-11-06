"""已经深跌（低于 20 日线 >20%）的前强势股：马上卖 vs 等反弹？看之后 5/20/60 天表现。"""
import json, os, glob, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
C = {}
for f in glob.glob(os.path.join(DATA, "stocks", "*.json")):
    d = json.load(open(f)); s = pd.Series(d["c"], index=pd.to_datetime(d["d"]), dtype=float); C[os.path.basename(f)[:-5]] = s[~s.index.duplicated()]
C = pd.DataFrame(C).sort_index()
m20, m200 = C.rolling(20).mean(), C.rolling(200).mean()
was_strong = (C.shift(25) > m200.shift(25)) & (C.shift(25) / C.shift(277) - 1 > 0.5)   # 一个月前还是强势股（年涨 >50%）
cond = (C / m20 - 1 < -0.20) & was_strong
first = cond & ~cond.shift(1, fill_value=False)
out = {}
for h in [5, 20, 60]:
    fwd = C.shift(-h) / C - 1
    mn = C[::-1].rolling(h, min_periods=1).min()[::-1].shift(-1) / C - 1
    mx = C[::-1].rolling(h, min_periods=1).max()[::-1].shift(-1) / C - 1
    v, lo, hi = fwd[first].stack(), mn[first].stack(), mx[first].stack()
    out[h] = dict(n=int(v.size), avg=float(v.mean()), med=float(v.median()), up=float((v > 0).mean()),
                  worse10=float((lo < -0.10).mean()), bounce10=float((hi > 0.10).mean()))
    print(h, out[h])
json.dump(out, open(os.path.join(DATA, "oversold.json"), "w"))
