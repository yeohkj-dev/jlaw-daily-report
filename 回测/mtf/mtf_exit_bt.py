"""小周期（1 / 2 / 4 小时）买进 + 卖出回测，约 3 年（2023-12 起），4 个系统：A0、META、BRK（放量突破 50 日高）、C9。

买进（和 mtf_bt.py 一样）：E0 次日开盘；E2 小周期开盘区间突破；E3 小周期收盘重新站上 20 EMA
卖出（买进固定用 E0 次日开盘，只比较卖法）：
  XD    日线：系统止损（收盘价判断）+ 拿 60 个交易日（和 21 年研究的 X0 一样）
  XLs   小周期收盘跌到止损价就在那根K线收盘卖（比日线收盘早发现）
  XLt   小周期移动止损：赚到 +10% 之后，小周期收盘跌破小周期 20 EMA 就卖；没到 +10% 之前用系统止损；最多 60 天
  XDt   日线移动止损（对照）：赚到 +10% 之后，日线收盘跌破 20 天线 → 次日开盘卖
同一时间买卖 SPY 当比较。用法：python 回测/mtf/mtf_exit_bt.py → mtf_exit_trades.pkl、mtf_exit_stats.json
"""
import datetime as dt
import json
import os
import pickle
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mtf_bt as M
import research21 as R
import c9_rules

TFS = (60, 120, 240)
HOLD = 60
STOP = {"A0": (0.08, 0.12), "META": (0.08, 0.12), "BRK": (0.15, None), "C9": (0.10, 0.15)}


def ltf_exit(D, days, k, entry, kind, flat, by, mode, spy_px):
    """从进场日 k（开盘买）开始，用小周期K线逐根检查。返回 (卖出日, 价, 时间, 原因)。"""
    soft, hard = STOP[kind]
    s_px, h_px = entry * (1 - soft), (entry * (1 - hard) if hard else None)
    armed = False
    for d_i in range(k, min(len(days), k + HOLD)):
        for fi in by.get(days[d_i], []):
            b = flat[fi]
            if h_px and b["l"] <= h_px:
                return d_i, min(b["o"], h_px), b["end"], "hard"
            if b["c"] <= s_px:
                return d_i, b["c"], b["end"], "stop"
            if mode == "XLt":
                if b["h"] >= entry * 1.10:
                    armed = True
                if armed and b["c"] < b["ema"]:
                    return d_i, b["c"], b["end"], "trail"
    j = k + HOLD - 1
    return (j, D["c"].values[j], "close", "time") if j < len(days) else None


def daily_exit(D, days, k, entry, kind, mode):
    o, l, c = D["o"].values, D["l"].values, D["c"].values
    m20 = D["c"].rolling(20).mean().values
    soft, hard = STOP[kind]
    s_px, h_px = entry * (1 - soft), (entry * (1 - hard) if hard else None)
    armed = False
    for j in range(k, min(len(c), k + HOLD)):
        if h_px and j > k and o[j] <= h_px:
            return j, o[j], "open", "hard"
        if h_px and l[j] <= h_px:
            return j, h_px, "close", "hard"
        if c[j] <= s_px or (mode == "XDt" and armed and c[j] < m20[j]):
            return (j + 1, o[j + 1], "open", "stop") if j + 1 < len(c) else None
        if c[j] >= entry * 1.10:
            armed = True
    j = k + HOLD - 1
    return (j, c[j], "close", "time") if j < len(c) else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    BT = M.BT
    SPY = M.daily("SPY")
    spy_up = SPY["c"] > SPY["c"].rolling(200).mean()
    mt = pickle.load(open(os.path.join(BT, "meta_trades20_rs.pkl"), "rb"))
    js = pickle.load(open(os.path.join(BT, "jlaw_sig20.pkl"), "rb"))
    start = pd.Timestamp(M.START)
    sigs = {}
    for r in mt[(mt.d >= M.START) & (mt.rs >= 90) & mt.mkt].itertuples():
        sigs.setdefault(r.sym, []).append(("A0", pd.Timestamp(r.d)))
    for r in js[(js.d >= M.START) & (js.kind == "META")].itertuples():
        sigs.setdefault(r.sym, []).append(("META", pd.Timestamp(r.d)))
    allsyms = sorted(f[:-5] for f in os.listdir(os.path.join(BT, "cache20")) if f.endswith(".json"))
    for sym in allsyms:
        if sym == "SPY":
            continue
        try:
            D = R.daily(sym)
        except Exception:
            continue
        if len(D) < 260 or D.index[-1] < start:
            continue
        X = R.prep(D)
        for kind, fn in (("BRK", R.brk_signals), ("C9", c9_rules.signals)):
            for i in fn(D, X, spy_up):
                if D.index[i] >= start:
                    sigs.setdefault(sym, []).append((kind, D.index[i]))
    print("信号", {k: sum(1 for v in sigs.values() for s in v if s[0] == k) for k in ("A0", "META", "BRK", "C9")}, "股票", len(sigs), flush=True)
    os.makedirs(M.C60, exist_ok=True)
    with ThreadPoolExecutor(8) as ex:
        got = dict(zip(sorted(sigs) + ["SPY"], ex.map(M.get60, sorted(sigs) + ["SPY"])))
    S60 = M.day_bars(got["SPY"])
    first60 = min(S60)

    def spy_px(day, when):
        ts = pd.Timestamp(day)
        if ts not in SPY.index:
            return None
        if when in (None, "open"):
            return SPY.at[ts, "o"]
        if isinstance(when, str):
            return SPY.at[ts, "c"]
        bars = [b for b in S60.get(day, []) if b["end"] <= when]
        return bars[-1]["c"] if bars else SPY.at[ts, "o"]

    rows, bad = [], []
    for n_, (sym, ss) in enumerate(sorted(sigs.items()), 1):
        if not got.get(sym):
            continue
        D = M.daily(sym)
        days = [d.date() for d in D.index]
        di = {d: i for i, d in enumerate(days)}
        g60 = M.day_bars(got[sym])
        dc = dict(zip(days, D["c"].values))
        good = {d for d, bars in g60.items() if d in dc and abs(bars[-1]["c"] / dc[d] - 1) <= 0.02}
        if not g60 or len(good) < 0.8 * len([d for d in g60 if d in dc]):
            bad.append(sym)
            continue
        g60 = {d: v for d, v in g60.items() if d in good}
        for tf in TFS:
            flat, by = M.aggregate(g60, tf)
            for kind, d in ss:
                i0 = di.get(d.date())
                if i0 is None or d.date() < first60 or i0 + 1 >= len(days):
                    continue
                # 买进：E0 / E2 / E3（卖法用系统止损 + 60 天）
                ent = M.entries(kind if kind != "C9" and kind != "BRK" else "META", None, i0, D, days, flat, by)
                for m, (k, px, when) in ent.items():
                    if m == "E1" or (m == "E0" and tf != 60):
                        continue
                    x = daily_exit(D, days, k, px, kind, "XD")
                    if x:
                        j, xp, xw, why = x
                        s0, s1 = spy_px(days[k], when), spy_px(days[j], xw)
                        rows.append((kind, sym, d.date(), "entry", m, tf if m != "E0" else 0, xp / px - 1, (s1 / s0 - 1) if s0 and s1 else np.nan, j - k, why))
                # 卖出：固定 E0 次日开盘买
                k, px = i0 + 1, D["o"].values[i0 + 1]
                for mode in ("XLs", "XLt"):
                    x = ltf_exit(D, days, k, px, kind, flat, by, mode, spy_px)
                    if x:
                        j, xp, xw, why = x
                        s0, s1 = spy_px(days[k], None), spy_px(days[j], xw)
                        rows.append((kind, sym, d.date(), "exit", mode, tf, xp / px - 1, (s1 / s0 - 1) if s0 and s1 else np.nan, j - k, why))
                if tf == 60:
                    for mode in ("XD", "XDt"):
                        x = daily_exit(D, days, k, px, kind, mode)
                        if x:
                            j, xp, xw, why = x
                            s0, s1 = spy_px(days[k], None), spy_px(days[j], xw)
                            rows.append((kind, sym, d.date(), "exit", mode, 0, xp / px - 1, (s1 / s0 - 1) if s0 and s1 else np.nan, j - k, why))
        if n_ % 200 == 0:
            print(f"  {n_}/{len(sigs)}", flush=True)
    T = pd.DataFrame(rows, columns=["kind", "sym", "sig", "test", "method", "tf", "ret", "spy", "hold", "why"])
    T["ex"] = T.ret - T.spy
    pickle.dump(T, open(os.path.join(HERE, "mtf_exit_trades.pkl"), "wb"))
    print("数据对不上不用", len(bad), bad[:15], "交易", len(T), flush=True)
    stats = {}
    for (kind, test, m, tf), g in T.groupby(["kind", "test", "method", "tf"]):
        g = g.drop_duplicates(["sym", "sig"])
        stats[f"{kind}|{test}|{m}|{tf}"] = dict(n=len(g), ex=g.ex.mean() * 100, avg=g.ret.mean() * 100, win=(g.ret > 0).mean() * 100,
                                               hold=g.hold.mean(), t=g.ex.mean() / (g.ex.std() / np.sqrt(len(g))) if len(g) > 2 else None,
                                               total=g.ex.sum())
    json.dump(stats, open(os.path.join(HERE, "mtf_exit_stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    for k, v in stats.items():
        print(k.ljust(22), " ".join(f"{a}={b:.2f}" if isinstance(b, float) else f"{a}={b}" for a, b in v.items()))


if __name__ == "__main__":
    main()
