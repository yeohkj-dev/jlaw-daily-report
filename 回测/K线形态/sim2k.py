"""本金 US$2,000 的账户模拟（20 年数据，BT_TAG=20）：放量突破（跌 15% 才卖，拿 20 / 60 天） vs J Law META（原版 5R、2:1 目标、收盘跌 8% 拿 60 天）。
假设：每张单手续费 US$1（买卖个股时，没持股的钱放在 SPY，所以要先卖 SPY 再买股票 = 每次 2 张单）；可买零股；最少下单 US$50；
仓位两种：A「每笔最多亏账户 1%」（买入 = 账户 × 1% ÷ 止损距离，单只最多 20%，最多 10 只）、B「每笔固定账户 20%，最多 5 只」。
每个方案随机挑 10 次（同一天信号太多只能挑几只）。输出 sim2k.json。"""
import json, os, sys
from multiprocessing import Pool
import numpy as np
import pandas as pd

os.environ.setdefault("BT_TAG", "20")
HERE = os.path.dirname(os.path.abspath(__file__))
CAP, MINPOS, SEEDS = 2000.0, 50.0, 10
FEE = float(os.environ.get("SIM_FEE", "1"))          # 每张单手续费
CASHSPY = os.environ.get("SIM_SPY", "1") == "1"      # 1 = 没持股的钱放 SPY（每次多 2 张单）；0 = 留现金
SIZINGS = os.environ.get("SIM_SIZING", "risk1,fix20").split(",")


def trades(key):
    import system_bt as S
    T = S.T; B = T[T.setup == "B"]
    M = pd.read_pickle(os.path.join(HERE, "..", "meta_trades20.pkl"))
    mk = lambda df, m, sd, mod: pd.DataFrame({"sym": df.sym, "mod": mod, "ed": df.ed, "xd": df[m + "_xd"], "r": df[m], "entry": df.entry, "sd": sd, "gap": 0.0, "sig": df.d})
    if key in ("MRS90C8", "BRS90"):
        MR = pd.read_pickle(os.path.join(HERE, "..", "meta_trades20_rs.pkl"))
        BR = B.merge(pd.read_pickle(os.path.join(HERE, "b_rs20.pkl")), on=["sym", "d"])
        return mk(MR[MR.rs >= 90], "C8", 0.08, "M") if key == "MRS90C8" else mk(BR[BR.rs >= 90], "E19", 0.15, "B")
    return {"B20": mk(B, "E45", 0.15, "B"), "B60": mk(B, "E19", 0.15, "B"), "MJ": mk(M, "J5R", M.risk, "M"),
            "MRR2": mk(M, "RR2M", M.risk, "M"), "MC8": mk(M, "C8", 0.08, "M")}[key]


def job(args):
    key, sizing, period, seed = args
    import system_bt as S
    kw = dict(risk=0.01, maxpos=10) if sizing == "risk1" else dict(fixed=0.20, maxpos=5)
    kw.update({"full": {}, "10y": dict(start="2016-01-04")}[period])
    r = S.run(priority="random", seed=seed, cash_spy=CASHSPY, trades=trades(key), capital=CAP, fee=FEE, min_pos=MINPOS, **kw)
    yrs = (pd.Timestamp(r["curve"]["d"][-1]) - pd.Timestamp(r["curve"]["d"][0])).days / 365.25
    return key, sizing, period, seed, {"final": round(CAP * (1 + r["sys"]["total"] / 100), 0), "cagr": r["sys"]["cagr"], "maxdd": r["sys"]["maxdd"],
                                       "n": r["n"], "per_year": round(r["n"] / yrs, 1), "win": r["win"], "fees": round(r["n"] * (4 if CASHSPY else 2) * FEE, 0),
                                       "spy_final": round(CAP * (1 + r["spy"]["total"] / 100) - FEE, 0), "spy_cagr": r["spy"]["cagr"], "spy_maxdd": r["spy"]["maxdd"],
                                       "curve_d": r["curve"]["d"], "curve": [round(CAP * v, 0) for v in r["curve"]["sys"]], "spy_curve": [round(CAP * v, 0) for v in r["curve"]["spy"]]}


if __name__ == "__main__":
    KEYS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["B20", "B60", "MJ", "MRR2", "MC8"]
    OUTF = os.path.join(HERE, sys.argv[2] if len(sys.argv) > 2 else "sim2k.json")
    jobs = [(k, s, p, sd) for k in KEYS for s in SIZINGS for p in ("full", "10y") for sd in range(SEEDS)]
    out = {}
    with Pool(2) as pool:
        for k, s, p, sd, res in pool.imap_unordered(job, jobs):
            out.setdefault(f"{k}|{s}|{p}", {})[sd] = res
    summ = {}
    for key, runs in out.items():
        v = list(runs.values()); fin = np.array([x["final"] for x in v])
        med = sorted(v, key=lambda x: x["final"])[len(v) // 2]
        summ[key] = {"final": np.percentile(fin, [10, 50, 90]).round(0).tolist(), "cagr": float(np.median([x["cagr"] for x in v])),
                     "maxdd": float(np.median([x["maxdd"] for x in v])), "per_year": float(np.median([x["per_year"] for x in v])),
                     "win": float(np.median([x["win"] for x in v])), "fees": float(np.median([x["fees"] for x in v])),
                     "beat": int(sum(x["final"] > x["spy_final"] for x in v)), "spy_final": v[0]["spy_final"], "spy_cagr": v[0]["spy_cagr"],
                     "spy_maxdd": v[0]["spy_maxdd"], "curve_d": med["curve_d"][::5], "curve": med["curve"][::5], "spy_curve": med["spy_curve"][::5]}
        print(key, summ[key]["final"], "年化", summ[key]["cagr"], "回撤", summ[key]["maxdd"], "每年", summ[key]["per_year"], "笔 胜", summ[key]["win"],
              "手续费", summ[key]["fees"], "赢SPY", summ[key]["beat"], "/", len(v), "| SPY", summ[key]["spy_final"], summ[key]["spy_cagr"], flush=True)
    json.dump(summ, open(OUTF, "w", encoding="utf-8"), ensure_ascii=False)
