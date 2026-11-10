"""21 年多时间框架回测（2005–2026，日线数据）：周线定趋势 / 形态，日线定买点。

免费的 60 分钟数据只有约 3 年（见 mtf_bt.py），所以 21 年版本把时间框架往上移一级：
  大周期 = 周线：周收盘 > 10 周线 > 40 周线，且 10 周线向上（「周线上升趋势」）
  信号    = 日线的 A0 / META 回调 / VCP 突破就绪（和网站同一份程序算出的信号，回测/jlaw_sig20.pkl、meta_trades20_rs.pkl）
  小周期 = 日线买点：
    D0 现在的做法：次日开盘买（VCP：次日碰到突破点买，高于突破点 5% 不追）
    D1 收盘确认：之后 5 天内，有一天收盘高于信号日最高价 → 当天收盘买
    D2 突破信号日高点：之后 5 天内，盘中碰到信号日最高价就买（开盘已高于它 3% 以上不追）
  每种都再加一个版本「+W」：只在周线上升趋势时才买
卖出（全部一样，和 A0 相同）：收盘比买价跌 8% → 次日开盘卖；盘中跌到 −12% → 当场卖；否则拿 60 个交易日后收盘卖。
同一时间买卖 SPY 当比较。用法：python 回测/mtf/mtf21_bt.py → mtf21_trades.pkl、mtf21_stats.json
"""
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BT = next((p for p in (os.environ.get("BT_DATA"), os.path.join(REPO, "回测"), os.path.join(os.path.dirname(REPO), "回测"))
           if p and os.path.exists(os.path.join(p, "cache20"))), os.path.join(REPO, "回测"))
MAX_WAIT, HOLD = 5, 60


def daily(sym):
    d = json.load(open(os.path.join(BT, "cache20", sym + ".json")))
    df = pd.DataFrame({k: d[k] for k in "ohlcv"}, index=pd.to_datetime(d["d"]))
    return df[~df.index.duplicated()].dropna()


def weekly_up(D):
    """每个交易日对应「上一周收盘时」的周线趋势（不偷看本周）。"""
    w = D["c"].resample("W-FRI").last().dropna()
    m10, m40 = w.rolling(10).mean(), w.rolling(40).mean()
    up = (w > m10) & (m10 > m40) & (m10 > m10.shift(2))
    up = up.shift(1)                                      # 用上一周的结果
    return up.reindex(D.index, method="ffill").fillna(False).astype(bool)


def exit_a0(o, h, l, c, k, entry, at_close):
    """从进场日 k 开始；at_close=True 表示收盘才买（当天不检查盘中止损）。返回 (卖出 index, 价, 原因)。"""
    n = len(c)
    hard, soft = entry * 0.88, entry * 0.92
    if not at_close and l[k] <= hard:
        return k, hard, "hard"
    if c[k] <= soft and not at_close:
        return (k + 1, o[k + 1], "close8") if k + 1 < n else None
    for j in range(k + 1, min(n, k + HOLD)):
        if o[j] <= hard:
            return j, o[j], "hard"
        if l[j] <= hard:
            return j, hard, "hard"
        if c[j] <= soft:
            return (j + 1, o[j + 1], "close8") if j + 1 < n else None
    j = k + HOLD - 1
    return (j, c[j], "time") if j < n else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    mt = pickle.load(open(os.path.join(BT, "meta_trades20_rs.pkl"), "rb"))
    js = pickle.load(open(os.path.join(BT, "jlaw_sig20.pkl"), "rb"))
    sigs = ([("A0", r.sym, pd.Timestamp(r.d), None) for r in mt[(mt.rs >= 90) & mt.mkt].itertuples()]
            + [("META", r.sym, pd.Timestamp(r.d), None) for r in js[js.kind == "META"].itertuples()]
            + [("VCP", r.sym, pd.Timestamp(r.d), r.pivot) for r in js[js.kind == "VCP"].itertuples()])
    print("信号", len(sigs), {k: sum(1 for s in sigs if s[0] == k) for k in ("A0", "META", "VCP")}, flush=True)
    SPY = daily("SPY")
    so, sc = SPY["o"], SPY["c"]
    by_sym = {}
    for s in sigs:
        by_sym.setdefault(s[1], []).append(s)
    rows = []
    for n, (sym, ss) in enumerate(sorted(by_sym.items()), 1):
        try:
            D = daily(sym)
        except Exception:
            continue
        o, h, l, c = (D[k].values for k in "ohlc")
        idx = {d: i for i, d in enumerate(D.index)}
        wup = weekly_up(D).values
        for kind, _, d, pivot in ss:
            i0 = idx.get(d)
            if i0 is None or i0 + 1 >= len(c):
                continue
            hi = h[i0]
            ent = {}
            if kind == "VCP":
                if o[i0 + 1] <= pivot * 1.05 and h[i0 + 1] >= pivot:
                    ent["D0"] = (i0 + 1, max(o[i0 + 1], pivot), False)
            else:
                ent["D0"] = (i0 + 1, o[i0 + 1], False)
            for k in range(i0 + 1, min(len(c), i0 + 1 + MAX_WAIT)):
                if "D1" not in ent and c[k] > hi:
                    ent["D1"] = (k, c[k], True)
                if "D2" not in ent and h[k] >= hi and o[k] <= hi * 1.03:
                    ent["D2"] = (k, max(o[k], hi), False)
            for m, (k, px, at_close) in ent.items():
                ex = exit_a0(o, h, l, c, k, px, at_close)
                if not ex:
                    continue
                j, xp, why = ex
                dk, dj = D.index[k], D.index[j]
                if dk not in SPY.index or dj not in SPY.index:
                    continue
                s0 = sc[dk] if at_close else so[dk]
                s1 = so[dj] if why == "close8" else sc[dj]
                rec = dict(kind=kind, sym=sym, sig=d, method=m, wait=k - i0, ret=xp / px - 1, spy=s1 / s0 - 1, why=why,
                           wup=bool(wup[i0]), year=d.year)
                rows.append(rec)
        if n % 300 == 0:
            print(f"  {n}/{len(by_sym)} 只", flush=True)
    T = pd.DataFrame(rows)
    T["ex"] = T.ret - T.spy
    pickle.dump(T, open(os.path.join(HERE, "mtf21_trades.pkl"), "wb"))
    stats = {}
    for kind in ("A0", "META", "VCP"):
        n_sig = sum(1 for s in sigs if s[0] == kind)
        for m in ("D0", "D1", "D2"):
            for wf in (False, True):
                x = T[(T.kind == kind) & (T.method == m)]
                if wf:
                    x = x[x.wup]
                if not len(x):
                    continue
                yrs = x.groupby("year").ex.mean()
                half = {"2005-2015": x[x.year <= 2015].ex.mean() * 100, "2016-2026": x[x.year >= 2016].ex.mean() * 100}
                stats[f"{kind}_{m}{'+W' if wf else ''}"] = dict(
                    n=len(x), take=len(x) / n_sig * 100, avg=x.ret.mean() * 100, med=x.ret.median() * 100, win=(x.ret > 0).mean() * 100,
                    ex=x.ex.mean() * 100, ex_med=x.ex.median() * 100, beat=(x.ex > 0).mean() * 100, t=x.ex.mean() / (x.ex.std() / np.sqrt(len(x))),
                    yrs_pos=(yrs > 0).mean() * 100, halves=half, hard=(x.why == "hard").mean() * 100)
    json.dump(stats, open(os.path.join(HERE, "mtf21_stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    for k, v in stats.items():
        print(k.ljust(12), " ".join(f"{a}={b:.1f}" if isinstance(b, float) else f"{a}={b}" for a, b in v.items() if a != "halves"),
              {a: round(b, 2) for a, b in v["halves"].items()})


if __name__ == "__main__":
    main()
