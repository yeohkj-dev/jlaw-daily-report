"""多时间框架进场回测（约 3 年，2023-12 起）：日线找形态（大周期），1 / 2 / 4 小时线找买点（小周期）。

同一批信号（和网站一样，回测/jlaw_sig20.pkl、meta_trades20_rs.pkl）：
  A0  = META 就绪 + RS ≥ 90 + SPY 在 200 天线上（网站「A0. 回测最佳」）
  META = META 回调就绪（全部）
  VCP  = VCP 突破就绪
进场方法（信号日之后最多 5 个交易日内），小周期 TF = 60 / 120 / 240 分钟：
  E0 现在的做法：A0 / META 次日开盘买；VCP 次日碰到突破点买（高于突破点 5% 不追）
  E1 小周期收盘高于前一天最高价（VCP：收盘站上突破点、≤ 突破点 5%，且这根K线的量 ≥ 前 20 根平均 1.5 倍）
  E2 当天第一根小周期K线的高点被之后的K线收盘突破（开盘区间突破）
  E3 小周期收盘重新站上小周期 20 EMA（前一根在下面）
卖出（全部一样，和 A0 相同）：收盘比买价跌 8% → 次日开盘卖；盘中跌到 −12% → 当场卖（进场当天用 60 分钟K线检查）；否则拿 60 个交易日后收盘卖。
同一时间买卖 SPY 当比较。免费的 60 分钟数据只有约 3 年（Yahoo），2 / 4 小时K线由 60 分钟K线合成。
数据：日线 回测/cache20，60 分钟线 回测/mtf/cache60（都不进仓库）。
用法：python 回测/mtf/mtf_bt.py → mtf_trades.pkl、mtf_stats.json
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
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
from common import yahoo_chart

BT = next((p for p in (os.environ.get("BT_DATA"), os.path.join(REPO, "回测"), os.path.join(os.path.dirname(REPO), "回测"))
           if p and os.path.exists(os.path.join(p, "cache20"))), os.path.join(REPO, "回测"))
C60 = os.path.join(HERE, "cache60")
START = "2023-12-15"
MAX_WAIT, HOLD = 5, 60
TFS = (60, 120, 240)


def et_of(ts):
    """美东时间（3 月第二个周日至 11 月第一个周日是夏令时）。"""
    u = dt.datetime.fromtimestamp(ts, dt.timezone.utc).replace(tzinfo=None)
    y = u.year
    m2 = dt.date(y, 3, 8) + dt.timedelta(days=(6 - dt.date(y, 3, 8).weekday()) % 7)
    n1 = dt.date(y, 11, 1) + dt.timedelta(days=(6 - dt.date(y, 11, 1).weekday()) % 7)
    return u + dt.timedelta(hours=-4 if m2 <= (u - dt.timedelta(hours=5)).date() < n1 else -5)


def get60(sym):
    path = os.path.join(C60, sym + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    try:
        bars, _ = yahoo_chart(sym.replace(".", "-"), "730d", "60m")
    except Exception:
        return None
    out = [dict(t=b["t"], o=b["o"], h=b["h"], l=b["l"], c=b["c"], v=b["v"]) for b in bars if b["c"] and b["o"]]
    json.dump(out, open(path, "w"))
    return out


def daily(sym):
    d = json.load(open(os.path.join(BT, "cache20", sym + ".json")))
    df = pd.DataFrame({k: d[k] for k in "ohlcv"}, index=pd.to_datetime(d["d"]))
    return df[~df.index.duplicated()].dropna()


def day_bars(b60):
    """{美东日期: [60 分钟K线（带 et、end 时间）]}，只留正常交易时段。"""
    g = {}
    for b in b60 or []:
        e = et_of(b["t"])
        if not (dt.time(9, 30) <= e.time() < dt.time(16, 0)):
            continue
        g.setdefault(e.date(), []).append(dict(b, et=e, end=min(e + dt.timedelta(minutes=60), e.replace(hour=16, minute=0))))
    return g


def aggregate(g60, tf):
    """60 分钟K线合成 tf 分钟K线（每天从 09:30 开始数）。返回 (flat 列表, {日期: [flat 索引]})。"""
    flat, by = [], {}
    n = tf // 60
    for d in sorted(g60):
        bars = g60[d]
        for i in range(0, len(bars), n):
            ch = bars[i:i + n]
            by.setdefault(d, []).append(len(flat))
            flat.append(dict(et=ch[0]["et"], end=ch[-1]["end"], o=ch[0]["o"], h=max(x["h"] for x in ch), l=min(x["l"] for x in ch),
                             c=ch[-1]["c"], v=sum(x["v"] or 0 for x in ch)))
    closes = [b["c"] for b in flat]
    k, e = 2 / 21, None
    for b, c in zip(flat, closes):
        e = c if e is None else c * k + e * (1 - k)
        b["ema"] = e
    vols = np.array([b["v"] for b in flat], dtype=float)
    cs = np.concatenate([[0], np.cumsum(vols)])
    for i, b in enumerate(flat):
        b["avgv"] = (cs[i] - cs[max(0, i - 20)]) / min(20, i) if i else 0
    return flat, by


def entries(kind, pivot, i0, D, days, flat, by):
    """返回 {方法: (进场日 index, 进场价, 进场时间 or None=开盘)}。"""
    out = {}
    o, h = D["o"].values, D["h"].values
    if i0 + 1 >= len(days):
        return out
    if kind == "VCP":
        if o[i0 + 1] <= pivot * 1.05 and h[i0 + 1] >= pivot:
            out["E0"] = (i0 + 1, max(o[i0 + 1], pivot), None)
    else:
        out["E0"] = (i0 + 1, o[i0 + 1], None)
    for k in range(i0 + 1, min(len(days), i0 + 1 + MAX_WAIT)):
        idxs = by.get(days[k], [])
        if not idxs:
            continue
        prev_high = h[k - 1]
        first_hi = flat[idxs[0]]["h"]
        for j, fi in enumerate(idxs):
            b = flat[fi]
            if "E1" not in out:
                if kind == "VCP":
                    if pivot < b["c"] <= pivot * 1.05 and b["avgv"] and b["v"] >= 1.5 * b["avgv"]:
                        out["E1"] = (k, b["c"], b["end"])
                elif b["c"] > prev_high:
                    out["E1"] = (k, b["c"], b["end"])
            if "E2" not in out and j >= 1 and b["c"] > first_hi:
                out["E2"] = (k, b["c"], b["end"])
            if "E3" not in out and fi >= 1:
                p = flat[fi - 1]
                if p["c"] < p["ema"] and b["c"] > b["ema"]:
                    out["E3"] = (k, b["c"], b["end"])
        if len(out) == 4:
            break
    return out


def exit_a0(D, k, entry, after, g60, days):
    """A0 卖法。after = 进场时间（None = 开盘买，当天全部算）。返回 (卖出日 index, 价, 原因, 时间标记)。"""
    o, l, c = D["o"].values, D["l"].values, D["c"].values
    hard, soft = entry * 0.88, entry * 0.92
    if after is None:
        if l[k] <= hard:
            return k, hard, "hard", "intraday"
    else:
        for b in g60.get(days[k], []):
            if b["et"] >= after and b["l"] <= hard:
                return k, hard, "hard", "intraday"
    if c[k] <= soft:
        return (k + 1, o[k + 1], "close8", "open") if k + 1 < len(c) else None
    for j in range(k + 1, min(len(c), k + HOLD)):
        if o[j] <= hard:
            return j, o[j], "hard", "open"
        if l[j] <= hard:
            return j, hard, "hard", "intraday"
        if c[j] <= soft:
            return (j + 1, o[j + 1], "close8", "open") if j + 1 < len(c) else None
    j = k + HOLD - 1
    return (j, c[j], "time", "close") if j < len(c) else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(C60, exist_ok=True)
    mt = pickle.load(open(os.path.join(BT, "meta_trades20_rs.pkl"), "rb"))
    js = pickle.load(open(os.path.join(BT, "jlaw_sig20.pkl"), "rb"))
    js = js[js.d >= START]
    a0 = mt[(mt.d >= START) & (mt.rs >= 90) & mt.mkt]
    sigs = ([("A0", r.sym, pd.Timestamp(r.d), None) for r in a0.itertuples()]
            + [("META", r.sym, pd.Timestamp(r.d), None) for r in js[js.kind == "META"].itertuples()]
            + [("VCP", r.sym, pd.Timestamp(r.d), r.pivot) for r in js[js.kind == "VCP"].itertuples()])
    syms = sorted({s[1] for s in sigs} | {"SPY"})
    print("信号", len(sigs), {k: sum(1 for s in sigs if s[0] == k) for k in ("A0", "META", "VCP")}, "股票", len(syms), flush=True)
    with ThreadPoolExecutor(8) as ex:
        got = dict(zip(syms, ex.map(get60, syms)))
    print("60 分钟数据", sum(1 for v in got.values() if v), "/", len(syms), flush=True)
    SD = daily("SPY")
    S60 = day_bars(got["SPY"])
    first60 = min(S60)

    def spy_px(day, when):
        """同一时间的 SPY：when None=开盘、'close'=收盘、'open'=开盘、'intraday'=收盘（近似）、datetime=那根 60 分钟K线收盘。"""
        ts = pd.Timestamp(day)
        if ts not in SD.index:
            return None
        if when is None or when == "open":
            return SD.at[ts, "o"]
        if isinstance(when, str):
            return SD.at[ts, "c"]
        bars = [b for b in S60.get(day, []) if b["end"] <= when]
        return bars[-1]["c"] if bars else SD.at[ts, "o"]

    by_sym = {}
    for s in sigs:
        by_sym.setdefault(s[1], []).append(s)
    rows, bad_syms = [], []
    for n, (sym, ss) in enumerate(sorted(by_sym.items()), 1):
        if not got.get(sym):
            continue
        try:
            D = daily(sym)
        except Exception:
            continue
        days = [d.date() for d in D.index]
        di = {d: i for i, d in enumerate(days)}
        g60 = day_bars(got[sym])
        # 数据核对：60 分钟最后一根收盘要和日线收盘差 ≤2%，否则那天不用（例如 BNY 的 60 分钟数据是另一只证券）
        dc = dict(zip(days, D["c"].values))
        good = {d for d, bars in g60.items() if d in dc and abs(bars[-1]["c"] / dc[d] - 1) <= 0.02}
        if not g60 or len(good) < 0.8 * len([d for d in g60 if d in dc]):
            bad_syms.append(sym)
            continue
        g60 = {d: v for d, v in g60.items() if d in good}
        for tf in TFS:
            flat, by = aggregate(g60, tf)
            for kind, _, d, pivot in ss:
                i0 = di.get(d.date())
                if i0 is None or d.date() < first60:
                    continue
                for m, (k, px, when) in entries(kind, pivot, i0, D, days, flat, by).items():
                    if m == "E0" and tf != 60:
                        continue                                # E0 和时间框架无关，只算一次
                    ex_ = exit_a0(D, k, px, when, g60, days)
                    if not ex_:
                        continue
                    j, xp, why, xwhen = ex_
                    s0, s1 = spy_px(days[k], when), spy_px(days[j], xwhen)
                    rows.append(dict(kind=kind, sym=sym, sig=d.date(), tf=tf if m != "E0" else 0, method=m, wait=k - i0,
                                     entry=px, ret=xp / px - 1, spy=(s1 / s0 - 1) if s0 and s1 else np.nan, why=why))
        if n % 100 == 0:
            print(f"  {n}/{len(by_sym)} 只", flush=True)
    print("60 分钟数据和日线对不上、不用的股票", len(bad_syms), bad_syms[:20], flush=True)
    T = pd.DataFrame(rows)
    T["ex"] = T["ret"] - T["spy"]
    pickle.dump(T, open(os.path.join(HERE, "mtf_trades.pkl"), "wb"))
    print("交易", len(T), flush=True)

    stats = {}
    for kind in ("A0", "META", "VCP"):
        K = T[T.kind == kind]
        n_sig = sum(1 for s in sigs if s[0] == kind and s[2].date() >= first60)
        base = K[K.method == "E0"].drop_duplicates(["sym", "sig"]).set_index(["sym", "sig"]).ex
        stats[f"{kind}_E0"] = dict(n=len(base), take=len(base) / n_sig * 100, ex=base.mean() * 100,
                                   win=(K[K.method == "E0"].ret > 0).mean() * 100, total=base.sum())
        for tf in TFS:
            for m in ("E1", "E2", "E3"):
                x = K[(K.method == m) & (K.tf == tf)].drop_duplicates(["sym", "sig"]).set_index(["sym", "sig"])
                if not len(x):
                    continue
                both = base.index.intersection(x.index)
                skip = base.index.difference(x.index)
                d = x.ex[both] - base[both]
                stats[f"{kind}_{m}_{tf}"] = dict(
                    n=len(x), take=len(x) / n_sig * 100, ex=x.ex.mean() * 100, win=(x.ret > 0).mean() * 100, total=x.ex.sum(),
                    paired=d.mean() * 100 if len(d) else None, paired_t=(d.mean() / (d.std() / np.sqrt(len(d)))) if len(d) > 2 else None,
                    skipped=len(skip), skipped_ex=base[skip].mean() * 100 if len(skip) else None, wait=x.wait.mean())
    json.dump(stats, open(os.path.join(HERE, "mtf_stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    for k, v in stats.items():
        print(k.ljust(14), " ".join(f"{a}={b:.2f}" if isinstance(b, float) else f"{a}={b}" for a, b in v.items()))


if __name__ == "__main__":
    main()
