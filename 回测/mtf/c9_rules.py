"""C9 方法的买进信号（日线），依据 c9 training 课程笔记（Day1–Day7）。课程有写数字的照用，没写的标「解读」。

  大盘：SPY 收盘在 200 天线上（课程只有「Index hardly break D200」，解读）
  Stage 2（D2 p22）：收盘 > 150 天线和 200 天线；连续 ≥ 21 天在 200 天线上（「above DMA 200 at least one month」）；
                    200 天线向上（解读：比 21 天前高，代表 HH & HL 升势）
  之前有升势（D3 p5「已经上升 20∼30%」）：底部最高点比底部开始前 63 天内最低点高 ≥ 25%
  底部 ≥ 3 个月（D3 p41「Length of Base – At least 3 months」）：用前 63 个交易日
    深度 10–40%（杯 30–40%，平台 / VCP 较浅；解读）
    收缩（VCP「30%…15%…8%」）：最后 21 天的振幅 < 前 42 天振幅的 60%，最后 10 天振幅 < 10%（解读）
    量缩（「Price Tight Volume Dry」）：前一天的 10 日均量 < 50 日均量
  买点（D4 p2 枢轴突破）：收盘突破底部最高点（前 63 天最高价），且不高于它 5%（「错过E位3∼5%，不建议高追」）
止损（D6 p37 图上 10%）：在 research21.py 的 STOPS 里设成收盘跌 10%、盘中 −15% 保护（解读）
"""
import numpy as np
import pandas as pd

BASE = 63


def signals(D, X, spy_up):
    c, h, l, v = D["c"], D["h"], D["l"], D["v"]
    m150, m200 = c.rolling(150).mean(), c.rolling(200).mean()
    above200 = (c > m200).astype(int).rolling(21).min() == 1
    stage2 = (c > m150) & (c > m200) & above200 & (m200 > m200.shift(21))
    base_hi = h.rolling(BASE).max().shift(1)
    base_lo = l.rolling(BASE).min().shift(1)
    depth = (base_hi - base_lo) / base_hi
    early = (h.shift(22).rolling(42).max() - l.shift(22).rolling(42).min()) / h.shift(22).rolling(42).max()
    late = (h.shift(1).rolling(21).max() - l.shift(1).rolling(21).min()) / h.shift(1).rolling(21).max()
    last10 = (h.shift(1).rolling(10).max() - l.shift(1).rolling(10).min()) / h.shift(1).rolling(10).max()
    prior_lo = l.shift(BASE + 1).rolling(63).min()
    prior_up = base_hi / prior_lo >= 1.25
    dry = v.shift(1).rolling(10).mean() < v.shift(1).rolling(50).mean()
    liquid = (c >= 5) & ((v * c).rolling(20).mean() >= 5e6)
    trig = (c > base_hi) & (c.shift(1) <= base_hi.shift(1)) & (c <= base_hi * 1.05)
    ok = (stage2 & prior_up & (depth >= 0.10) & (depth <= 0.40) & (late < 0.6 * early) & (last10 < 0.10) & dry & liquid & trig
          & spy_up.reindex(D.index).fillna(False))
    return [i for i in np.where(ok.fillna(False).values)[0] if i >= 260]
