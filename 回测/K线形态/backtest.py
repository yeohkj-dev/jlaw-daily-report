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
import sys
from patterns import detect, META
SET2 = len(sys.argv) > 1 and sys.argv[1] == "2"
if SET2:      # 第二批形态
    from patterns2 import detect2 as detect, META2 as META
SET3 = len(sys.argv) > 1 and sys.argv[1] == "3"
if SET3:      # 第三批：经典图形
    from patterns3 import detect3 as detect, META3 as META
SET4 = len(sys.argv) > 1 and sys.argv[1] == "4"
if SET4:      # 第四批：Smart Money Order Block
    from patterns_ob import detect_ob as detect, META_OB as META
SUF = "2" if SET2 else ("3" if SET3 else ("4" if SET4 else ""))

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = os.environ.get("BT_TAG", "")   # "20" = 用 cache20（2005 起 20 年数据），输出文件名加 20
CACHE = os.path.join(HERE, "..", "cache" + TAG)
H = (5, 10, 20, 60)
PLEN = {k: 1 for k in META}
PLEN.update({"kicker_bull": 2, "kicker_bear": 2, "matching_low": 2, "on_neck": 2, "oops_bull": 2, "oops_bear": 2, "luk_id": 2,
             "tasuki_up": 3, "two_black_gap": 3, "advance_block": 3, "tls_bear": 4, "tls_bull": 4})
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
    # 省内存版（20 年数据约 300 万次信号）：每只股票先做成紧凑 DataFrame；全市场基准用按日期累加，不存每一根K线
    cal = pd.Index(spy.d.values)
    bsum = {k: np.zeros(len(cal)) for k in H}; bcnt = np.zeros(len(cal)); ball = {k: [0.0, 0.0, 0] for k in H}
    chunks, n_ev = [], 0
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
        ci = cal.get_indexer(df.d.values[valid]); okc = ci >= 0
        for k in H:
            v = fwd[k][valid]; m = okc & ~np.isnan(v)
            np.add.at(bsum[k], ci[m], v[m]); ball[k][0] += float(v[m].sum()); ball[k][1] += float((v[m] ** 2).sum()); ball[k][2] += int(m.sum())
        np.add.at(bcnt, ci[okc], 1)
        rows = []
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
                rows.append((df.d.values[i], name, i, brk, bool(conf), ctx.vrel.values[i], bool(ctx.uptrend.values[i]), bool(ctx.above200.values[i]),
                             bool(regime.get(df.d.values[i], True)),
                             bool(abs(l[i] / ctx.sma50.values[i] - 1) < 0.03 or (l[i] <= ctx.sma50.values[i] <= c[i])),
                             (c[i] / pl - 1) if dirn >= 0 else (ph / c[i] - 1),
                             *[fwd[k][i] for k in H],
                             *[((c[i + 1 + k] / c[i + 1] - 1) if (conf and i + 1 + k < N) else np.nan) for k in H]))
        if rows:
            cols = ["d", "p", "i", "brk", "conf", "vrel", "uptrend", "above200", "mkt", "near50", "stop_pct"] + [f"r{k}" for k in H] + [f"c{k}" for k in H]
            x = pd.DataFrame(rows, columns=cols)
            for col in ["vrel", "stop_pct"] + [f"r{k}" for k in H] + [f"c{k}" for k in H]:
                x[col] = x[col].astype("float32")
            x["i"] = x["i"].astype("int32"); x["brk"] = x["brk"].astype("int8")
            x.insert(0, "sym", sym)
            chunks.append(x); n_ev += len(x)
        if n % 300 == 0:
            print(n, sym, n_ev, flush=True)
    ev = pd.concat(chunks, ignore_index=True); del chunks
    for col in ("sym", "p", "d"):
        ev[col] = ev[col].astype("category")
    m = bcnt > 0
    bl = pd.DataFrame({f"r{k}": bsum[k][m] / bcnt[m] for k in H}, index=pd.Index(cal[m], name="d"))
    ev = ev.join(bl.add_prefix("b"), on="d")
    for k in H:
        ev[f"x{k}"] = (ev[f"r{k}"] - ev[f"br{k}"]).astype("float32")
    for col in ("sym", "p", "d"):
        ev[col] = ev[col].astype(str)
    ev.to_pickle(os.path.join(HERE, f"events{SUF}{TAG}.pkl"))
    if not SET2 and not SET3 and not SET4:
        bl.to_pickle(os.path.join(HERE, f"baseline{TAG}.pkl"))
        pd.DataFrame({f"r{k}": {"count": ball[k][2], "mean": ball[k][0] / ball[k][2],
                                 "std": (ball[k][1] / ball[k][2] - (ball[k][0] / ball[k][2]) ** 2) ** 0.5} for k in H}).to_csv(os.path.join(HERE, f"baseline_all{TAG}.csv"))
    b = bcnt
    print("events", len(ev), "base bars", int(bcnt.sum()))


if __name__ == "__main__":
    main()
