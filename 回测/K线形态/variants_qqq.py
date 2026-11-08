"""META + RS 系统的改进测试 + 跟 QQQ 比（20 年数据 2006–2026，BT_TAG=20）。
逐笔来自 回测/meta_more20.pkl（meta_more.py）。账户规则同 rs_sys20：每笔最多亏账户 1%、单只最多 20%、最多 10 只、没持股的钱放基准 ETF、
同一天信号太多随机挑（10 个种子）。base = SPY 或 QQQ（钱放哪只 + 跟哪只比）。分全期、2006–2015、2016–2026。
输出 variants_qqq20.json。"""
import json, os
from multiprocessing import Pool
import numpy as np
import pandas as pd

os.environ.setdefault("BT_TAG", "20")
HERE = os.path.dirname(os.path.abspath(__file__))
SEEDS = 10
# key: (标签, RS 下限, 只在 SPY>200 天线时买, 卖法, 止损距离, 按 RS 高先买)
CONF = {
    "base":   ("原版：RS ≥ 90 + 收盘跌 8% 卖 + 拿 60 天", 90, False, "C8", 0.08, False),
    "m200":   ("+ 只在 SPY 站上 200 天线时买", 90, True, "C8", 0.08, False),
    "rs95":   ("RS 改成 ≥ 95", 95, False, "C8", 0.08, False),
    "rs95m":  ("RS ≥ 95 + 只在 SPY 站上 200 天线时买", 95, True, "C8", 0.08, False),
    "prio":   ("同一天太多信号：RS 高的先买", 90, False, "C8", 0.08, True),
    "t50":    ("拿满 60 天后还在 50 天线上就继续拿", 90, False, "C8T50", 0.08, False),
    "t50m":   ("50 天线续拿 + 只在 SPY 站上 200 天线时买", 90, True, "C8T50", 0.08, False),
    "c10":    ("收盘跌 10% 才卖", 90, False, "C10", 0.10, False),
    "c12":    ("收盘跌 12% 才卖", 90, False, "C12", 0.12, False),
}
PER = {"all": {}, "h1": dict(end="2015-12-31"), "h2": dict(start="2016-01-04")}


def trades(key):
    _, lo, m200, ex, sd, prio = CONF[key]
    T = pd.read_pickle(os.path.join(HERE, "..", "meta_more20.pkl"))
    g = T[(T.rs >= lo) & (T.mkt if m200 else True)]
    return pd.DataFrame({"sym": g.sym, "mod": "M", "ed": g.ed, "xd": g[ex + "_xd"], "r": g[ex], "entry": g.entry, "sd": sd,
                         "gap": g.rs.astype(float), "sig": g.d}), prio


def job(a):
    key, base, per, seed = a
    import system_bt as S
    tr, prio = trades(key)
    r = S.run(priority="gap" if prio else "random", seed=seed, cash_spy=True, trades=tr, risk=0.01, maxpos=10, base=base, **PER[per])
    return key, base, per, seed, {"cagr": float(r["sys"]["cagr"]), "maxdd": float(r["sys"]["maxdd"]), "b_cagr": float(r["spy"]["cagr"]),
                                  "b_maxdd": float(r["spy"]["maxdd"]), "n": r["n"], "win": r["win"], "expo": r["expo"],
                                  "years": r["years"] if per == "all" else None}


if __name__ == "__main__":
    jobs = [(k, b, p, s) for k in CONF for b in ("SPY", "QQQ") for p in PER for s in range(SEEDS if not CONF[k][5] else 1)]
    res = {}
    with Pool(2) as pool:
        for k, b, p, s, v in pool.imap_unordered(job, jobs):
            res.setdefault(f"{k}|{b}|{p}", []).append(v)
    out = {}
    for kk, v in res.items():
        c = [x["cagr"] for x in v]
        out[kk] = {"cagr": [float(np.percentile(c, 10)), float(np.median(c)), float(np.percentile(c, 90))],
                   "beat": int(sum(x["cagr"] > x["b_cagr"] for x in v)), "seeds": len(v), "maxdd": float(np.median([x["maxdd"] for x in v])),
                   "b_cagr": v[0]["b_cagr"], "b_maxdd": v[0]["b_maxdd"], "n": float(np.median([x["n"] for x in v])),
                   "win": float(np.median([x["win"] for x in v])), "expo": float(np.median([x["expo"] for x in v]))}
        if v[0]["years"]:
            ys = v[0]["years"].keys()
            out[kk]["years"] = {y: {"sys": float(np.median([x["years"][y]["sys"] for x in v])), "bench": v[0]["years"][y]["spy"]} for y in ys}
        k, b, p = kk.split("|")
        print(f"{k:6s} {b} {p:3s} 年化 {out[kk]['cagr'][1]:5.1f}（{out[kk]['cagr'][0]:5.1f}~{out[kk]['cagr'][2]:5.1f}） 基准 {out[kk]['b_cagr']:5.1f} 赢 {out[kk]['beat']}/{len(v)} 回撤 {out[kk]['maxdd']:6.1f}（基准 {out[kk]['b_maxdd']}） 笔 {out[kk]['n']:.0f} 仓位 {out[kk]['expo']:.0f}%", flush=True)
    json.dump({"conf": {k: v[0] for k, v in CONF.items()}, "res": out}, open(os.path.join(HERE, "variants_qqq20.json"), "w", encoding="utf-8"), ensure_ascii=False)
