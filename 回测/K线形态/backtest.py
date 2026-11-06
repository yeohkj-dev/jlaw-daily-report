"""K线形态回测。
样本：回测/cache 下约 2254 只美股，5 年日线（2021-11 → 2026-11）。
入场：信号日的下一天开盘价；出场：之后第 5 / 10 / 20 个交易日收盘。
超额收益 = 形态收益 − 同一信号日、全样本所有股票的平均收益（扣掉大盘涨跌）。
另算：
  * 确认版：下一天收盘突破形态高点（看涨）/ 跌破低点（看跌）才进场，入场价 = 确认日收盘。
  * Bulkowski 式"突破方向"：之后 20 天内先收在形态最高价之上，还是先收在最低价之下。
输出 events.pkl（每次信号一行）与 baseline.pkl（每个日期的全市场平均前瞻收益）。
"""
import glob, json, os
import numpy as np
import pandas as pd
from patterns import detect, META

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "..", "cache")
H = (5, 10, 20, 60)
PLEN = {k: 1 for k in META}
PLEN.update({k: 2 for k in ["bull_engulf", "bear_engulf", "piercing", "dark_cloud", "bull_harami", "bear_harami",
                            "tweezer_bottom", "tweezer_top", "bull_kr", "bear_kr", "inside_bar_up"]})
PLEN.update({k: 3 for k in ["morning_star", "evening_star", "three_soldiers", "three_crows", "three_inside_up", "three_inside_down"]})
PLEN.update({"rising_three": 5, "falling_three": 5})


def load(path):
    d = json.load(open(path))
    df = pd.DataFrame(d).dropna()
    df = df[(df.h > df.l) & (df.v > 0) & (df.o > 0)].reset_index(drop=True)
    return df


def main():
    spy = load(os.path.join(CACHE, "SPY.json"))
    spy["above200"] = spy.c > spy.c.rolling(200).mean()
    regime = dict(zip(spy.d, spy.above200))
    ev_rows, base = [], []
    files = sorted(glob.glob(os.path.join(CACHE, "*.json")))
    for n, f in enumerate(files):
        sym = os.path.basename(f)[:-5]
        if sym in ("SPY", "QQQ"):
            continue
        df = load(f)
        if len(df) < 260:
            continue
        P, ctx = detect(df)
        o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
        N = len(df)
        fwd = {}
        ent = np.r_[o[1:], np.nan]
        for k in H:
            ex = np.r_[c[k:], [np.nan] * k]
            fwd[k] = ex / ent - 1
        liquid = (c >= 5) & ((df.v * df.c).rolling(20).mean().values >= 5e6)
        valid = liquid & ~np.isnan(fwd[20]) & (np.arange(N) >= 200)
        base.append(pd.DataFrame({"d": df.d.values[valid], **{f"r{k}": fwd[k][valid] for k in H}}))
        for name, sig in P.items():
            idx = np.where(sig.values & valid)[0]
            if not len(idx):
                continue
            dirn = META[name][1]
            L = PLEN[name]
            for i in idx:
                ph, pl = h[i - L + 1:i + 1].max(), l[i - L + 1:i + 1].min()
                # 突破方向（20 天内先收破哪边）
                up_hit = np.where(c[i + 1:i + 21] > ph)[0]; dn_hit = np.where(c[i + 1:i + 21] < pl)[0]
                u = up_hit[0] if len(up_hit) else 99; dd = dn_hit[0] if len(dn_hit) else 99
                brk = 1 if u < dd else (-1 if dd < u else 0)
                # 确认版
                conf = (c[i + 1] > ph) if dirn > 0 else ((c[i + 1] < pl) if dirn < 0 else False)
                row = {"sym": sym, "d": df.d.values[i], "p": name, "i": i, "brk": brk, "conf": bool(conf),
                       "vrel": ctx.vrel.values[i], "uptrend": bool(ctx.uptrend.values[i]), "above200": bool(ctx.above200.values[i]),
                       "mkt": bool(regime.get(df.d.values[i], True)),
                       "near50": bool(abs(l[i] / ctx.sma50.values[i] - 1) < 0.03 or (l[i] <= ctx.sma50.values[i] <= c[i])),
                       "stop_pct": (c[i] / pl - 1) if dirn >= 0 else (ph / c[i] - 1)}
                for k in H:
                    row[f"r{k}"] = fwd[k][i]
                    row[f"c{k}"] = (c[i + 1 + k] / c[i + 1] - 1) if (conf and i + 1 + k < N) else np.nan
                ev_rows.append(row)
        if n % 300 == 0:
            print(n, sym, len(ev_rows), flush=True)
    ev = pd.DataFrame(ev_rows)
    b = pd.concat(base)
    bl = b.groupby("d")[[f"r{k}" for k in H]].mean()
    ev = ev.join(bl.add_prefix("b"), on="d")
    for k in H:
        ev[f"x{k}"] = ev[f"r{k}"] - ev[f"br{k}"]
    ev.to_pickle(os.path.join(HERE, "events.pkl"))
    bl.to_pickle(os.path.join(HERE, "baseline.pkl"))
    b[[f"r{k}" for k in H]].describe().to_csv(os.path.join(HERE, "baseline_all.csv"))
    print("events", len(ev), "base bars", len(b))


if __name__ == "__main__":
    main()
