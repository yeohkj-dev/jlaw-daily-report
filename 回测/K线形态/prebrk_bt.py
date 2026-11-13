"""「即将突破（等放量）」名单回测：收盘后先列出快要突破的股票，之后几天放量突破时，什么时候买最好？（2026-11-13）

名单（第 i 天收盘后，全部规则）：
  股票升势：收盘 > 50 天线 > 200 天线、50 天线比 10 天前高；SPY 在 200 天线上；价 ≥ 5、20 日均成交额 ≥ 500 万
  离 50 日最高价（含今天）0–5%，还没突破；波动收窄：近 10 天 ATR < 之前 30 天 ATR × 0.8（N 版不要求）
  成交量萎缩：近 5 天均量 < 50 日均量（N 版不要求）
  突破价 = 名单当天的 50 日最高价（之后不再改）
之后 5 个交易日内等突破（第一次最高价 > 突破价那天 = 突破日 j），比较几种买法：
  I  盘中一穿过突破价就买（买价 = max(开盘, 突破价)），不管成交量 —— 假突破也会买到
  IV 同上，但只算当天全天成交量 ≥ 20 日均量 2 倍的（实际要靠盘中按时间推算的量，这里用全天量，略偏乐观）
  C  当天收盘确认（收盘 > 突破价、量 ≥ 2 倍）才买，用收盘价
  N  当天收盘确认后，第二天开盘买（= 网站 A3 现在的做法，只是股票先在名单上）
对照 A3：不看名单，所有「放量（≥2 倍）收盘突破 50 日高 + 升势 + SPY 在 200 天线上」第二天开盘买（20 年回测的原版）。
卖法都用 A3 的：收盘比买价跌 15% → 第二天开盘卖；否则拿 60 个交易日收盘卖。
超额 = 同期（买入到卖出）买 SPY 的报酬差。每只股票同一种买法持仓期间不重复买。
数据：仓库旁边的 回测/cache20（约 2,250 只美股 2005–2026，今天还在交易的股票 → 有幸存者偏差）。
用法：python prebrk_bt.py   → prebrk_bt20.json、prebrk_trades20.pkl
"""
import glob
import json
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get("BT_CACHE", os.path.join(HERE, "..", "..", "..", "回测", "cache20"))
WAIT = 5            # 名单出来后等几个交易日
HOLD = 60
CAT = 0.15          # 收盘比买价跌 15% 卖
VOLX = 2.0
NEAR = 0.05


def load(path):
    df = pd.DataFrame(json.load(open(path))).dropna()
    return df[(df.h > df.l) & (df.v > 0) & (df.o > 0)].reset_index(drop=True)


SPY = load(os.path.join(CACHE, "SPY.json"))
SPY["a200"] = SPY.c > SPY.c.rolling(200).mean()
SPY_A200 = dict(zip(SPY.d, SPY.a200))
SPY_O = dict(zip(SPY.d, SPY.o))
SPY_C = dict(zip(SPY.d, SPY.c))


def exit_from(o, c, d, ie, px, entry_at_close):
    """从第 ie 天以 px 买（entry_at_close=True 表示当天收盘买，当天不检查止损）。回传 (报酬, 卖出日 index, 卖出用开盘?)。"""
    N = len(c)
    start = ie + 1 if entry_at_close else ie
    last = min(ie + HOLD, N - 1)
    for k in range(start, last + 1):
        if c[k] < px * (1 - CAT) and k + 1 < N:
            return o[k + 1] / px - 1, k + 1, True
    return c[last] / px - 1, last, False


def spy_ret(d_in, at_open_in, d_out, at_open_out):
    a = (SPY_O if at_open_in else SPY_C).get(d_in)
    b = (SPY_O if at_open_out else SPY_C).get(d_out)
    return b / a - 1 if a and b else None


def run_sym(f):
    sym = os.path.basename(f)[:-5]
    if sym in ("SPY", "QQQ"):
        return []
    df = load(f)
    if len(df) < 300:
        return []
    o, h, l, c, v = (df[k].astype(float).values for k in "ohlcv")
    d = df.d.values
    N = len(c)
    s = pd.Series(c)
    sma50, sma200 = s.rolling(50).mean().values, s.rolling(200).mean().values
    sma50_10 = np.roll(sma50, 10)
    H50 = pd.Series(h).rolling(50).max().values                    # 含今天
    hh50_prev = pd.Series(h).rolling(50).max().shift(1).values     # 不含今天（A3 用）
    c1 = np.roll(c, 1)
    tr = np.maximum(h - l, np.maximum(abs(h - c1), abs(l - c1)))
    atr10 = pd.Series(tr).rolling(10).mean().values
    atr30p = pd.Series(tr).rolling(30).mean().shift(10).values      # 之前 30 天（不含最近 10 天）
    v5 = pd.Series(v).rolling(5).mean().values
    v50 = pd.Series(v).rolling(50).mean().values
    avgv20 = pd.Series(v).rolling(20).mean().shift(1).values        # 不含当天
    liquid = (c >= 5) & (pd.Series(v * c).rolling(20).mean().values >= 5e6)
    mkt = np.array([bool(SPY_A200.get(x, False)) for x in d])
    up = (c > sma50) & (sma50 > sma200) & (sma50 > sma50_10)

    out = []
    busy = {}

    def add(kind, i_sig, j, px, at_open, extra):
        if busy.get(kind, -1) >= j:
            return
        r, jx, x_open = exit_from(o, c, d, j, px, not at_open)
        sp = spy_ret(d[j], at_open, d[jx], x_open)
        busy[kind] = jx
        out.append(dict(sym=sym, kind=kind, d=d[i_sig], ed=d[j], year=d[j][:4], r=r, x=(r - sp) if sp is not None else np.nan,
                        held=jx - j, **extra))

    for i in range(260, N - 2):
        if not (liquid[i] and mkt[i] and up[i]):
            continue
        # ---- 对照：A3 原版（放量收盘突破前 50 天最高价，第二天开盘买）----
        if c[i] > hh50_prev[i] and c1[i] <= hh50_prev[i - 1] and avgv20[i] > 0 and v[i] >= VOLX * avgv20[i]:
            add("A3", i, i + 1, o[i + 1], True, {})
        # ---- 即将突破名单 ----
        lvl = H50[i]
        dist = 1 - c[i] / lvl
        if not (0 < dist <= NEAR):
            continue
        tight = atr10[i] < 0.8 * atr30p[i]
        dry = v5[i] < v50[i]
        for tag, ok in (("", tight and dry), ("_all", True)):
            if not ok:
                continue
            j = next((k for k in range(i + 1, min(i + WAIT + 1, N - 1)) if h[k] > lvl), None)
            if j is None:
                if tag == "":
                    out.append(dict(sym=sym, kind="LIST_MISS", d=d[i], ed=None, year=d[i][:4], r=np.nan, x=np.nan, held=0))
                continue
            vok = avgv20[j] > 0 and v[j] >= VOLX * avgv20[j]
            cok = c[j] > lvl
            ex = dict(gap=o[j] / lvl - 1, dist=dist, vok=bool(vok), cok=bool(cok))
            add("I" + tag, i, j, max(o[j], lvl), True, ex)
            if vok:
                add("IV" + tag, i, j, max(o[j], lvl), True, ex)
            if vok and cok:
                add("C" + tag, i, j, c[j], False, ex)
                add("N" + tag, i, j + 1, o[j + 1], True, ex)
            if tag == "":
                out.append(dict(sym=sym, kind="LIST_HIT", d=d[i], ed=d[j], year=d[i][:4], r=np.nan, x=np.nan, held=0, vok=bool(vok), cok=bool(cok)))
    return out


def summ(t):
    r, x = t.r, t.x.dropna()
    by = t.groupby("year").x.mean()
    return dict(n=int(len(t)), win=round(100 * (r > 0).mean(), 1), avg=round(100 * r.mean(), 2), med=round(100 * r.median(), 2),
                ex=round(100 * x.mean(), 2), ex_med=round(100 * x.median(), 2),
                t=round(x.mean() / x.std() * np.sqrt(len(x)), 1) if len(x) > 2 else None,
                worst5=round(100 * r.quantile(0.05), 1), hold=round(t.held.mean(), 1),
                years_pos=int((by > 0).sum()), years=int(by.size),
                ex_2016=round(100 * t[t.year >= "2016"].x.mean(), 2), ex_pre=round(100 * t[t.year < "2016"].x.mean(), 2),
                by_year={k: round(100 * v_, 2) for k, v_ in by.items()})


def main():
    files = sorted(glob.glob(os.path.join(CACHE, "*.json")))
    with Pool(10) as p:
        rows = [r for rs in p.imap_unordered(run_sym, files, chunksize=20) for r in rs]
    T = pd.DataFrame(rows)
    for col in ("vok", "cok"):
        T[col] = T[col].fillna(False).astype(bool)
    T.to_pickle(os.path.join(HERE, "prebrk_trades20.pkl"))
    res = {"info": dict(start=str(T.d.min()), end=str(T.d.max()), stocks=len(files) - 2, wait=WAIT, hold=HOLD, cat=CAT, volx=VOLX, near=NEAR)}
    for k in ["A3", "I", "IV", "C", "N", "I_all", "IV_all", "C_all", "N_all"]:
        ts = T[T.kind == k]
        if len(ts):
            res[k] = summ(ts)
    hit, miss = T[T.kind == "LIST_HIT"], T[T.kind == "LIST_MISS"]
    n_list = len(hit) + len(miss)
    res["list"] = dict(n=n_list, hit=round(100 * len(hit) / n_list, 1) if n_list else None,
                       hit_vol=round(100 * hit.vok.sum() / n_list, 1) if n_list else None,
                       hit_vol_close=round(100 * (hit.vok & hit.cok).sum() / n_list, 1) if n_list else None,
                       per_day=round(n_list / T[T.kind.isin(["LIST_HIT", "LIST_MISS"])].d.nunique(), 1) if n_list else None)
    # 盘中穿过但收盘跌回突破价下面（假突破）的比例和报酬
    I = T[T.kind == "I"]
    if len(I):
        res["I_fake"] = summ(I[~I.cok]) | dict(share=round(100 * (~I.cok).mean(), 1))
        res["I_real"] = summ(I[I.cok])
    json.dump(res, open(os.path.join(HERE, "prebrk_bt20.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in res.items():
        if isinstance(v, dict) and "ex" in v:
            print(f"{k:7s} n={v['n']:6d} 胜率 {v['win']:5.1f}%  平均 {v['avg']:+6.2f}%  超额 {v['ex']:+6.2f}%（中位 {v['ex_med']:+.2f}）"
                  f" t={v['t']}  2016前 {v['ex_pre']:+.2f} / 后 {v['ex_2016']:+.2f}  年份正 {v['years_pos']}/{v['years']}")
    print("名单", res["list"])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
