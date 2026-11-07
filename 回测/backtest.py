"""回测第 2 步：用网站的选股规则在过去几年每天重跑一次，记录信号，模拟交易 / 计算之后的报酬。

  * J Law META 回调、VCP 突破：直接调用 tools/jlaw_daily_screen.py 的 analyse()（与网站同一份代码），
    再按 main() 的规则挑出「就绪」名单，模拟交易（两种卖法）
  * Stage 1→2、Stage 2、Luk 三个选股器：按网站同样的条件逐日重算，统计上榜后 5 / 10 / 20 天的报酬
  * 大盘状态（躺赚 / 警戒 / 血汗钱）：按 market_regime.py 的规则逐日重算（宽度用股票池里市值 ≥100 亿的股票）

限制：只有今天还在交易的股票（幸存者偏差）；历史市值 = 今天市值 × 当时股价 / 今天股价；没有历史业绩日期（META 少一项「业绩催化」优势）。
输出：回测/results.pkl
"""
import datetime as dt
import json
import os
import pickle
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache" + os.environ.get("BT_TAG", ""))   # BT_TAG=20 → cache20（2005 起）
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
WARMUP = 300                      # 前 300 个交易日只用来算指标
HORIZONS = (5, 10, 20)


# ---------------- 读数据 ----------------
def load_bars(sym):
    with open(os.path.join(CACHE, sym + ".json")) as f:
        d = json.load(f)
    df = pd.DataFrame({k: d[k] for k in "ohlcv"}, index=pd.to_datetime(d["d"]))
    return df[~df.index.duplicated()]


def panel():
    uni = json.load(open(os.path.join(HERE, "universe.json"), encoding="utf-8"))
    meta = {r["name"]: r for r in uni if os.path.exists(os.path.join(CACHE, r["name"] + ".json"))}
    spy = load_bars("SPY")
    dates = spy.index
    cols = {k: {} for k in "ohlcv"}
    for s in meta:
        b = load_bars(s).reindex(dates)
        for k in "ohlcv":
            cols[k][s] = b[k]
    P = {k: pd.DataFrame(cols[k]) for k in "ohlcv"}
    return meta, P, dates


# ---------------- 大盘状态 ----------------
def market_state(P, meta):
    C, V, O, H, L = P["c"], P["v"], P["o"], P["h"], P["l"]
    last = C.ffill().iloc[-1]
    mc_now = pd.Series({s: (meta[s].get("market_cap_basic") or 0) for s in C.columns})
    mcap = C.div(last).mul(mc_now)
    big = mcap >= 1e10
    above50 = (C > C.rolling(50).mean()) & big
    breadth = above50.sum(axis=1) / big.sum(axis=1).replace(0, np.nan) * 100
    red, yellow = pd.Series(False, C.index), pd.Series(False, C.index)
    for x in ("SPY", "QQQ"):
        c, v, o, h, l = C[x], V[x], O[x], H[x], L[x]
        s20, s50, s200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
        up50 = s50 > s50.shift(5)
        chg = c / c.shift(1) - 1
        qw = pd.Series([d.month in (3, 6, 9, 12) and d.weekday() == 4 and 15 <= d.day <= 21 for d in C.index], C.index)
        dist = ((chg < -0.002) & (v > v.shift(1)) & ~qw).astype(int).rolling(20).sum()
        gapdn = (o < l.shift(1)) & ((c - l) <= 0.25 * (h - l))
        abnormal = ((chg <= -0.03) | gapdn).astype(int).rolling(10).sum() > 0
        worst = (chg.rolling(5).min() == chg.rolling(63).min()) & (chg.rolling(63).min() < -0.015)
        red |= ((c < s50) & ~up50) | (c < s200) | (s50 < s200)
        yellow |= (dist >= 4) | abnormal | worst | ((c < s50) & up50) | (c < s20)
    red |= breadth < 40
    yellow |= breadth < 50
    hi20 = C["SPY"] >= C["SPY"].rolling(20).max()
    yellow |= hi20 & (breadth < breadth.shift(10) - 5)
    state = pd.Series("躺赚", C.index)
    state[yellow] = "警戒"
    state[red] = "血汗钱"
    return state, breadth


# ---------------- J Law：逐只股票跑 analyse（多进程）----------------
_SPY = None


def _init(spy_rows):
    global _SPY
    sys.path.insert(0, TOOLS)
    sys.argv = [sys.argv[0], os.path.join(HERE, "tmp")]
    _SPY = spy_rows


def _rows(df):
    return [dict(d=i.date(), o=r.o, h=r.h, l=r.l, c=r.c, v=r.v) for i, r in zip(df.index, df.itertuples()) if not np.isnan(r.c)]


def jlaw_worker(args):
    import jlaw_daily_screen as js
    sym, m, mc_now = args
    df = load_bars(sym)
    px = _rows(df)
    if len(px) < WARMUP + 5 or not mc_now:
        return sym, []
    c = np.array([x["c"] for x in px]); v = np.array([x["v"] for x in px])
    cs = np.concatenate([[0], np.cumsum(c)]); vs = np.concatenate([[0], np.cumsum(v)])
    sma = lambda n, t: (cs[t + 1] - cs[t + 1 - n]) / n
    spy_idx = {x["d"]: i for i, x in enumerate(_SPY)}
    out = []
    for t in range(WARMUP, len(px)):
        close = c[t]
        mcap = mc_now * close / c[-1]
        avg30 = (vs[t + 1] - vs[t - 29]) / 30
        s50, s200 = sma(50, t), sma(200, t)
        # 网站扫描条件：市值 ≥30 亿、股价 ≥10、量 ≥50 万、30 日均量 ≥50 万、收盘 > 200 天线、50 天线 > 200 天线、成交额粗筛
        if not (mcap >= 3e9 and close >= 10 and v[t] >= 5e5 and avg30 >= 5e5 and close > s200 and s50 > s200
                and close * avg30 >= 7e7):
            continue
        d = px[t]["d"]
        if d not in spy_idx:
            continue
        w = px[t - 299:t + 1]
        i0 = spy_idx.get(w[0]["d"], 0)
        spy_w = _SPY[i0:spy_idx[d] + 1]
        sc = [x["c"] for x in spy_w]
        p1m = (close / c[t - 21] - 1) * 100
        p6m = (close / c[t - 126] - 1) * 100
        meta = dict(name=sym, description=m.get("description") or "", sector=m.get("sector") or "", industry=m.get("industry") or "",
                    market_cap_basic=mcap, **{"Perf.1M": p1m, "Perf.6M": p6m}, earnings_release_date=None,
                    earnings_release_next_date=None, exchange=m.get("exchange"))
        r = js.analyse(meta, w, spy_w)
        if not r:
            continue
        mt, vc = r["meta"], r["vcp"]
        rec = dict(d=d, mom=bool(r["mom"]), ind=r["industry"], p1m=p1m, p6m=p6m, vcp=dict(score=vc["score"], status=vc["status"],
                   risk=vc["risk"], pivot=vc["pivot"], stop=vc["stop"], ext=vc["ext"]))
        if mt:
            e = mt["edges"]
            rec["meta"] = dict(in_pb=mt["in_pullback"], lowvol=e["低量回调"], ma=e["10/20 天线支撑"], bo=e["突破位支撑"],
                               n=sum(e.values()), risk=mt["risk"], stop=mt["stop"])
        out.append(rec)
    return sym, out


def jlaw_signals(meta, spy_df, P):
    spy_rows = _rows(spy_df)
    last = P["c"].ffill().iloc[-1]
    jobs = [(s, meta[s], meta[s].get("market_cap_basic")) for s in meta if s not in ("SPY", "QQQ")]
    with Pool(int(os.environ.get("BT_POOL", max(1, os.cpu_count() - 1))), initializer=_init, initargs=(spy_rows,)) as pool:
        res = {}
        for i, (s, recs) in enumerate(pool.imap_unordered(jlaw_worker, jobs, chunksize=4), 1):
            res[s] = recs
            if i % 200 == 0:
                print(f"  J Law：{i}/{len(jobs)}", flush=True)
    # 按日期横向：RS 层、热门产业组、就绪名单（与 jlaw_daily_screen.main() 相同）
    spy_c = spy_df["c"]
    by_day = {}
    for s, recs in res.items():
        for r in recs:
            by_day.setdefault(r["d"], []).append((s, r))
    sig = []
    for d, items in by_day.items():
        ts = pd.Timestamp(d)
        k = spy_c.index.get_loc(ts)
        spy1m = (spy_c.iloc[k] / spy_c.iloc[k - 21] - 1) * 100
        spy6m = (spy_c.iloc[k] / spy_c.iloc[k - 126] - 1) * 100
        min1m, min6m = max(2 * spy1m, 5.0), max(2 * spy6m, 10.0)
        rs_layer = {s for s, r in items if r["p1m"] >= min1m and r["p6m"] >= min6m}
        groups = {}
        for s, r in items:
            if r["mom"] or s in rs_layer:
                groups.setdefault(r["ind"], []).append(s)
        hot = {g for g, v in groups.items() if g and len(v) >= 3}
        for s, r in items:
            m = r.get("meta")
            if m and m["in_pb"]:
                n = m["n"] + (r["ind"] in hot)
                if m["lowvol"] and (m["ma"] or m["bo"]) and m["risk"] <= 5.0 and n >= 4:
                    sig.append(dict(kind="META", sym=s, d=ts, stop=m["stop"], n=n))
            v = r["vcp"]
            if s in rs_layer and v["score"] >= 6 and v["status"] in ("等突破", "刚突破") and v["risk"] <= 8.0:
                sig.append(dict(kind="VCP", sym=s, d=ts, stop=v["stop"], pivot=v["pivot"], ext=v["ext"], n=v["score"]))
    return pd.DataFrame(sig)


# ---------------- 模拟交易 ----------------
def simulate(sig, P):
    O, H, L, C = (P[k].values for k in "ohlc")
    S10 = P["c"].rolling(10).mean().values
    S20 = P["c"].rolling(20).mean().values
    col = {s: i for i, s in enumerate(P["c"].columns)}
    idx = {d: i for i, d in enumerate(P["c"].index)}
    T = len(idx)
    trades = []
    busy = {}                                 # (kind, sym) → 持仓到哪一天
    for r in sig.sort_values("d").itertuples():
        j, t = col[r.sym], idx[r.d]
        if busy.get((r.kind, r.sym), -1) >= t or t + 1 >= T:
            continue
        o1, h1 = O[t + 1, j], H[t + 1, j]
        if np.isnan(o1):
            continue
        stop = r.stop
        if r.kind == "META":
            entry = o1
        else:                                  # VCP：突破点挂买入单；高于突破点 5% 不追
            pv = r.pivot
            if o1 > pv * 1.05:
                continue
            if h1 < pv:
                continue
            entry = max(o1, pv)
        if entry <= stop:
            continue
        R = entry - stop
        res = {}
        for mode in ("5R", "MA10", "MA20"):
            ex, ed = None, None
            maxd = 40 if mode == "5R" else 60
            for k in range(t + 1, min(T, t + 1 + maxd)):
                o, h, l, c = O[k, j], H[k, j], L[k, j], C[k, j]
                if np.isnan(c):
                    continue
                if l <= stop:                  # 止损（跳空低开就按开盘价）
                    ex, ed = (min(o, stop) if k > t + 1 else stop), k
                    break
                if mode == "5R":
                    tgt = entry + 5 * R
                    if h >= tgt:
                        ex, ed = (max(o, tgt) if k > t + 1 else tgt), k
                        break
                elif k > t + 1 and c < (S10 if mode == "MA10" else S20)[k, j]:
                    ex, ed = c, k
                    break
            if ex is None:
                ed = min(T - 1, t + maxd)
                while np.isnan(C[ed, j]):
                    ed -= 1
                ex = C[ed, j]
                if ed == T - 1:
                    res[mode] = None           # 还没结束的交易不计
                    continue
            res[mode] = dict(r=(ex - entry) / R, ret=ex / entry - 1, days=ed - t, exit_d=P["c"].index[ed])
        if res.get("MA10") or res.get("5R"):
            hold = max(v["days"] for v in res.values() if v)
            busy[(r.kind, r.sym)] = t + hold
            trades.append(dict(kind=r.kind, sym=r.sym, d=r.d, entry=entry, stop=stop, risk_pct=(entry - stop) / entry * 100,
                               **{f"{m}_{k}": (v[k] if v else None) for m, v in res.items() for k in ("r", "ret", "days", "exit_d")}))
    return pd.DataFrame(trades)


# ---------------- 名单：Stage、Luk ----------------
def lists(P, meta, spy):
    O, H, L, C, V = (P[k] for k in "ohlcv")
    last = C.ffill().iloc[-1]
    mc_now = pd.Series({s: (meta[s].get("market_cap_basic") or np.nan) for s in C.columns})
    mcap = C.div(last).mul(mc_now)
    s50, s200 = C.rolling(50).mean(), C.rolling(200).mean()
    val = C * V
    avg30 = V.rolling(30).mean()
    dollar20 = val.rolling(20).mean()
    out = {}

    # Stage 名单（与 stage_check 相同）
    slope200 = (s200 / s200.shift(21) - 1) * 100
    slope50 = (s50 / s50.shift(10) - 1) * 100
    hi52, lo52 = H.rolling(252).max(), L.rolling(252).min()
    rs = C.div(spy, axis=0)
    rs1m = (rs / rs.shift(21) - 1) * 100
    rs_high = rs >= 0.97 * rs.rolling(126).max()
    pool = (mcap >= 3e9) & (C >= 10) & (V >= 5e5) & (avg30 >= 5e5) & (C * avg30 >= 7e7) & (dollar20 >= 1e8) \
        & (((C > s200) & (s50 > s200)) | (C > s50))
    s2 = pool & (C > s50) & (s50 > s200) & (slope200 >= 1) & (slope50 > 0) & (C >= 0.75 * hi52) & (C >= 1.25 * lo52)
    bhi = H.shift(10).rolling(126).max()
    blo = L.shift(10).rolling(126).min()
    depth = (bhi - blo) / bhi * 100
    s12 = pool & ~s2 & (slope200 >= -1.5) & (slope200 < 1) & (depth <= 40) & (C >= s50) & (C >= 0.97 * s200) & (slope50 >= 0) \
        & (rs1m >= 0) & (C >= 0.92 * bhi) & (C <= 1.10 * bhi)
    avg50 = V.shift(10).rolling(50).mean()
    upv = (V / avg50).where(C > C.shift(1))
    vx = upv.rolling(10).max()
    score = (C > bhi).astype(int) + (vx >= 1.5).astype(int) + (C > s200).astype(int) + (s50 >= 0.98 * s200).astype(int) + rs_high.astype(int)
    newly = lambda m, k: m & ~(m.astype(float).shift(1).rolling(k).max().fillna(0).astype(bool))
    out["Stage 2 新进入"] = newly(s2, 20)
    out["Stage 1→2 候选（新上榜）"] = newly(s12, 10)
    out["Stage 1→2 刚突破 + 得分 ≥4"] = newly(s12 & (C > bhi) & (score >= 4), 10)

    # Luk 三个选股器（近似 TradingView 字段）
    chg = C / C.shift(1) - 1
    gap = O / C.shift(1) - 1
    volw = ((H - L) / C).rolling(5).mean() * 100            # 近似 TradingView「Volatility W」
    ema21 = C.ewm(span=21, adjust=False).mean()
    avg10 = V.rolling(10).mean()
    big = mcap >= 1e8
    strong_ok = big & (volw > 3.5) & (C > ema21) & (val > 5e7)
    gap_ok = big & (avg10 > 5e5) & (val > 5e7) & (gap >= 0.03)
    lead_ok = big & (avg10 > 5e5) & (val.rolling(5).sum() > 3e8)
    perf1m = C / C.shift(21) - 1

    def topn(score_df, ok, n, days=None):
        m = pd.DataFrame(False, index=C.index, columns=C.columns)
        sc = score_df.where(ok)
        for i, d in enumerate(C.index):
            if days is not None and not days[i]:
                continue
            row = sc.iloc[i].dropna()
            if len(row):
                m.loc[d, row.nlargest(n).index] = True
        return m
    fri = np.array([(i + 1 == len(C.index)) or C.index[i + 1].weekday() < C.index[i].weekday() for i in range(len(C.index))])
    out["Luk Strong Day（前 30）"] = topn(chg, strong_ok, 30)
    out["Luk Gappers（前 30）"] = topn(gap, gap_ok, 30)
    out["Luk Leaders（每周前 50）"] = topn(perf1m, lead_ok, 50, fri)
    return out, (C * V).rolling(20).mean()


def forward(masks, P, spy, state, liquid):
    """上榜后：下一天开盘买，持有 N 天后的收盘卖。与 SPY 和全部股票的平均比较。"""
    O, C = P["o"], P["c"]
    rows = []
    fwd = {N: C.shift(-N) / O.shift(-1) - 1 for N in HORIZONS}
    spyf = {N: spy.shift(-N) / P["o"]["SPY"].shift(-1) - 1 for N in HORIZONS}
    base_ok = liquid >= 1e7
    base = {N: fwd[N].where(base_ok).mean(axis=1) for N in HORIZONS}
    start = C.index[WARMUP]
    for name, m in masks.items():
        m = m.loc[start:]
        st = m.stack()
        st = st[st]
        for (d, s) in st.index:
            rec = dict(list=name, d=d, sym=s, state=state.get(d))
            for N in HORIZONS:
                r = fwd[N].at[d, s]
                rec[f"r{N}"] = r
                rec[f"spy{N}"] = spyf[N].at[d]
                rec[f"base{N}"] = base[N].at[d]
            rows.append(rec)
    return pd.DataFrame(rows)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    meta, P, dates = panel()
    print("股票", len(meta), "交易日", len(dates), dates[0].date(), "→", dates[-1].date(), flush=True)
    state, breadth = market_state(P, meta)
    print("大盘状态完成", state.iloc[WARMUP:].value_counts().to_dict(), flush=True)
    spy_df = load_bars("SPY")
    sig = jlaw_signals(meta, spy_df, P)
    print("J Law 信号", len(sig), sig["kind"].value_counts().to_dict() if len(sig) else {}, flush=True)
    trades = simulate(sig, P) if len(sig) else pd.DataFrame()
    print("交易", len(trades), flush=True)
    masks, liquid = lists(P, meta, P["c"]["SPY"])
    # J Law 就绪名单也算上榜后报酬，方便和其他名单比较
    for k in ("META", "VCP"):
        m = pd.DataFrame(False, index=P["c"].index, columns=P["c"].columns)
        for r in sig[sig["kind"] == k].itertuples():
            m.at[r.d, r.sym] = True
        masks[f"J Law {k} 就绪"] = m
    ev = forward(masks, P, P["c"]["SPY"], state, liquid)
    print("名单事件", len(ev), flush=True)
    with open(os.path.join(HERE, "results.pkl"), "wb") as f:
        pickle.dump(dict(state=state, breadth=breadth, sig=sig, trades=trades, ev=ev, start=dates[WARMUP], end=dates[-1],
                         n_stocks=len(meta) - 2, spy=P["c"]["SPY"]), f)
    print("完成")


if __name__ == "__main__":
    main()
