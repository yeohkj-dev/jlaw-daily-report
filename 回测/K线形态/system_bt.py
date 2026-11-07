"""把 exit_bt.py 的逐笔交易组合成「一个账户」来跑：有资金、有仓位上限、有手续费，按日计算账户净值，跟买入持有 SPY 比。
不用盯盘的规则（全部在收盘后决定、第二天开盘下单）：
  模块 A 低位放量长下影：第二天开盘买；收盘比买价跌 15% → 隔天开盘卖；最多拿 60 天（exit_bt 的 E19）
  模块 B 放量突破 50 日高（个股升势 + SPY 在 200MA 上）：第二天开盘买；止损单 = 突破K线最低点 − 1 ATR（券商挂 GTC 止损单，自动执行）；
         拿满 20 天卖（E11）
仓位：每笔最多亏账户的 RISK（默认 1%）：买入金额 = 账户 × RISK ÷ 止损距离；单笔最多账户 20%；最多同时 MAXPOS 只；现金不够就不买。
同一天信号太多：A 优先，B 按「开盘离突破点」从远到近（PRIORITY="gap"）或随机（"random"，检验是不是靠排序）。
手续费 + 滑价：每边 0.1%。
输出 system_bt.json（各版本的净值曲线和统计）。
"""
import glob, json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = os.environ.get("BT_TAG", "")   # "20" = 用 cache20（2005 起 20 年数据），输出文件名加 20
CACHE = os.path.join(HERE, "..", "cache" + TAG)
COST = 0.001


def load(sym):
    df = pd.DataFrame(json.load(open(os.path.join(CACHE, sym + ".json")))).dropna()
    df = df[(df.h > df.l) & (df.v > 0) & (df.o > 0)]
    return df.set_index("d")


T = pd.read_pickle(os.path.join(HERE, f"exit_trades{TAG}.pkl"))
SPY = load("SPY")


def build_trades(use, b_setup="B", a_exit="E19", excl=(), b_exit="E11", a_mkt="all"):
    rows = []
    if "A" in use:
        a = T[T.setup == "A"]
        if a_mkt == "bear":
            a = a[~a.mkt]                   # 只在 SPY 低于 200MA 时做长下影
        rows.append(pd.DataFrame({"sym": a.sym, "mod": "A", "ed": a.ed, "xd": a[a_exit + "_xd"], "r": a[a_exit], "entry": a.entry, "sd": 0.15, "gap": 0.0, "sig": a.d}))
    if "B" in use:
        b = T[T.setup == b_setup]
        rows.append(pd.DataFrame({"sym": b.sym, "mod": "B", "ed": b.ed, "xd": b[b_exit + "_xd"], "r": b[b_exit], "entry": b.entry, "sd": b.rpct_w, "gap": b.gap, "sig": b.d}))
    out = pd.concat(rows, ignore_index=True)
    for m in excl:                      # 去掉某些月份的信号（检验是不是靠一次事件）
        out = out[out.sig.str[:7] != m]
    return out


CLOSES = {}


def closes(sym):
    if sym not in CLOSES:
        CLOSES[sym] = load(sym).c
    return CLOSES[sym]


def run(use=("A", "B"), risk=0.01, maxpos=10, priority="gap", b_setup="B", seed=0, start=None, cash_spy=False, a_first=True, a_exit="E19", excl=(), fixed=None, b_exit="E11", a_mkt="all", end=None, trades=None, capital=1.0, fee=0.0, min_pos=0.0):
    """capital = 起始本金（美元）；fee = 每张单固定手续费（美元）；SPY 为底时买卖个股要先卖 / 再买 SPY，多付两张单；min_pos = 最小下单金额"""
    tr = trades.copy() if trades is not None else build_trades(use, b_setup, a_exit, excl, b_exit, a_mkt)
    start = start or str(T.ed.min())
    tr = tr[tr.ed >= start]
    rng = np.random.default_rng(seed)
    tr["rnd"] = rng.random(len(tr))
    by_day = {d: g for d, g in tr.groupby("ed")}
    days = [d for d in SPY.index if d >= start and (end is None or d <= end)]
    tr = tr[tr.ed <= days[-1]]
    cash, eq0 = float(capital), float(capital)
    nfee = fee * (2 if cash_spy else 1)          # 每次买或卖要付几张单的手续费
    pos = []            # dict(sym, mod, alloc, entry, xd, r)
    curve, done, expo = [], [], []
    prev_t = None
    for t in days:
        if cash_spy and prev_t is not None:
            cash *= SPY.c[t] / SPY.c[prev_t]
        prev_t = t
        # 1) 今天到期 / 止损的先卖
        keep = []
        for p in pos:
            if p["xd"] <= t:
                val = p["alloc"] * (1 + p["r"]) * (1 - COST) - nfee
                cash += val
                done.append({"mod": p["mod"], "ed": p["ed"], "xd": p["xd"], "r": p["r"] - 2 * COST, "pnl": val - p["alloc"] / (1 - COST), "sym": p["sym"]})
            else:
                keep.append(p)
        pos = keep
        # 2) 今天开盘买（用昨天收盘的账户净值算仓位）
        if t in by_day:
            g = by_day[t].copy()
            if priority == "gap":
                g["k"] = np.where(g["mod"] == "A", 1e9 + g.rnd, g.gap)
            else:
                g["k"] = g.rnd + (np.where(g["mod"] == "A", 10, 0) if a_first else 0)
            g = g.sort_values("k", ascending=False)
            held = {p["sym"] for p in pos}
            for _, s in g.iterrows():
                if len(pos) >= maxpos or s.sym in held:
                    continue
                want = eq0 * fixed if fixed else min(eq0 * risk / s.sd, eq0 * 0.20)
                amt = min(want, cash)
                if amt < eq0 * 0.02 or amt < max(min_pos, 3 * nfee):
                    continue
                cash -= amt
                pos.append({"sym": s.sym, "mod": s["mod"], "alloc": (amt - nfee) * (1 - COST), "entry": s.entry, "xd": s.xd, "r": s.r, "ed": t})
                held.add(s.sym)
        # 3) 收盘按市价算账户
        mv = 0.0
        for p in pos:
            c = closes(p["sym"]).get(t)
            mv += p["alloc"] * (c / p["entry"]) if c is not None and not np.isnan(c) else p["alloc"]
        eq0 = cash + mv
        curve.append(eq0); expo.append(mv / eq0 if eq0 else 0)
    eq = pd.Series(curve, index=days) / capital
    spy = SPY.c.loc[days] / SPY.c.loc[days].iloc[0]
    D = pd.DataFrame(done)
    yrs = (pd.Timestamp(days[-1]) - pd.Timestamp(days[0])).days / 365.25

    def stats(s):
        dd = s / s.cummax() - 1
        rets = s.pct_change().dropna()
        return {"total": round(100 * (s.iloc[-1] - 1), 1), "cagr": round(100 * (s.iloc[-1] ** (1 / yrs) - 1), 1),
                "maxdd": round(100 * dd.min(), 1), "vol": round(100 * rets.std() * np.sqrt(252), 1),
                "sharpe": round(rets.mean() / rets.std() * np.sqrt(252), 2) if rets.std() else None}
    yr = {}
    for y in sorted({d[:4] for d in days}):
        ii = [d for d in days if d[:4] == y]
        prev = [d for d in days if d < ii[0]]
        base_e = eq[prev[-1]] if prev else 1.0; base_s = spy[prev[-1]] if prev else 1.0
        yr[y] = {"sys": round(100 * (eq[ii[-1]] / base_e - 1), 1), "spy": round(100 * (spy[ii[-1]] / base_s - 1), 1)}
    out = {"sys": stats(eq), "spy": stats(spy), "years": yr,
           "n": int(len(D)), "win": round(100 * (D.r > 0).mean(), 1) if len(D) else None,
           "avg_r": round(100 * D.r.mean(), 2) if len(D) else None,
           "by_mod": {m: {"n": int(len(g)), "win": round(100 * (g.r > 0).mean(), 1), "avg": round(100 * g.r.mean(), 2),
                          "pnl_share": round(100 * g.pnl.sum() / D.pnl.sum(), 1) if D.pnl.sum() else None} for m, g in D.groupby("mod")} if len(D) else {},
           "expo": round(100 * float(np.mean(expo)), 1), "avg_pos": None,
           "curve": {"d": days[::5] + ([days[-1]] if (len(days) - 1) % 5 else []),
                     "sys": [round(float(eq[d]), 4) for d in days[::5]] + ([round(float(eq.iloc[-1]), 4)] if (len(days) - 1) % 5 else []),
                     "spy": [round(float(spy[d]), 4) for d in days[::5]] + ([round(float(spy.iloc[-1]), 4)] if (len(days) - 1) % 5 else []),
                     "dd": [round(float(100 * (eq[d] / eq[:d].max() - 1)), 2) for d in days[::5]] + ([round(float(100 * (eq.iloc[-1] / eq.max() - 1)), 2)] if (len(days) - 1) % 5 else []),
                     "spydd": [round(float(100 * (spy[d] / spy[:d].max() - 1)), 2) for d in days[::5]] + ([round(float(100 * (spy.iloc[-1] / spy.max() - 1)), 2)] if (len(days) - 1) % 5 else [])}}
    if len(D):
        out["trades_sample"] = D.sort_values("pnl").iloc[[0, -1]].to_dict("records")
    return out


if __name__ == "__main__":
    V = {
        "main": dict(),
        "random": dict(priority="random"),
        "random2": dict(priority="random", seed=7),
        "A_only": dict(use=("A",)),
        "B_only": dict(use=("B",)),
        "risk05": dict(risk=0.005),
        "max5": dict(maxpos=5),
        "max20": dict(maxpos=20),
        "B_nofilter": dict(use=("B",), b_setup="B0"),
    }
    R = {}
    for k, kw in V.items():
        R[k] = run(**kw)
        s = R[k]
        print(f"{k:10s} 系统 总{s['sys']['total']:6.1f}% 年化{s['sys']['cagr']:5.1f}% 最大回撤{s['sys']['maxdd']:6.1f}% 夏普{s['sys']['sharpe']} | SPY 总{s['spy']['total']}% 年化{s['spy']['cagr']}% 回撤{s['spy']['maxdd']}% | 笔{s['n']} 胜{s['win']} 均{s['avg_r']} 仓位{s['expo']}% {s['by_mod']}")
        print("           ", {y: (v['sys'], v['spy']) for y, v in s["years"].items()})
    json.dump(R, open(os.path.join(HERE, f"system_bt{TAG}.json"), "w", encoding="utf-8"), ensure_ascii=False)
