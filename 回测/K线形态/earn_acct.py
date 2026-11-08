"""财报前要不要卖：账户回测（⭐ 版本 = META + RS≥90 + SPY>200 天线才买 + 收盘跌 8% 卖 + 拿 60 天，没持股的钱放 QQQ）。
A 照拿（财报照过）/ B 财报前一天收盘全卖 / D 信号后 14 天内有财报就不买。随机挑 10 次，分全期、2006–2015、2016–2026。
要先跑 回测/earn_fetch.py（财报日）、回测/earn_test.py（逐笔）。输出 earn_acct20.json。"""
import os, sys, json
os.environ["BT_TAG"] = "20"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
from multiprocessing import Pool
import numpy as np, pandas as pd
PER = {"all": {}, "h1": dict(end="2015-12-31"), "h2": dict(start="2016-01-04")}


def tr(key):
    X = pd.read_pickle(os.path.join(HERE, "..", "earn_trades20.pkl"))
    X = X[X.mkt]
    if key == "D":
        X = X[~X.soon14]
    m = "B" if key == "B" else "A"
    return pd.DataFrame({"sym": X.sym, "mod": "M", "ed": X.ed, "xd": X[m + "_xd"], "r": X[m], "entry": X.entry, "sd": 0.08, "gap": 0.0, "sig": X.d})


def job(a):
    key, per, seed = a
    import system_bt as S
    r = S.run(priority="random", seed=seed, cash_spy=True, trades=tr(key), risk=0.01, maxpos=10, base="QQQ", **PER[per])
    return key, per, float(r["sys"]["cagr"]), float(r["sys"]["maxdd"]), float(r["spy"]["cagr"])


if __name__ == "__main__":
    jobs = [(k, p, s) for k in "ABD" for p in PER for s in range(10)]
    res = {}
    with Pool(2) as pool:
        for k, p, c, dd, b in pool.imap_unordered(job, jobs):
            res.setdefault((k, p), []).append((c, dd, b))
    out = {}
    for (k, p), v in sorted(res.items()):
        c = [x[0] for x in v]
        out[f"{k}|{p}"] = {"cagr": float(np.median(c)), "lo": float(np.percentile(c, 10)), "hi": float(np.percentile(c, 90)),
                           "maxdd": float(np.median([x[1] for x in v])), "bench": v[0][2], "beat": sum(x[0] > x[2] for x in v)}
        print(k, p, out[f"{k}|{p}"])
    json.dump(out, open(os.path.join(HERE, "earn_acct20.json"), "w"))
