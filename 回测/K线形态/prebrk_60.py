"""「即将突破」名单的盘中提醒能不能做到：用 60 分钟K线（约 3 年，2023-12 起）测真正可执行的版本（2026-11-13）。

prebrk_bt.py 的 IV（盘中穿过突破价就买、只算全天量 ≥ 2 倍的日子）用了收盘才知道的全天成交量，偏乐观。
这里改成盘中当时就知道的东西：每根 60 分钟K线结束时检查
  ① 今天最高价已经 > 突破价；② 到这根为止的累计成交量 ≥ 2 × 「平常到这个时候的累计量」
     （平常 = 这只股票前 20 天、同一根K线为止的累计量平均，成交量是 U 形，不能按时间平均分）
两个都成立 → 发提醒，用这根K线的收盘价买（R1，最实际：提醒到了才买）；
对照 R0 = 同一批但用突破价买（假设挂了突破单，偏乐观）。
同期对照：C（收盘确认才买）、N（收盘确认后第二天开盘买）、A3（原版）—— 只取 60 分钟数据有的期间。
卖法同 A3：收盘比买价跌 15% → 第二天开盘卖；否则拿 60 天。数据核对：那天 60 分钟最后一根收盘和日线收盘差 >2% 就不用。
"""
import datetime as dt
import glob
import json
import os
import sys
from multiprocessing import Pool
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import prebrk_bt as B  # noqa: E402

C60 = os.path.join(HERE, "..", "mtf", "cache60")
NY = ZoneInfo("America/New_York")
PACE = 2.0


def bars60(sym):
    p = os.path.join(C60, sym + ".json")
    if not os.path.exists(p):
        return None
    days = {}
    for b in json.load(open(p)):
        t = dt.datetime.fromtimestamp(b["t"], NY)
        if not (dt.time(9, 30) <= t.time() < dt.time(16, 0)) or b.get("v") is None or b.get("c") is None:
            continue
        days.setdefault(str(t.date()), []).append(b)
    return {d: sorted(v, key=lambda x: x["t"]) for d, v in days.items()}


def run_sym(f):
    sym = os.path.basename(f)[:-5]
    D60 = bars60(sym)
    if not D60:
        return []
    first60 = min(D60)
    rows = []
    for r in B.run_sym(f):                       # 日线版的全部信号（名单、A3、C、N…）
        if r["d"] < first60 or r["kind"] not in ("A3", "C", "N", "LIST_HIT"):
            continue
        r = dict(r)
        r["kind"] = r["kind"]
        rows.append(r)
    # 盘中版：重新跑名单，找突破日的 60 分钟K线
    df = B.load(f)
    o, h, l, c, v = (df[k].astype(float).values for k in "ohlcv")
    d = list(df.d.values)
    N = len(c)
    s = pd.Series(c)
    sma50, sma200 = s.rolling(50).mean().values, s.rolling(200).mean().values
    sma50_10 = np.roll(sma50, 10)
    H50 = pd.Series(h).rolling(50).max().values
    c1 = np.roll(c, 1)
    tr = np.maximum(h - l, np.maximum(abs(h - c1), abs(l - c1)))
    atr10 = pd.Series(tr).rolling(10).mean().values
    atr30p = pd.Series(tr).rolling(30).mean().shift(10).values
    v5, v50 = pd.Series(v).rolling(5).mean().values, pd.Series(v).rolling(50).mean().values
    liquid = (c >= 5) & (pd.Series(v * c).rolling(20).mean().values >= 5e6)
    mkt = np.array([bool(B.SPY_A200.get(x, False)) for x in d])
    up = (c > sma50) & (sma50 > sma200) & (sma50 > sma50_10)
    busy = {}

    def profile(j):
        """前 20 个交易日、每根 60 分钟K线为止的累计成交量平均（只用 60 分钟数据完整、和日线一致的日子）。"""
        cums = []
        for k in range(max(0, j - 20), j):
            bs = D60.get(d[k])
            if not bs or len(bs) < 6 or abs(bs[-1]["c"] / c[k] - 1) > 0.02:
                continue
            cums.append(np.cumsum([b["v"] for b in bs])[:7])
        if len(cums) < 10:
            return None
        L = min(len(x) for x in cums)
        return np.mean([x[:L] for x in cums], axis=0)

    for i in range(260, N - 2):
        if d[i] < first60 or not (liquid[i] and mkt[i] and up[i]):
            continue
        lvl = H50[i]
        dist = 1 - c[i] / lvl
        if not (0 < dist <= B.NEAR) or not (atr10[i] < 0.8 * atr30p[i] and v5[i] < v50[i]):
            continue
        j = next((k for k in range(i + 1, min(i + B.WAIT + 1, N - 1)) if h[k] > lvl), None)
        if j is None or busy.get("R1", -1) >= j:
            continue
        bs = D60.get(d[j])
        if not bs or abs(bs[-1]["c"] / c[j] - 1) > 0.02:
            continue
        prof = profile(j)
        if prof is None:
            continue
        cum, hi = 0, 0
        for n, b in enumerate(bs[:len(prof)]):
            cum += b["v"]
            hi = max(hi, b["h"])
            if hi > lvl and cum >= PACE * prof[n]:
                for kind, px in (("R1", b["c"]), ("R0", max(bs[0]["o"], lvl))):
                    if busy.get(kind, -1) >= j:
                        continue
                    rr, jx, x_open = B.exit_from(o, c, d, j, px, False)
                    sp = B.spy_ret(d[j], True, d[jx], x_open)
                    busy[kind] = jx
                    rows.append(dict(sym=sym, kind=kind, d=d[i], ed=d[j], year=d[j][:4], r=rr, x=(rr - sp) if sp is not None else np.nan,
                                     held=jx - j, bar=n, vs_lvl=px / lvl - 1, cok=bool(c[j] > lvl), day_vx=v[j] / (pd.Series(v[max(0, j - 20):j]).mean())))
                break
    return rows


def main():
    files = [f for f in sorted(glob.glob(os.path.join(B.CACHE, "*.json"))) if os.path.exists(os.path.join(C60, os.path.basename(f)))]
    with Pool(10) as p:
        rows = [r for rs in p.imap_unordered(run_sym, files, chunksize=10) for r in rs]
    T = pd.DataFrame(rows)
    T["cok"] = T["cok"].astype("boolean").fillna(False).astype(bool) if "cok" in T else False
    T.to_pickle(os.path.join(HERE, "prebrk60_trades.pkl"))
    res = {"info": dict(start=str(T[T.kind == "R1"].ed.min()), end=str(T[T.kind == "R1"].ed.max()), stocks=len(files), pace=PACE)}
    for k in ["A3", "C", "N", "R0", "R1"]:
        ts = T[T.kind == k]
        if len(ts) > 2:
            res[k] = B.summ(ts)
    R1 = T[T.kind == "R1"]
    if len(R1):
        res["R1_detail"] = dict(bar_hist={int(k): int(v) for k, v in R1.bar.value_counts().sort_index().items()},
                                vs_lvl_med=round(100 * R1.vs_lvl.median(), 2), close_fail=round(100 * (~R1.cok).mean(), 1),
                                day_vx_med=round(float(R1.day_vx.median()), 2), day_vx_ge2=round(100 * (R1.day_vx >= 2).mean(), 1))
        res["R1_fail"] = B.summ(R1[~R1.cok]) if (~R1.cok).sum() > 2 else None
    json.dump(res, open(os.path.join(HERE, "prebrk60.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    for k, v in res.items():
        if isinstance(v, dict) and "ex" in v:
            print(f"{k:4s} n={v['n']:5d} 胜率 {v['win']:5.1f}%  平均 {v['avg']:+6.2f}%  超额 {v['ex']:+6.2f}%（中位 {v['ex_med']:+.2f}） t={v['t']}  年份 {v['by_year']}")
    print(res.get("R1_detail"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
