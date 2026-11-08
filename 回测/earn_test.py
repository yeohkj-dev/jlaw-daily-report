"""财报前要不要卖？用 META + RS≥90 交易（meta_more20.pkl 的 C8 = 收盘跌 8% 卖、拿 60 天）+ earnings_dates.json。
反应日 R = 财报日（开盘前公布 BMO）或下一个交易日（收盘后公布 AMC）。持有期间如果遇到 R：
  A 照拿（原版）
  B 财报前全卖：R 的前一个交易日收盘卖（如果在那之前没被止损）
  C 财报前卖一半：A、B 各一半
  D 不买：信号日后 14 个日历天内有财报的信号不做（J Law 的规则）
输出 earn_trades20.pkl（每笔 A/B 的收益、出场日、跟 SPY/QQQ 比）+ 打印逐笔统计。"""
import json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache20")


def load(sym):
    df = pd.DataFrame(json.load(open(os.path.join(CACHE, sym + ".json")))).dropna()
    return df[(df.h > df.l) & (df.v > 0) & (df.o > 0)].reset_index(drop=True)


if __name__ == "__main__":
    T = pd.read_pickle(os.path.join(HERE, "meta_more20.pkl"))
    T = T[T.rs >= 90].copy()
    E = json.load(open(os.path.join(HERE, "earnings_dates.json")))
    spy, qqq = load("SPY"), load("QQQ")
    so, sc = dict(zip(spy.d, spy.o)), dict(zip(spy.d, spy.c))
    qo, qc = dict(zip(qqq.d, qqq.o)), dict(zip(qqq.d, qqq.c))
    rows = []
    for sym, g in T.groupby("sym"):
        df = load(sym); d = list(df.d.values); o, c = df.o.values, df.c.values
        pos = {x: i for i, x in enumerate(d)}
        ev = []
        for s in E.get(sym) or []:
            day, kind = s.split()
            i = int(np.searchsorted(d, day))          # 第一个 ≥ 财报日的交易日
            if i >= len(d):
                continue
            if kind == "AMC" and d[i] == day:
                i += 1
            if i < len(d):
                ev.append(i)                           # 反应日 index
        ev = sorted(set(ev))
        first_e = E.get(sym)[0].split()[0] if E.get(sym) else "9999"
        for r in g.itertuples():
            t = pos[r.ed]; k = pos[r.C8_xd]
            sig_i = t - 1
            # 持有期间（买入那天开盘之后）第一个反应日
            R = next((x for x in ev if t < x <= k), None)
            row = {"sym": sym, "d": r.d, "ed": r.ed, "entry": r.entry, "mkt": r.mkt, "rs": r.rs,
                   "covered": r.d >= first_e, "A": r.C8, "A_xd": r.C8_xd, "A_x": r.C8_x, "A_xq": r.C8_xq,
                   "has_e": R is not None, "soon14": any(sig_i < x and (pd.Timestamp(d[x]) - pd.Timestamp(r.d)).days <= 14 for x in ev)}
            if R is not None:
                kb = R - 1                                     # 反应日前一天收盘卖
                rb = c[kb] / o[t] - 1
                row.update(B=rb, B_xd=d[kb], B_x=rb - (sc[d[kb]] / so[d[t]] - 1), B_xq=rb - (qc[d[kb]] / qo[d[t]] - 1),
                           gap=o[R] / c[R - 1] - 1, day=c[R] / c[R - 1] - 1)
            else:
                row.update(B=r.C8, B_xd=r.C8_xd, B_x=r.C8_x, B_xq=r.C8_xq, gap=np.nan, day=np.nan)
            rows.append(row)
    X = pd.DataFrame(rows)
    X.to_pickle(os.path.join(HERE, "earn_trades20.pkl"))
    print("笔数", len(X), "有财报日资料覆盖", int(X.covered.sum()), "持有期间遇到财报", int(X.has_e.sum()), "信号后 14 天内有财报", int(X.soon14.sum()))
    W = X[X.has_e]
    print(f"遇到财报那天：开盘跳空平均 {100*W.gap.mean():+.2f}%，中位 {100*W.gap.median():+.2f}%，跳空 ≤ −10% 的 {100*(W.gap<=-.10).mean():.1f}%，≥ +10% 的 {100*(W.gap>=.10).mean():.1f}%；"
          f"当天收盘比前一天平均 {100*W.day.mean():+.2f}%")
    for lab, S in (("全部", X), ("SPY>200", X[X.mkt])):
        for m in ("A", "B"):
            print(f"{lab:7s} {m} 笔{len(S)} 平均{100*S[m].mean():6.2f}% 比SPY{100*S[m+'_x'].mean():6.2f}% 比QQQ{100*S[m+'_xq'].mean():6.2f}% 胜率{100*(S[m]>0).mean():4.0f}% 最差1% {100*S[m].quantile(.01):6.1f}%")
        Cm = (S.A + S.B) / 2; Cx = (S.A_xq + S.B_xq) / 2
        print(f"{lab:7s} C 平均{100*Cm.mean():6.2f}% 比QQQ{100*Cx.mean():6.2f}%")
        D = S[~S.soon14]
        print(f"{lab:7s} D 不做14天内有财报：笔{len(D)} 平均{100*D.A.mean():6.2f}% 比SPY{100*D.A_x.mean():6.2f}% 比QQQ{100*D.A_xq.mean():6.2f}%；被去掉的 {len(S)-len(D)} 笔 比QQQ{100*S[S.soon14].A_xq.mean():6.2f}%")
