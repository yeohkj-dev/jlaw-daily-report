"""数据挖掘：见 mine_feats.py 的说明。输出 mine.json。"""
import itertools, glob, json, os
import numpy as np, pandas as pd
from mine_feats import FEAT, feats, HERE, CACHE, bl, BIAS

rows = []
for f in glob.glob(os.path.join(CACHE, "*.json")):
    s = os.path.basename(f)[:-5]
    if s in ("SPY", "QQQ"):
        continue
    df = pd.DataFrame(json.load(open(f))).dropna()
    df = df[(df.h > df.l) & (df.v > 0) & (df.o > 0)].reset_index(drop=True)
    if len(df) < 300:
        continue
    F = feats(df)
    c, o = df.c, df.o
    ent = o.shift(-1)
    liquid = (c >= 5) & ((df.v * c).rolling(20).mean() >= 5e6)
    for k in (20, 60):
        cap = 0.8 if k == 60 else 0.5
        F[f"x{k}"] = np.clip(c.shift(-k) / ent - 1 - df.d.map(bl[f"r{k}"]), -cap, cap) - BIAS[f"{k}_all"] / 100
    F["d"] = df.d
    m = liquid & (np.arange(len(df)) >= 252) & F.x20.notna()
    rows.append(F[m].dropna(subset=list(FEAT)))
A = pd.concat(rows, ignore_index=True)
for k in FEAT:
    A[k] = A[k].astype(np.int8)
A["oos"] = A.d >= "2025-01-01"
A["mon"] = A.d.str[:7]
print("bars", len(A), "IS", int((~A.oos).sum()), "OOS", int(A.oos.sum()))

res = []
names = list(FEAT)
for r_ in (1, 2, 3):
    for combo in itertools.combinations(names, r_):
        g = A.groupby(list(combo))
        st = g.agg(n=("x20", "size"), x20=("x20", "mean"), sd=("x20", "std"), x60=("x60", "mean"), months=("mon", "nunique"))
        gi = A[~A.oos].groupby(list(combo)).agg(ni=("x20", "size"), xi=("x20", "mean"))
        go = A[A.oos].groupby(list(combo)).agg(no=("x20", "size"), xo=("x20", "mean"))
        st = st.join(gi).join(go)
        st = st[(st.ni >= 1500) & (st.no >= 600) & (st.months >= 12)]
        ok = (np.sign(st.xi) == np.sign(st.xo)) & (st.xi.abs() >= 0.006) & (st.xo.abs() >= 0.004)
        for key, r in st[ok].iterrows():
            key = key if isinstance(key, tuple) else (key,)
            res.append({"feat": combo, "bins": [int(x) for x in key],
                        "desc": "；".join(f"{FEAT[f][0]} = {FEAT[f][2][b]}" for f, b in zip(combo, key)),
                        "n": int(r.n), "x20": round(r.x20 * 100, 2), "x60": round(r.x60 * 100, 2), "xi": round(r.xi * 100, 2),
                        "xo": round(r.xo * 100, 2), "ni": int(r.ni), "no": int(r.no), "months": int(r.months),
                        "t": round(r.x20 / (r.sd / np.sqrt(r.n)), 1)})
res.sort(key=lambda x: -abs(x["xo"]) * min(1, x["no"] / 3000))
json.dump({"bars": int(len(A)), "found": res}, open(os.path.join(HERE, "mine.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("通过样本外验证的组合：", len(res))
for x in res[:40]:
    print(f"{x['x20']:+.2f} | IS {x['xi']:+.2f} OOS {x['xo']:+.2f} | 60d {x['x60']:+.2f} | n {x['n']} | {x['desc']}")
