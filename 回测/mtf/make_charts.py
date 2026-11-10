"""多时间框架买点的图表例子（真实回测交易）：左边日线（大周期，找形态），右边 2 小时线（小周期，找买点）。

用法：python 回测/mtf/make_charts.py → 回测/mtf/charts/*.png，并复制到 docs/img/mtf/（网站用）
"""
import datetime as dt
import os
import shutil
import sys

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans CJK SC", "Noto Sans SC", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mtf_bt as M

OUT = os.path.join(HERE, "charts")
SITE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "docs", "img", "mtf")
EXAMPLES = [
    dict(file="brk_rklb", sym="RKLB", sig="2024-09-27", kind="BRK", m="E2",
         title="放量突破 50 日高 + 2 小时开盘区间突破（RKLB，2024-09）"),
    dict(file="brk_gehc", sym="GEHC", sig="2025-02-13", kind="BRK", m="E2",
         title="放量突破后 2 小时始终没有突破 → 不买（GEHC，2025-02）"),
    dict(file="a0_lite", sym="LITE", sig="2025-10-06", kind="A0", m="E3",
         title="A0（META + RS≥90）+ 2 小时收盘重新站上 20 EMA（LITE，2025-10）"),
    dict(file="a0_coin", sym="COIN", sig="2025-07-25", kind="A0", m="E3",
         title="A0 信号后 2 小时一直在 20 EMA 下面 → 不买（COIN，2025-07）"),
]
UP, DN = "#26a69a", "#ef5350"


def candles(ax, xs, o, h, l, c, w=0.6):
    for x, oo, hh, ll, cc in zip(xs, o, h, l, c):
        col = UP if cc >= oo else DN
        ax.vlines(x, ll, hh, color=col, lw=0.8)
        ax.add_patch(plt.Rectangle((x - w / 2, min(oo, cc)), w, max(abs(cc - oo), (hh - ll) * 0.005), color=col))


def draw(ex):
    D = M.daily(ex["sym"])
    sig = pd.Timestamp(ex["sig"])
    i0 = D.index.get_loc(sig)
    days = [d.date() for d in D.index]
    g60 = M.day_bars(M.get60(ex["sym"]))
    flat, by = M.aggregate(g60, 120)
    ent = M.entries("META", None, i0, D, days, flat, by)
    e = ent.get(ex["m"])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 5.6), gridspec_kw=dict(width_ratios=[1.15, 1]))
    fig.suptitle(ex["title"], fontsize=13, fontweight="bold", x=0.01, ha="left")

    # ---- 日线 ----
    lo, hi = max(0, i0 - 70), min(len(D), i0 + 25)
    W = D.iloc[lo:hi]
    xs = range(len(W))
    candles(a1, xs, W.o.values, W.h.values, W.l.values, W.c.values)
    a1.plot(xs, D.c.rolling(20).mean().iloc[lo:hi].values, color="#43a047", lw=1, label="20 天线")
    a1.plot(xs, D.c.rolling(50).mean().iloc[lo:hi].values, color="#1e88e5", lw=1, label="50 天线")
    si = i0 - lo
    if ex["kind"] == "BRK":
        lvl = D.h.rolling(50).max().shift(1).iloc[i0]
        a1.hlines(lvl, si - 50, si, color="#ff9800", ls="--", lw=1.2, label="前 50 天最高价")
    a1.annotate("大周期信号", (si, W.h.values[si]), xytext=(-70, 25), textcoords="offset points", color="#1F4E78", fontsize=10,
                arrowprops=dict(arrowstyle="->", color="#1F4E78"))
    a1.axvspan(si + 0.5, si + 5.5, color="#FFF3E0", alpha=0.7, label="之后 5 天：看 2 小时图找买点")
    a1.set_title("日线（大周期）：找趋势和形态", fontsize=11, loc="left")
    a1.legend(fontsize=8, loc="upper left")
    a1.set_xticks([si]), a1.set_xticklabels([f"{sig:%Y-%m-%d}"], fontsize=9)
    a1.grid(alpha=0.2)

    # ---- 2 小时线 ----
    show_days = days[i0 - 2:i0 + 7]
    idxs = [fi for d in show_days for fi in by.get(d, [])]
    B = [flat[fi] for fi in idxs]
    xs2 = range(len(B))
    candles(a2, xs2, [b["o"] for b in B], [b["h"] for b in B], [b["l"] for b in B], [b["c"] for b in B], w=0.55)
    if ex["m"] == "E3":
        a2.plot(xs2, [b["ema"] for b in B], color="#8e24aa", lw=1.3, label="2 小时 20 EMA")
    # 每天第一根 2 小时K线的高点（开盘区间）
    for d in show_days[3:8]:
        f = by.get(d, [])
        if f and ex["m"] == "E2":
            k0 = idxs.index(f[0])
            a2.hlines(flat[f[0]]["h"], k0, k0 + len(f) - 0.5, color="#ff9800", ls="--", lw=1)
    day_starts = [idxs.index(by[d][0]) for d in show_days if by.get(d)]
    for k, d in zip(day_starts, [d for d in show_days if by.get(d)]):
        a2.axvline(k - 0.5, color="#ccc", lw=0.6)
        a2.text(k, a2.get_ylim()[0] if False else min(b["l"] for b in B), f"{d:%m-%d}", fontsize=8, color="#888", va="top")
    if e:
        k, px, when = e
        fi = next((idxs.index(i) for i in by.get(days[k], []) if flat[i]["end"] == when), None)
        if fi is not None:
            a2.scatter([fi], [px], s=120, marker="^", color="#2E7D32", zorder=5)
            a2.annotate(f"小周期买点 {px:.2f}", (fi, px), xytext=(-80, 40), textcoords="offset points", color="#2E7D32", fontsize=10, fontweight="bold",
                        arrowprops=dict(arrowstyle="->", color="#2E7D32"))
            stop = px * (1 - (0.15 if ex["kind"] == "BRK" else 0.08))
            a2.axhline(stop, color="#C62828", ls=":", lw=1.1, label=f"止损 {stop:.2f}（{'收盘跌 15%' if ex['kind'] == 'BRK' else '收盘跌 8%'}）")
        # 次日开盘买的价位（对照）
        a2.axhline(D.o.iloc[i0 + 1], color="#757575", ls="-.", lw=0.9, label=f"次日开盘价 {D.o.iloc[i0 + 1]:.2f}（旧做法）")
    else:
        a2.text(0.5, 0.5, "5 天内没有出现 2 小时买点 → 不买", transform=a2.transAxes, ha="center", color="#C62828", fontsize=13, fontweight="bold",
                bbox=dict(facecolor="white", edgecolor="#C62828", alpha=0.9, boxstyle="round,pad=0.4"))
        a2.axhline(D.o.iloc[i0 + 1], color="#757575", ls="-.", lw=0.9, label=f"次日开盘价 {D.o.iloc[i0 + 1]:.2f}（旧做法会买在这里）")
    a2.set_title("2 小时线（小周期）：找买点", fontsize=11, loc="left")
    a2.legend(fontsize=8, loc="upper left")
    a2.set_xticks([])
    a2.grid(alpha=0.2)

    # 结果说明
    after = D.iloc[i0 + 1:i0 + 61]
    ret_d0 = None
    note = ""
    if e:
        k, px, _ = e
        ex_ = M.exit_a0(D, k, px, e[2], g60, days) if ex["kind"] != "BRK" else None
        if ex["kind"] == "BRK":
            c = D.c.values
            j = next((j for j in range(k, min(len(c), k + 60)) if c[j] <= px * 0.85), min(len(c) - 1, k + 59))
            note = f"结果：小周期买 {px:.2f} → {'止损' if c[j] <= px * 0.85 else '拿满 60 天'}卖 {c[j]:.2f}（{(c[j] / px - 1) * 100:+.0f}%）"
        elif ex_:
            j, xp, why, _ = ex_
            note = f"结果：小周期买 {px:.2f} → 卖 {xp:.2f}（{(xp / px - 1) * 100:+.0f}%，{ {'time': '拿满 60 天', 'close8': '收盘跌 8%', 'hard': '跌到 −12%'}.get(why, why) }）"
    else:
        lo_ = after.l.min()
        note = f"如果照旧做法次日开盘买 {D.o.iloc[i0 + 1]:.2f}：之后 60 天最低到 {lo_:.2f}（{(lo_ / D.o.iloc[i0 + 1] - 1) * 100:+.0f}%），会被止损"
    fig.text(0.01, 0.01, note, fontsize=10.5, color="#333")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, ex["file"] + ".png")
    fig.savefig(path, dpi=90)
    plt.close(fig)
    return path, note


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(SITE, exist_ok=True)
    for ex in EXAMPLES:
        p, note = draw(ex)
        shutil.copy(p, os.path.join(SITE, os.path.basename(p)))
        print(p, os.path.getsize(p) // 1024, "KB |", note)


if __name__ == "__main__":
    main()
