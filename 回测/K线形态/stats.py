"""汇总回测结果 → stats.json
胜率(超额) = 持有期后"按形态方向"跑赢同日全市场平均的比例（看涨：超额>0；看跌：超额<0）。
胜率(绝对) = 看涨形态之后股价上涨的比例 / 看跌形态之后股价下跌的比例。
平均超额 = 按方向的超额收益（看跌形态取负号，正数 = 形态说对了）。收益截断在 ±50%（60 天 ±80%）防止极端值主导。
"""
import json, os
import numpy as np
import pandas as pd
import sys
from patterns import META
SUF = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("2", "3", "4") else ""
if SUF == "2":
    from patterns2 import META2 as META
if SUF == "3":
    from patterns3 import META3 as META
if SUF == "4":
    from patterns_ob import META_OB as META

HERE = os.path.dirname(os.path.abspath(__file__))
HS = (5, 10, 20, 60)
TAG = os.environ.get("BT_TAG", "")
ev = pd.read_pickle(os.path.join(HERE, f"events{SUF}{TAG}.pkl"))
for k in HS:
    cap = 0.8 if k == 60 else 0.5
    ev[f"x{k}"] = ev[f"x{k}"].clip(-cap, cap)
    ev[f"cx{k}"] = (ev[f"c{k}"] - ev[f"br{k}"]).clip(-cap, cap)


BIAS = json.load(open(os.path.join(HERE, f"bias{TAG}.json")))


def summ(g, dirn, col="x", reg="all"):
    s = np.sign(dirn) if dirn else 1
    out = {"n": int(len(g))}
    if len(g) < 30:
        return out
    for k in HS:
        x = g[f"{col}{k}"].dropna() * s
        if len(x) < 30:
            continue
        out[f"ex{k}"] = round(float(x.mean()) * 100 - s * BIAS[f"{k}_{reg}"], 2)   # 扣掉截断造成的基准偏差
        out[f"win{k}"] = round(float((x > 0).mean()) * 100, 1)
        if col == "x":
            r = g[f"r{k}"].dropna() * s
            out[f"abs{k}"] = round(float((r > 0).mean()) * 100, 1)
    for k in (10, 20, 60):
        x = g[f"{col}{k}"].dropna() * s
        if len(x) >= 30:
            out[f"t{k}"] = round(float((x.mean() - s * BIAS[f"{k}_{reg}"] / 100) / (x.std() / np.sqrt(len(x)))), 1)
    return out


res = {}
for p, (cn, dirn, cat) in META.items():
    g = ev[ev.p == p]
    if not len(g):
        continue
    r = {"name": cn, "dir": dirn, "cat": cat, "all": summ(g, dirn)}
    if dirn:
        r["brk_rate"] = round(float((g.brk == dirn).mean()) * 100, 1)
        r["conf_rate"] = round(float(g.conf.mean()) * 100, 1)
        r["conf"] = summ(g[g.conf], dirn, "cx")
    r["vol_hi"] = summ(g[g.vrel >= 1.5], dirn)
    r["vol_lo"] = summ(g[g.vrel < 1.0], dirn)
    r["trend_up"] = summ(g[g.uptrend], dirn)
    r["trend_no"] = summ(g[~g.uptrend], dirn)
    r["near50"] = summ(g[g.near50], dirn)
    r["mkt_bull"] = summ(g[g.mkt], dirn, reg="bull")
    r["mkt_bear"] = summ(g[~g.mkt], dirn, reg="bear")
    # 最佳组合：顺大势（个股上升趋势 + 大盘在 200MA 上）+ 放量
    if dirn > 0:
        r["best"] = summ(g[g.uptrend & g.mkt & (g.vrel >= 1.5)], dirn, reg="bull")
    elif dirn < 0:
        r["best"] = summ(g[~g.above200 & ~g.mkt & (g.vrel >= 1.5)], dirn, reg="bear")
    r["avg_stop"] = round(float(g.stop_pct.median()) * 100, 2)
    g = g.assign(y=g.d.str[:4])
    r["by_year"] = {y: summ(gg, dirn).get("ex20") for y, gg in g.groupby("y")}
    res[p] = r

bl = pd.read_pickle(os.path.join(HERE, f"baseline{TAG}.pkl"))
info = {"n_events": int(len(ev)), "n_stocks": int(ev.sym.nunique()), "start": str(ev.d.min()), "end": str(ev.d.max()),
        "base": {k: round(float(bl[f"r{k}"].mean()) * 100, 2) for k in HS}}
json.dump({"info": info, "res": res}, open(os.path.join(HERE, f"stats{SUF}{TAG}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

rows = []
for p, r in res.items():
    a = r["all"]; b = r.get("best", {})
    rows.append([r["name"][:10], r["dir"], a["n"], a.get("win10"), a.get("ex10"), a.get("ex20"), a.get("ex60"), a.get("t60"), a.get("abs60"),
                 r["vol_hi"].get("ex60"), r["trend_up"].get("ex60"), r["trend_no"].get("ex60"), r["near50"].get("ex20"),
                 r["mkt_bull"].get("ex60"), r["mkt_bear"].get("ex60"), b.get("n"), b.get("ex20"), b.get("ex60"), r.get("conf", {}).get("ex60")])
df = pd.DataFrame(rows, columns=["形态", "向", "n", "胜10", "超10", "超20", "超60", "t60", "绝胜60", "放量60", "升势60", "非升60", "近50MA20",
                                 "牛60", "熊60", "组合n", "组合20", "组合60", "确认60"])
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 30)
print(info)
print(df.sort_values("超60", ascending=False).to_string(index=False))
