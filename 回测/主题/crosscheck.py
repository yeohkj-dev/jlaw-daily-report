"""主题雷达研究 ④：数据核对，写 data/crosscheck.json。
 1. 日线缓存（Yahoo）vs TradingView 选股器：全部股票的 1 年涨幅（缓存到最后一天为止 vs TradingView 今天的 Perf.Y，日期差几天，只看中位差距）
 2. 随机抽 5 个综合信号，直接从原始 JSON 逐只重算「之后 12 个月成员平均涨跌」和同期 SPY，对比 panel 里的数字
 3. 主题篮子 vs 主题 ETF：信号日期是否接近（在报告的主题表里）
用法：python 回测/主题/crosscheck.py
"""
import json
import os
import random
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, HERE)
from common import tv_scan  # noqa: E402
from analyze import first_entries  # noqa: E402

BT = os.environ.get("BT_DIR") or os.path.join(os.path.dirname(REPO), "回测")
D = os.path.join(HERE, "data")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    out = []
    meta = json.load(open(os.path.join(D, "meta.json"), encoding="utf-8"))
    p = pd.read_pickle(os.path.join(D, "panel.pkl")).sort_values(["group", "date"]).reset_index(drop=True)

    # 1. vs TradingView
    try:
        data = tv_scan({"filter": [{"left": "market_cap_basic", "operation": "greater", "right": 2e8}], "columns": ["name", "close", "Perf.Y"],
                        "options": {"lang": "en"}, "range": [0, 6000], "markets": ["america"]})
        tv = {x["d"][0]: x["d"] for x in data}
        diffs, n = [], 0
        for s in meta["exchange"]:
            if s not in tv or tv[s][2] is None:
                continue
            c = json.load(open(os.path.join(BT, "cache20", s + ".json")))["c"]
            if len(c) < 253:
                continue
            diffs.append(abs((c[-1] / c[-253] - 1) * 100 - tv[s][2])); n += 1
        med = float(np.median(diffs)); within = float(np.mean(np.array(diffs) <= 15))
        out.append(dict(name="日线缓存 vs TradingView（1 年涨幅）", ok=med <= 8 and n > 1500,
                        detail=f"{n} 只股票：缓存（到 {meta['last']}）和 TradingView 今天的 1 年涨幅，差距中位数 {med:.1f} 个百分点，{within*100:.0f}% 的股票差 ≤15 个百分点（两边日期差几天，所以不会完全一样；用来抓拆股之类的大错）"))
    except Exception as e:
        out.append(dict(name="日线缓存 vs TradingView（1 年涨幅）", ok=False, detail=f"TradingView 取不到：{e}"))

    # 2. 抽查重算
    sig = first_entries(p, "p_comp").dropna(subset=["f12"])
    random.seed(7)
    spy = json.load(open(os.path.join(BT, "cache20", "SPY.json")))
    sd = {d: i for i, d in enumerate(spy["d"])}
    bad, lines = 0, []
    for _, r in sig.sample(5, random_state=7).iterrows():
        d0 = str(r["date"].date()); i0 = sd[d0]; d1 = spy["d"][i0 + 252]
        rets = []
        for s in meta["members"][r["group"]]:
            j = json.load(open(os.path.join(BT, "cache20", s + ".json")))
            ix = {d: i for i, d in enumerate(j["d"])}
            if d0 in ix and d1 in ix and ix[d0] >= 252 and spy["d"][i0 - 252] in ix:      # 一年前就有K线 = 当时是成员
                rets.append(j["c"][ix[d1]] / j["c"][ix[d0]] - 1)
        mine, sp = float(np.mean(rets)), spy["c"][i0 + 252] / spy["c"][i0] - 1
        okk = abs(mine - r["f12"]) < 0.01 and abs(sp - r["spy12"]) < 1e-6
        bad += not okk
        lines.append(f"{d0} {r['group']}：重算 {mine*100:+.1f}%（{len(rets)} 只）vs 回测 {r['f12']*100:+.1f}%（{int(r['n'])} 只），SPY {sp*100:+.1f}% vs {r['spy12']*100:+.1f}%")
    out.append(dict(name="抽查 5 个信号，从原始日线逐只重算之后 12 个月", ok=bad == 0, detail="；".join(lines)))
    json.dump(out, open(os.path.join(D, "crosscheck.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for c in out:
        print("✔" if c["ok"] else "⚠", c["name"], "|", c["detail"])


if __name__ == "__main__":
    main()
