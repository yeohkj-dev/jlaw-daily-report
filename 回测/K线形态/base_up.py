"""对照组：同一段时间、任何一天买任何一只（流动性够的）股票，20 / 60 天后上涨的比例；按 SPY 是否在 200MA 上分开。
期间 = stats{TAG}.json 的信号日范围。输出 base_up{TAG}.json"""
import glob, json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = os.environ.get("BT_TAG", "")
CACHE = os.path.join(HERE, "..", "cache" + TAG)
info = json.load(open(os.path.join(HERE, f"stats{TAG}.json"), encoding="utf-8"))["info"]
S0, S1 = info["start"], info["end"]
spy = pd.DataFrame(json.load(open(os.path.join(CACHE, "SPY.json")))).dropna()
spy["a"] = spy.c > spy.c.rolling(200).mean()
A = dict(zip(spy.d, spy.a))
acc = {"all": [0, 0, 0], "bull": [0, 0, 0], "bear": [0, 0, 0]}
for f in sorted(glob.glob(os.path.join(CACHE, "*.json"))):
    s = os.path.basename(f)[:-5]
    if s in ("SPY", "QQQ"):
        continue
    df = pd.DataFrame(json.load(open(f))).dropna()
    df = df[(df.h > df.l) & (df.v > 0) & (df.o > 0)].reset_index(drop=True)
    if len(df) < 260:
        continue
    o, c, d = df.o.values, df.c.values, df.d.values
    liq = ((df.c >= 5) & ((df.v * df.c).rolling(20).mean() >= 5e6)).values
    idx = np.arange(200, len(df) - 61)
    idx = idx[liq[idx] & (d[idx] >= S0) & (d[idx] <= S1)]
    if not len(idx):
        continue
    m = np.array([A.get(x, True) for x in d[idx]])
    u20 = c[idx + 20] / o[idx + 1] > 1
    u60 = c[idx + 60] / o[idx + 1] > 1
    for k, sel in (("all", np.ones(len(idx), bool)), ("bull", m), ("bear", ~m)):
        acc[k][0] += int(u20[sel].sum()); acc[k][1] += int(u60[sel].sum()); acc[k][2] += int(sel.sum())
out = {"up20": round(100 * acc["all"][0] / acc["all"][2], 1), "up60": round(100 * acc["all"][1] / acc["all"][2], 1), "n": acc["all"][2],
       "bull": {"up20": round(100 * acc["bull"][0] / acc["bull"][2], 1), "up60": round(100 * acc["bull"][1] / acc["bull"][2], 1), "n": acc["bull"][2]},
       "bear": {"up20": round(100 * acc["bear"][0] / acc["bear"][2], 1), "up60": round(100 * acc["bear"][1] / acc["bear"][2], 1), "n": acc["bear"][2]},
       "start": S0, "end": S1}
json.dump(out, open(os.path.join(HERE, f"base_up{TAG}.json"), "w"))
print(out)
